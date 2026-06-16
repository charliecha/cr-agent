"""
CLI entry point for the Google ADK CR implementation.

Usage:
    python -m adk.run --pr <pr_url> --repo <local_repo_path> [--post-comments]
"""

import asyncio
import re
import click
from dotenv import load_dotenv

load_dotenv()

from shared.schemas import CRReport
from shared.git_client import post_inline_comment


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

    # check session state for structured output (output_key="cr_report")
    session_state = (await runner.session_service.get_session(
        app_name="cr_root", user_id="ci", session_id=session.id
    )).state
    if "cr_report" in session_state:
        raw = session_state["cr_report"]
        return CRReport.model_validate(raw) if isinstance(raw, dict) else CRReport.model_validate_json(raw)

    # fall back to parsing JSON from final text reply
    m = re.search(r"\{.*\}", final_text, flags=re.DOTALL)
    if not m:
        raise ValueError(f"No CRReport JSON found in ADK output:\n{final_text[:500]}")
    return CRReport.model_validate_json(m.group())


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
