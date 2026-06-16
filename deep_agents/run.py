"""
CLI entry point for the Deep Agents CR implementation.

Usage:
    python -m deep_agents.run --pr <pr_url> --repo <local_repo_path> [--post-comments]
"""

import json
import sys
import click
from dotenv import load_dotenv

load_dotenv()

from shared.schemas import CRReport
from shared.git_client import post_inline_comment
from shared.model_config import set_langfuse_context, token_counter


@click.command()
@click.option("--pr", required=True, help="GitHub/GitLab PR URL")
@click.option("--repo", required=True, help="Local path to the checked-out repo")
@click.option("--post-comments", is_flag=True, default=False,
              help="Post findings as inline PR comments")
@click.option("--output", default="-", help="Write JSON report to file (- for stdout)")
def main(pr: str, repo: str, post_comments: bool, output: str):
    from deep_agents.agent import run_review

    click.echo(f"[deep_agents] Reviewing {pr} ...", err=True)
    set_langfuse_context("deep_agents", pr)
    report: CRReport = run_review(pr_url=pr, repo_root=repo)

    report_json = report.model_dump_json(indent=2)

    if output == "-":
        print(report_json)
    else:
        with open(output, "w") as f:
            f.write(report_json)
        click.echo(f"[deep_agents] Report written to {output}", err=True)

    if post_comments:
        _post_findings(report)

    verdict_color = {"approve": "green", "request_changes": "yellow", "block": "red"}
    color = verdict_color.get(report.verdict, "white")
    click.echo(
        click.style(f"[deep_agents] verdict={report.verdict}  findings={len(report.findings)}", fg=color),
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
