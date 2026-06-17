"""
Tools shared by both agent implementations.
Each tool is a plain Python function; framework-specific wrappers live in
deep_agents/ and adk/ respectively.
"""

import os
import subprocess
from pathlib import Path


def git_diff(pr_url: str) -> str:
    """
    Fetch the unified diff for a PR/MR URL, or read a local .diff file for testing.
    """
    if pr_url.startswith("http"):
        from shared.git_client import get_pr_info
        return get_pr_info(pr_url).diff
    p = Path(pr_url)
    if p.exists() and p.suffix == ".diff":
        return p.read_text()
    result = subprocess.run(
        ["git", "diff", pr_url],
        capture_output=True, text=True, cwd=Path.cwd()
    )
    return result.stdout


def file_read(repo_root: str, filepath: str, start_line: int = 1, end_line: int = 0) -> str:
    """
    Read a file from the local clone of the repo being reviewed.
    start_line/end_line: 1-indexed, inclusive. end_line=0 means read to EOF.
    """
    import sys
    print(f"[file_read] repo_root={repo_root} filepath={filepath}", file=sys.stderr)
    path = Path(repo_root) / filepath
    if not path.exists():
        return f"ERROR: {filepath} not found in {repo_root}"
    lines = path.read_text(errors="replace").splitlines()
    sl = max(0, start_line - 1)
    el = len(lines) if end_line == 0 else end_line
    selected = lines[sl:el]
    return "\n".join(f"{sl + i + 1}: {line}" for i, line in enumerate(selected))


def grep(repo_root: str, pattern: str, file_glob: str = "**/*") -> str:
    """
    Grep for a pattern across the repo. Returns matching lines with file:line context.
    Capped at 100 lines to avoid flooding context.
    """
    import sys
    print(f"[grep] repo_root={repo_root} pattern={pattern}", file=sys.stderr)
    result = subprocess.run(
        ["grep", "-rn", "--include", _glob_to_include(file_glob), pattern, "."],
        capture_output=True, text=True, cwd=repo_root
    )
    output = result.stdout.strip()
    if not output:
        return f"No matches for '{pattern}'"
    lines = output.splitlines()
    if len(lines) > 100:
        return "\n".join(lines[:100]) + f"\n... ({len(lines) - 100} more lines truncated)"
    return output


def _glob_to_include(glob: str) -> str:
    return Path(glob).name if "**" in glob else glob
