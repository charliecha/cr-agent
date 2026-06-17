"""
Git platform client — wraps GitHub (PyGithub) and GitLab (python-gitlab).
Returns plain dicts so both agent implementations stay decoupled from SDK types.
"""

import os
from dataclasses import dataclass


@dataclass
class PRInfo:
    url: str
    title: str
    description: str
    diff: str                    # full unified diff
    changed_files: list[str]
    base_sha: str
    head_sha: str
    repo_full_name: str          # "owner/repo"
    target_branch: str = ""      # branch to checkout before review


def get_pr_info(pr_url: str) -> PRInfo:
    """Detect platform from URL and fetch PR/MR info + diff."""
    if "github.com" in pr_url:
        return _github_pr(pr_url)
    return _gitlab_pr(pr_url)


def post_inline_comment(pr_url: str, file: str, line: int, body: str) -> None:
    """Post a single inline review comment on the given file+line."""
    if "github.com" in pr_url:
        _github_comment(pr_url, file, line, body)
    else:
        _gitlab_comment(pr_url, file, line, body)


# ── GitHub ────────────────────────────────────────────────────────────────────

def _parse_github_url(url: str) -> tuple[str, str, int]:
    """Return (owner, repo, pr_number) from a GitHub PR URL."""
    # https://github.com/owner/repo/pull/123
    parts = url.rstrip("/").split("/")
    pr_number = int(parts[-1])
    repo = parts[-3]
    owner = parts[-4]
    return owner, repo, pr_number


def _github_pr(pr_url: str) -> PRInfo:
    from github import Github

    token = os.environ["GITHUB_TOKEN"]
    gh = Github(token)
    owner, repo_name, pr_number = _parse_github_url(pr_url)
    repo = gh.get_repo(f"{owner}/{repo_name}")
    pr = repo.get_pull(pr_number)

    diff = _github_diff(pr_url, token)
    changed_files = [f.filename for f in pr.get_files()]

    return PRInfo(
        url=pr_url,
        title=pr.title,
        description=pr.body or "",
        diff=diff,
        changed_files=changed_files,
        base_sha=pr.base.sha,
        head_sha=pr.head.sha,
        repo_full_name=f"{owner}/{repo_name}",
    )


def _github_diff(pr_url: str, token: str) -> str:
    import httpx

    owner, repo_name, pr_number = _parse_github_url(pr_url)
    resp = httpx.get(
        f"https://api.github.com/repos/{owner}/{repo_name}/pulls/{pr_number}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.diff"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text


def _github_comment(pr_url: str, file: str, line: int, body: str) -> None:
    from github import Github

    token = os.environ["GITHUB_TOKEN"]
    gh = Github(token)
    owner, repo_name, pr_number = _parse_github_url(pr_url)
    repo = gh.get_repo(f"{owner}/{repo_name}")
    pr = repo.get_pull(pr_number)
    commit = repo.get_commit(pr.head.sha)
    pr.create_review_comment(body=body, commit=commit, path=file, line=line)


# ── GitLab ────────────────────────────────────────────────────────────────────

def _parse_gitlab_url(url: str) -> tuple[str, int]:
    """Return (project_path, mr_iid) from a GitLab MR URL."""
    # https://gitlab.com/owner/repo/-/merge_requests/42
    parts = url.rstrip("/").split("/")
    mr_iid = int(parts[-1])
    dash_idx = parts.index("-")
    project_path = "/".join(parts[3:dash_idx])
    return project_path, mr_iid


def _gitlab_pr(mr_url: str) -> PRInfo:
    info, _ = _gitlab_pr_with_batches(mr_url)
    return info


_SKIP_EXTS = {".xml", ".json", ".md", ".png", ".jpg", ".svg", ".webp",
              ".gradle", ".pro", ".txt", ".toml", ".kts", ".lock", ".gitignore"}
_MAX_FILE_LINES = 200
_BATCH_CHARS = 40_000


def _batch_changes(changes: list[dict]) -> list[str]:
    """Filter non-code files, truncate large hunks, split into batches by char budget."""
    filtered = []
    for c in changes:
        path = c.get("new_path", "")
        ext = os.path.splitext(path)[1].lower()
        if ext in _SKIP_EXTS or not c.get("diff"):
            continue
        d = c["diff"]
        lines = d.split("\n")
        if len(lines) > _MAX_FILE_LINES:
            d = "\n".join(lines[:_MAX_FILE_LINES]) + "\n... (truncated)"
        filtered.append((path, d))

    batches, current, current_len = [], [], 0
    for path, d in filtered:
        entry = f"--- {path}\n{d}"
        if current and current_len + len(entry) > _BATCH_CHARS:
            batches.append("\n".join(current))
            current, current_len = [], 0
        current.append(entry)
        current_len += len(entry)
    if current:
        batches.append("\n".join(current))
    return batches


def get_pr_diff_batches(pr_url: str) -> tuple[PRInfo, list[str]]:
    """Fetch PR info and return (PRInfo, list_of_diff_batches)."""
    if "github.com" in pr_url:
        info = get_pr_info(pr_url)
        return info, [info.diff]
    return _gitlab_pr_with_batches(pr_url)


def _gitlab_pr_with_batches(mr_url: str) -> tuple[PRInfo, list[str]]:
    import httpx
    from urllib.parse import quote

    token = os.environ["GITLAB_TOKEN"]
    base_url = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
    project_path, mr_iid = _parse_gitlab_url(mr_url)
    encoded = quote(project_path, safe="")
    headers = {"PRIVATE-TOKEN": token}

    mr = httpx.get(
        f"{base_url}/api/v4/projects/{encoded}/merge_requests/{mr_iid}",
        headers=headers, timeout=30,
    ).raise_for_status().json()

    changes_resp = httpx.get(
        f"{base_url}/api/v4/projects/{encoded}/merge_requests/{mr_iid}/changes",
        headers=headers, timeout=30,
    ).raise_for_status().json()

    batches = _batch_changes(changes_resp.get("changes", []))

    info = PRInfo(
        url=mr_url,
        title=mr["title"],
        description=mr.get("description") or "",
        diff="\n".join(batches),
        changed_files=[],
        base_sha=mr["diff_refs"]["base_sha"],
        head_sha=mr["diff_refs"]["head_sha"],
        repo_full_name=project_path,
        target_branch=mr.get("target_branch", ""),
    )
    return info, batches



def _gitlab_comment(mr_url: str, file: str, line: int, body: str) -> None:
    import gitlab

    token = os.environ["GITLAB_TOKEN"]
    base_url = os.environ.get("GITLAB_URL", "https://gitlab.com")
    gl = gitlab.Gitlab(base_url, private_token=token)
    project_path, mr_iid = _parse_gitlab_url(mr_url)
    project = gl.projects.get(project_path)
    mr = project.mergerequests.get(mr_iid)
    mr.discussions.create({
        "body": body,
        "position": {
            "position_type": "text",
            "new_path": file,
            "new_line": line,
        },
    })
