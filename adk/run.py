"""
CLI entry point for the Google ADK CR implementation.

Usage:
    python -m adk.run --pr <pr_url> --repo <local_repo_path> [--post-comments]
"""

import asyncio
import json
import re
import click
from dotenv import load_dotenv

load_dotenv()

from shared.schemas import CRReport, Finding, Severity
from shared.git_client import post_inline_comment

_SEVERITY_RANK = {"critical": 2, "warning": 1, "info": 0}


def _parse_findings(raw) -> list[Finding]:
    if isinstance(raw, str):
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end <= start:
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


def _merge(pr_url: str, android_raw, backend_raw) -> CRReport:
    all_findings = _parse_findings(android_raw) + _parse_findings(backend_raw)

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


async def _run_adk(pr: str, repo: str) -> CRReport:
    from google.adk.runners import InMemoryRunner
    from google.genai import types
    from shared.tools import git_diff
    from adk.agents.root_agent import root_agent

    diff_content = git_diff(pr)

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

    final_text = ""
    async for event in runner.run_async(
        user_id=session.user_id,
        session_id=session.id,
        new_message=message,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    final_text = part.text

    session_state = (await runner.session_service.get_session(
        app_name="cr_root", user_id="ci", session_id=session.id
    )).state

    return _merge(pr, session_state.get("android_findings"), session_state.get("backend_findings"))


@click.command()
@click.option("--pr", required=True, help="GitHub/GitLab PR URL")
@click.option("--repo", required=True, help="Local path to the checked-out repo")
@click.option("--post-comments", is_flag=True, default=False,
              help="Post findings as inline PR comments")
@click.option("--output", default="-", help="Write JSON report to file (- for stdout)")
def main(pr: str, repo: str, post_comments: bool, output: str):
    click.echo(f"[adk] Reviewing {pr} ...", err=True)

    try:
        report = asyncio.run(asyncio.wait_for(_run_adk(pr, repo), timeout=120))
    except TimeoutError:
        click.echo("[adk] ERROR: timed out after 120s", err=True)
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


def _post_findings(report: CRReport) -> None:
    for f in report.findings:
        body = f"**[{f.severity.upper()}] {f.category}**\n\n{f.description}\n\n> {f.suggestion}"
        post_inline_comment(report.pr_url, f.file, f.line_start, body)
        click.echo(f"  commented on {f.file}:{f.line_start}", err=True)


if __name__ == "__main__":
    main()
