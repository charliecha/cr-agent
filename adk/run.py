"""
CLI entry point for the Google ADK CR implementation.

Usage:
    python -m adk.run --pr <pr_url> --repo <local_repo_path> [--post-comments]
"""

import asyncio
import json
import os

from adk.diff_parser import parse_diff

import click
from dotenv import load_dotenv

load_dotenv(override=True)

from shared.schemas import CRReport, Finding, Severity
from shared.git_client import post_inline_comment, upsert_mr_comment, post_inline_comment_gitlab, get_existing_inline_comments, PRInfo
from shared.model_config import set_langfuse_context, token_counter

_SEVERITY_RANK = {"critical": 2, "warning": 1, "info": 0}


def _is_test_file(path: str) -> bool:
    return (
        '/test/' in path or
        '/tests/' in path or
        '/androidTest/' in path or
        path.endswith('Test.kt') or
        path.endswith('Test.java') or
        path.endswith('Test.py') or
        path.endswith('_test.go')
    )


def _filter_test_files(diff_content: str) -> str:
    """Remove test file hunks from diff. Let CI handle test code validation."""
    lines = diff_content.split('\n')
    result = []
    skip_current_hunk = False

    for line in lines:
        # Standard git diff format: "diff --git a/path b/path"
        if line.startswith('diff --git'):
            skip_current_hunk = _is_test_file(line)
            if skip_current_hunk:
                continue
        # GitLab API diff format: "--- path"
        elif line.startswith('--- '):
            path = line[4:].strip()
            skip_current_hunk = _is_test_file(path)
            if skip_current_hunk:
                continue

        if not skip_current_hunk:
            result.append(line)

    return '\n'.join(result)


def _parse_findings(raw, domain: str = "") -> tuple[list[Finding], bool]:
    """Parse reviewer output. Returns (findings, ok) where ok=False means invalid output."""
    if raw is None:
        return [], True  # reviewer was gated/skipped — not an error
    if isinstance(raw, str):
        if raw.strip() == '{"findings": []}':
            return [], True  # gated output
        start = raw.find('{"findings"')
        if start == -1:
            start = raw.find('{ "findings"')
        if start == -1:
            if domain:
                click.echo(f"[adk] WARNING: {domain} reviewer output has no findings key — treating as invalid", err=True)
            return [], False
        end = raw.rfind("}")
        if end <= start:
            if domain:
                click.echo(f"[adk] WARNING: {domain} reviewer output malformed JSON — treating as invalid", err=True)
            return [], False
        try:
            raw = json.loads(raw[start:end + 1])
        except Exception:
            if domain:
                click.echo(f"[adk] WARNING: {domain} reviewer output JSON parse error — treating as invalid", err=True)
            return [], False
    if not isinstance(raw, dict):
        return [], False
    findings = []
    for f in raw.get("findings", []):
        try:
            findings.append(Finding(**f))
        except Exception:
            continue
    return findings, True


def _merge(pr_url: str, **domain_findings) -> CRReport:
    all_findings = []
    for domain, raw in domain_findings.items():
        findings, _ = _parse_findings(raw, domain=domain)
        all_findings.extend(findings)

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

    # Filter out test files - let CI handle test code validation
    filtered_diff = _filter_test_files(diff_content)
    if not filtered_diff.strip():
        click.echo("[adk] All changes are in test files, skipping review", err=True)
        return []

    diff_summary = json.dumps(parse_diff(pr, filtered_diff))

    runner = InMemoryRunner(agent=root_agent, app_name="cr_root")
    session = await runner.session_service.create_session(
        app_name="cr_root", user_id="ci",
        state={"diff_summary": diff_summary},
    )
    message = types.Content(
        role="user",
        parts=[types.Part(text=(
            f"pr_url: {pr}\n"
            f"repo: {repo}"
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

    from adk.agents.gate import _parse_active_domains, ALL_DOMAINS
    raw_domains = state.get("active_domains")
    active_domains = _parse_active_domains(raw_domains)
    if active_domains is None:
        click.echo("[planner] WARNING: active_domains invalid or missing — all reviewers ran as fallback", err=True)
        active_domains = ALL_DOMAINS
    elif active_domains:
        click.echo(f"[planner] active_domains={active_domains} ({len(active_domains)}/7 reviewers active)", err=True)
    else:
        click.echo("[planner] active_domains=[] (no reviewers active)", err=True)

    report = _merge(
        pr,
        android=state.get("android_findings"),
        backend=state.get("backend_findings"),
        security=state.get("security_findings"),
        concurrency=state.get("concurrency_findings"),
        caching=state.get("caching_findings"),
        db_schema=state.get("db_schema_findings"),
        frontend=state.get("frontend_findings"),
    )
    return report.findings


async def _run_adk(pr: str, repo: str) -> tuple[CRReport, PRInfo]:
    info = PRInfo(url=pr, title="", description="", diff="", changed_files=[],
                  base_sha="", head_sha="", repo_full_name="")
    if pr == "LOCAL":
        diff_path = os.path.join(repo, "pr.diff")
        with open(diff_path) as f:
            diff_content = f.read()
        batches = [diff_content]
    else:
        import subprocess
        from shared.git_client import get_pr_diff_batches
        info, batches = get_pr_diff_batches(pr)
        if info.target_branch:
            click.echo(f"[adk] Checking out target branch: {info.target_branch}", err=True)
            subprocess.run(["git", "fetch", "origin"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "checkout", info.target_branch], cwd=repo, check=True, capture_output=True)
        else:
            subprocess.run(["git", "pull"], cwd=repo, check=True, capture_output=True)

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
    return CRReport(pr_url=pr, findings=findings, summary=summary, verdict=verdict), info


def _resolve_repo(pr: str, repo: str | None) -> str:
    """Resolve repo path: use explicit path, or auto-detect from REPOS_DIR."""
    if repo:
        return repo
    repos_dir = os.environ.get("REPOS_DIR", "")
    if not repos_dir:
        raise click.UsageError("--repo not specified and REPOS_DIR not set in .env.")

    # Extract project name from PR URL, e.g. ".../latincore/-/merge_requests/1" → "latincore"
    parts = pr.rstrip("/").split("/")
    try:
        dash_idx = parts.index("-")
        project_name = parts[dash_idx - 1]
    except (ValueError, IndexError):
        raise click.UsageError("Cannot infer project name from PR URL. Please specify --repo.")

    candidate = os.path.join(repos_dir, project_name)
    if os.path.isdir(candidate):
        click.echo(f"[adk] Auto-detected repo: {candidate}", err=True)
        return os.path.abspath(candidate)

    raise click.UsageError(
        f"No repo found at {candidate}. "
        f"Clone it to $REPOS_DIR/{project_name}/ or pass --repo explicitly."
    )


@click.command()
@click.option("--pr", required=True, help="GitHub/GitLab PR URL")
@click.option("--repo", default=None, help="Local path to checked-out repo (auto-detected from repos/ if omitted)")
@click.option("--post-comments", is_flag=True, default=False,
              help="Post findings as inline PR comments")
@click.option("--output", default="-", help="Write JSON report to file (- for stdout)")
def main(pr: str, repo: str | None, post_comments: bool, output: str):
    repo = _resolve_repo(pr, repo)
    click.echo(f"[adk] Reviewing {pr} ...", err=True)
    set_langfuse_context("adk", pr)
    try:
        report, info = asyncio.run(asyncio.wait_for(_run_adk(pr, repo), timeout=600))
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
        _post_findings(report, info)

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


def _post_findings(report: CRReport, info: PRInfo) -> None:
    # 1. 整体评论（upsert，保持不变）
    upsert_mr_comment(report.pr_url, _format_mr_comment(report))

    # 2. inline comments（发前查已有，跳过重复）
    existing = get_existing_inline_comments(report.pr_url)
    posted = skipped = 0
    for f in report.findings:
        if f.file in existing:
            skipped += 1
            continue
        sev = f.severity.value
        icon = _SEV_ICON.get(sev, "")
        comment = (
            f"<!-- cr-agent-inline -->\n"
            f"{icon} **[{sev}] {f.category}**\n\n"
            f"{f.description}\n\n"
            f"**🔧 Fix:** {f.suggestion}"
        )
        try:
            ok = post_inline_comment_gitlab(report.pr_url, f.file, f.line_start, comment, info)
            if ok:
                posted += 1
        except Exception as e:
            click.echo(f"[adk] inline comment failed {f.file}:{f.line_start}: {e}", err=True)

    click.echo(
        f"[adk] Posted/updated MR comment + {posted} new inline comments ({skipped} skipped, already exists)",
        err=True,
    )


_SEV_ICON = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
_SEV_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _format_mr_comment(report: CRReport) -> str:
    verdict_icon = {"approve": "✅", "request_changes": "⚠️", "block": "🚫"}.get(report.verdict, "")
    lines = [
        f"## {verdict_icon} CR Agent Review",
        "",
        f"**Verdict:** `{report.verdict}`  **Summary:** {report.summary}",
    ]
    if report.findings:
        sorted_findings = sorted(report.findings, key=lambda f: _SEV_ORDER.get(f.severity.value, 9))
        lines += [
            "",
            "| File | Line | Severity | Category | Description | Suggestion |",
            "|------|------|----------|----------|-------------|------------|",
        ]
        for f in sorted_findings:
            sev = f.severity.value
            icon = _SEV_ICON.get(sev, "")
            desc = f.description.replace("|", "\\|")[:120]
            sugg = f.suggestion.replace("|", "\\|")[:80]
            lines.append(
                f"| `{f.file}` | {f.line_start} | {icon} {sev} | {f.category} | {desc} | {sugg} |"
            )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
