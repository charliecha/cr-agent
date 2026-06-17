"""
Git platform client — wraps GitHub (PyGithub) and GitLab (python-gitlab).
Returns plain dicts so both agent implementations stay decoupled from SDK types.
"""

import os
import re
from dataclasses import dataclass, field


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
    start_sha: str = ""          # diff_refs.start_sha, required for inline comments
    diff_new_lines: dict = field(default_factory=dict)  # {filepath: set[int]}


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


def _parse_hunk_new_lines(diff_text: str) -> set:
    """Return set of new-file line numbers that appear as added lines in the diff."""
    result = set()
    new_line = 0
    for line in diff_text.split('\n'):
        if line.startswith('@@'):
            m = re.search(r'\+(\d+)', line)
            if m:
                new_line = int(m.group(1)) - 1
        elif line.startswith('+++'):
            pass
        elif line.startswith('+'):
            new_line += 1
            result.add(new_line)
        elif line.startswith('-'):
            pass
        else:
            new_line += 1
    return result


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

    diff_new_lines = {
        c["new_path"]: _parse_hunk_new_lines(c["diff"])
        for c in changes_resp.get("changes", [])
        if c.get("diff")
    }

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
        start_sha=mr["diff_refs"].get("start_sha", ""),
        diff_new_lines=diff_new_lines,
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


_CR_AGENT_MARKER = "<!-- cr-agent -->"


def upsert_mr_comment(mr_url: str, body: str) -> None:
    """Post or update the cr-agent summary comment on a GitLab MR.

    Uses a hidden HTML marker to find the previous comment and edit it,
    so re-running review never creates duplicate notes.
    """
    import httpx
    from urllib.parse import quote

    token = os.environ["GITLAB_TOKEN"]
    base_url = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
    project_path, mr_iid = _parse_gitlab_url(mr_url)
    encoded = quote(project_path, safe="")
    headers = {"PRIVATE-TOKEN": token}
    marked_body = f"{_CR_AGENT_MARKER}\n{body}"

    # Search existing notes for our marker (paginate up to 100)
    notes = httpx.get(
        f"{base_url}/api/v4/projects/{encoded}/merge_requests/{mr_iid}/notes",
        headers=headers,
        params={"per_page": 100, "sort": "desc"},
        timeout=30,
    ).raise_for_status().json()

    existing_id = None
    for note in notes:
        if _CR_AGENT_MARKER in note.get("body", ""):
            existing_id = note["id"]
            break

    if existing_id:
        httpx.put(
            f"{base_url}/api/v4/projects/{encoded}/merge_requests/{mr_iid}/notes/{existing_id}",
            headers=headers,
            json={"body": marked_body},
            timeout=30,
        ).raise_for_status()
    else:
        httpx.post(
            f"{base_url}/api/v4/projects/{encoded}/merge_requests/{mr_iid}/notes",
            headers=headers,
            json={"body": marked_body},
            timeout=30,
        ).raise_for_status()


def post_inline_comment_gitlab(mr_url: str, file: str, line: int, body: str, info: "PRInfo") -> bool:
    """Post an inline comment on a GitLab MR diff line.

    Returns True if posted, False if the line is not in the diff (skipped gracefully).
    Raises on API errors.
    """
    if line not in info.diff_new_lines.get(file, set()):
        return False

    import httpx
    from urllib.parse import quote

    token = os.environ["GITLAB_TOKEN"]
    base_url = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
    project_path, mr_iid = _parse_gitlab_url(mr_url)
    encoded = quote(project_path, safe="")

    httpx.post(
        f"{base_url}/api/v4/projects/{encoded}/merge_requests/{mr_iid}/discussions",
        headers={"PRIVATE-TOKEN": token},
        json={
            "body": body,
            "position": {
                "position_type": "text",
                "base_sha": info.base_sha,
                "head_sha": info.head_sha,
                "start_sha": info.start_sha,
                "new_path": file,
                "old_path": file,
                "new_line": line,
            },
        },
        timeout=30,
    ).raise_for_status()
    return True


def get_existing_inline_comments(mr_url: str) -> set:
    """Return set of file paths that already have a cr-agent inline comment on this MR."""
    import httpx
    from urllib.parse import quote

    token = os.environ["GITLAB_TOKEN"]
    base_url = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
    project_path, mr_iid = _parse_gitlab_url(mr_url)
    encoded = quote(project_path, safe="")
    headers = {"PRIVATE-TOKEN": token}

    existing = set()
    page = 1
    while True:
        discussions = httpx.get(
            f"{base_url}/api/v4/projects/{encoded}/merge_requests/{mr_iid}/discussions",
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=30,
        ).raise_for_status().json()
        if not discussions:
            break
        for d in discussions:
            for note in d.get("notes", []):
                if _CR_AGENT_MARKER not in note.get("body", ""):
                    continue
                pos = note.get("position") or {}
                f = pos.get("new_path")
                if f:
                    existing.add(f)
        page += 1
    return existing
