"""
CLI entry point for the Google ADK CR implementation.

Usage:
    python -m adk.run --pr <pr_url> --repo <local_repo_path> [--post-comments]
"""

import asyncio
import json
import os

import click
from dotenv import load_dotenv

load_dotenv(override=True)

from shared.schemas import CRReport, Finding, Severity
from shared.git_client import post_inline_comment
from shared.model_config import set_langfuse_context, token_counter

_SEVERITY_RANK = {"critical": 2, "warning": 1, "info": 0}


def _parse_findings(raw) -> list[Finding]:
    if isinstance(raw, str):
        start = raw.find('{"findings"')
        if start == -1:
            start = raw.find('{ "findings"')
        if start == -1:
            return []
        end = raw.rfind("}")
        if end <= start:
            return []
        try:
            raw = json.loads(raw[start:end + 1])
        except Exception:
            return []
    if not isinstance(raw, dict):
        return []
    findings = []
    for f in raw.get("findings", []):
        try:
            findings.append(Finding(**f))
        except Exception:
            continue
    return findings


def _merge(pr_url: str, *raw_findings) -> CRReport:
    all_findings = []
    for raw in raw_findings:
        all_findings.extend(_parse_findings(raw))

    seen: dict[tuple, Finding] = {}
    for f in all_findings:
        key = (f.file, f.line_start, f.category)
        if key not in seen or _SEVERITY_RANK[f.severity] > _SEVERITY_RANK[seen[key].severity]:
            seen[key] = f
    findings = list(seen.values())

    if any(f.severity == Severity.CRITICAL for f in findings):
        verdict = "block"
    elif any(f.severity == Severity.WARNING for f in findings):
        verdict = "request_changes"
    else:
        verdict = "approve"

    n_crit = sum(1 for f in findings if f.severity == Severity.CRITICAL)
    n_warn = sum(1 for f in findings if f.severity == Severity.WARNING)
    summary = (
        "No issues found. The changes look safe to merge."
        if not findings else
        f"Found {len(findings)} issue(s): {n_crit} critical, {n_warn} warning. Review required before merging."
    )
    return CRReport(pr_url=pr_url, findings=findings, summary=summary, verdict=verdict)


def _dedup_findings(findings: list[Finding]) -> list[Finding]:
    seen: dict[tuple, Finding] = {}
    for f in findings:
        key = (f.file, f.line_start, f.category)
        if key not in seen or _SEVERITY_RANK[f.severity] > _SEVERITY_RANK[seen[key].severity]:
            seen[key] = f
    return list(seen.values())


async def _run_batch(pr: str, repo: str, diff_content: str) -> list[Finding]:
    from google.adk.runners import InMemoryRunner
    from google.genai import types
    from adk.agents.root_agent import root_agent

    runner = InMemoryRunner(agent=root_agent, app_name="cr_root")
    session = await runner.session_service.create_session(
        app_name="cr_root", user_id="ci"
    )
    message = types.Content(
        role="user",
        parts=[types.Part(text=(
            f"pr_url: {pr}\n"
            f"repo: {repo}\n\n"
            f"Diff:\n{diff_content}"
        ))],
    )
    async for _ in runner.run_async(
        user_id=session.user_id,
        session_id=session.id,
        new_message=message,
    ):
        pass

    state = (await runner.session_service.get_session(
        app_name="cr_root", user_id="ci", session_id=session.id
    )).state

    from adk.agents.gate import _parse_active_domains
    raw_domains = state.get("active_domains")
    active_domains = _parse_active_domains(raw_domains)
    if active_domains:
        click.echo(f"[planner] active_domains={active_domains} ({len(active_domains)}/6 reviewers active)", err=True)
    else:
        click.echo("[planner] WARNING: active_domains not found in state", err=True)

    report = _merge(
        pr,
        state.get("android_findings"),
        state.get("backend_findings"),
        state.get("security_findings"),
        state.get("concurrency_findings"),
        state.get("caching_findings"),
        state.get("db_schema_findings"),
    )
    return report.findings


async def _run_adk(pr: str, repo: str) -> CRReport:
    if pr == "LOCAL":
        diff_path = os.path.join(repo, "pr.diff")
        with open(diff_path) as f:
            diff_content = f.read()
        batches = [diff_content]
    else:
        import subprocess
        subprocess.run(["git", "pull"], cwd=repo, check=True, capture_output=True)
        from shared.git_client import get_pr_diff_batches
        _, batches = get_pr_diff_batches(pr)

    click.echo(f"[adk] {len(batches)} batch(es)", err=True)

    tasks = [_run_batch(pr, repo, batch) for batch in batches]
    results = await asyncio.gather(*tasks)

    all_findings: list[Finding] = []
    for findings in results:
        all_findings.extend(findings)

    findings = _dedup_findings(all_findings)

    if any(f.severity == Severity.CRITICAL for f in findings):
        verdict = "block"
    elif any(f.severity == Severity.WARNING for f in findings):
        verdict = "request_changes"
    else:
        verdict = "approve"

    n_crit = sum(1 for f in findings if f.severity == Severity.CRITICAL)
    n_warn = sum(1 for f in findings if f.severity == Severity.WARNING)
    summary = (
        "No issues found. The changes look safe to merge."
        if not findings else
        f"Found {len(findings)} issue(s): {n_crit} critical, {n_warn} warning. Review required before merging."
    )
    return CRReport(pr_url=pr, findings=findings, summary=summary, verdict=verdict)


@click.command()
@click.option("--pr", required=True, help="GitHub/GitLab PR URL")
@click.option("--repo", required=True, help="Local path to the checked-out repo")
@click.option("--post-comments", is_flag=True, default=False,
              help="Post findings as inline PR comments")
@click.option("--output", default="-", help="Write JSON report to file (- for stdout)")
def main(pr: str, repo: str, post_comments: bool, output: str):
    click.echo(f"[adk] Reviewing {pr} ...", err=True)
    set_langfuse_context("adk", pr)
    try:
        report = asyncio.run(asyncio.wait_for(_run_adk(pr, repo), timeout=600))
    except TimeoutError:
        click.echo("[adk] ERROR: timed out after 600s", err=True)
        raise SystemExit(1)

    report_json = report.model_dump_json(indent=2)
    if output == "-":
        print(report_json)
    else:
        with open(output, "w") as f:
            f.write(report_json)
        click.echo(f"[adk] Report written to {output}", err=True)

    if post_comments:
        _post_findings(report)

    verdict_color = {"approve": "green", "request_changes": "yellow", "block": "red"}
    color = verdict_color.get(report.verdict, "white")
    click.echo(
        click.style(f"[adk] verdict={report.verdict}  findings={len(report.findings)}", fg=color),
        err=True,
    )
    click.echo(
        f"[tokens] prompt={token_counter.prompt_tokens} completion={token_counter.completion_tokens} total={token_counter.total_tokens}",
        err=True,
    )


def _post_findings(report: CRReport) -> None:
    for f in report.findings:
        body = f"**[{f.severity.upper()}] {f.category}**\n\n{f.description}\n\n> {f.suggestion}"
        post_inline_comment(report.pr_url, f.file, f.line_start, body)
        click.echo(f"  commented on {f.file}:{f.line_start}", err=True)


if __name__ == "__main__":
    main()
