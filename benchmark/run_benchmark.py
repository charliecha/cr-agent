"""
Benchmark runner: runs both CR implementations against the same test PR fixtures
and outputs a comparison table + JSON results file.

Usage:
    python -m benchmark.run_benchmark [--output results/run.json]
"""

import os
import json
import time
import subprocess
import sys
from pathlib import Path
from typing import Any

import click
from pydantic import ValidationError
from dotenv import load_dotenv

from shared.schemas import CRReport

# Load .env so ADK agents can access CR_MODEL at import time
load_dotenv()

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_PRS = json.loads((Path(__file__).parent / "test_prs.json").read_text())


def run_framework(framework: str, fixture: dict) -> dict:
    """
    Run one framework against one fixture. Returns a metrics dict.
    Uses pr.diff as a local diff file; repo_path as the repo root.
    """
    repo_path = str(FIXTURES_DIR / fixture["repo_path"].split("/")[-1])
    diff_path = str(FIXTURES_DIR / fixture["repo_path"].split("/")[-1] / "pr.diff")

    module = "deep_agents.run" if framework == "deep_agents" else "adk.run"

    start = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", module, "--pr", diff_path, "--repo", repo_path, "--output", "-"],
            capture_output=True,
            text=True,
            timeout=150,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return {
            "framework": framework,
            "fixture_id": fixture["id"],
            "latency_seconds": round(elapsed, 2),
            "output_valid_json": False,
            "findings_count": 0,
            "true_positives": 0,
            "false_positives": 0,
            "expected_bugs": len(fixture["known_bugs"]),
            "verdict": "timeout",
            "stderr": f"subprocess killed after 150s",
        }
    elapsed = time.monotonic() - start

    output_valid = False
    findings_count = 0
    true_positives = 0
    false_positives = 0
    verdict = "error"

    if proc.returncode == 0 and proc.stdout.strip():
        try:
            report = CRReport.model_validate_json(proc.stdout)
            output_valid = True
            findings_count = len(report.findings)
            verdict = report.verdict

            known = {(b["file"], b["category"]) for b in fixture["known_bugs"]}
            matched = set()
            for f in report.findings:
                key = (f.file, f.category)
                if key in known and key not in matched:
                    true_positives += 1
                    matched.add(key)
                elif f.severity in ("critical", "warning"):
                    false_positives += 1
        except (ValidationError, json.JSONDecodeError) as e:
            pass

    return {
        "framework": framework,
        "fixture_id": fixture["id"],
        "latency_seconds": round(elapsed, 2),
        "output_valid_json": output_valid,
        "findings_count": findings_count,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "expected_bugs": len(fixture["known_bugs"]),
        "verdict": verdict,
        "stderr": proc.stderr[-500:] if proc.stderr else "",
    }


@click.command()
@click.option("--output", default="benchmark/results/latest.json", help="Output file for results")
@click.option("--framework", "frameworks", multiple=True,
              type=click.Choice(["deep_agents", "adk"]),
              default=["deep_agents", "adk"],
              help="Frameworks to run (repeatable, default: both)")
def main(output: str, frameworks: tuple):
    results = []

    for fixture in TEST_PRS:
        for framework in frameworks:
            click.echo(f"Running {framework} on {fixture['id']} ...", err=True)
            result = run_framework(framework, fixture)
            results.append(result)
            _print_row(result)

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(results, indent=2))
    click.echo(f"\nFull results saved to {output}", err=True)

    _print_summary(results)


def _print_row(r: dict) -> None:
    status = "OK" if r["output_valid_json"] else "FAIL"
    click.echo(
        f"  [{status}] {r['framework']:15} {r['fixture_id']:30} "
        f"tp={r['true_positives']}/{r['expected_bugs']} "
        f"fp={r['false_positives']} "
        f"{r['latency_seconds']}s "
        f"verdict={r['verdict']}"
    )


def _print_summary(results: list[dict]) -> None:
    click.echo("\n── Summary ─────────────────────────────────────────────────")
    for fw in ["deep_agents", "adk"]:
        fw_results = [r for r in results if r["framework"] == fw]
        total_tp = sum(r["true_positives"] for r in fw_results)
        total_expected = sum(r["expected_bugs"] for r in fw_results)
        total_fp = sum(r["false_positives"] for r in fw_results)
        avg_latency = sum(r["latency_seconds"] for r in fw_results) / len(fw_results) if fw_results else 0.0
        schema_ok = all(r["output_valid_json"] for r in fw_results)
        click.echo(
            f"  {fw:15}  "
            f"recall={total_tp}/{total_expected}  "
            f"false_positives={total_fp}  "
            f"avg_latency={avg_latency:.1f}s  "
            f"schema_valid={'yes' if schema_ok else 'NO'}"
        )


if __name__ == "__main__":
    main()
