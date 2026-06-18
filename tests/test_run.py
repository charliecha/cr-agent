"""Tests for adk/run.py — helpers and mock integration coverage."""

import json
import pytest

from shared.schemas import Severity
from shared.git_client import PRInfo
import adk.run as run_module
from adk.run import _filter_test_files, _parse_findings, _merge, _resolve_repo


# ── _filter_test_files ────────────────────────────────────────────────────────

def test_keeps_non_test_file():
    diff = "--- src/main/Foo.kt\n@@ -1 +1 @@\n+x\n"
    assert _filter_test_files(diff) == diff


def test_removes_test_suffix_kt():
    diff = "--- src/FooTest.kt\n@@ -1 +1 @@\n+x\n--- src/Bar.kt\n@@ -1 +1 @@\n+y\n"
    result = _filter_test_files(diff)
    assert "FooTest.kt" not in result
    assert "Bar.kt" in result


def test_removes_test_directory():
    diff = "--- src/test/java/Foo.kt\n@@ -1 +1 @@\n+x\n--- src/main/Bar.kt\n@@ -1 +1 @@\n+y\n"
    result = _filter_test_files(diff)
    assert "src/test/java/Foo.kt" not in result
    assert "src/main/Bar.kt" in result


def test_removes_android_test_directory():
    diff = "--- src/androidTest/Foo.kt\n@@ -1 +1 @@\n+x\n"
    result = _filter_test_files(diff)
    assert "androidTest" not in result


def test_removes_go_test_file():
    diff = "--- pkg/foo_test.go\n@@ -1 +1 @@\n+x\n--- pkg/foo.go\n@@ -1 +1 @@\n+y\n"
    result = _filter_test_files(diff)
    assert "foo_test.go" not in result
    assert "foo.go" in result


def test_git_diff_format_skips_test():
    diff = "diff --git a/src/FooTest.java b/src/FooTest.java\n--- a/src/FooTest.java\n+++ b/src/FooTest.java\n@@ -1 +1 @@\n+x\n"
    result = _filter_test_files(diff)
    assert "FooTest.java" not in result


def test_empty_diff_unchanged():
    assert _filter_test_files("") == ""


# ── _parse_findings ───────────────────────────────────────────────────────────

_VALID = {
    "file": "Foo.kt", "line_start": 10, "line_end": 10,
    "severity": "critical", "category": "null_deref",
    "description": "desc", "suggestion": "fix",
}


def test_parse_valid():
    raw = json.dumps({"findings": [_VALID]})
    findings, ok = _parse_findings(raw)
    assert ok is True
    assert len(findings) == 1
    assert findings[0].severity == Severity.CRITICAL


def test_parse_gated_empty():
    findings, ok = _parse_findings('{"findings": []}')
    assert ok is True
    assert findings == []


def test_parse_none_is_ok():
    findings, ok = _parse_findings(None)
    assert ok is True
    assert findings == []


def test_parse_invalid_json():
    findings, ok = _parse_findings("not json")
    assert ok is False
    assert findings == []


def test_parse_missing_findings_key():
    findings, ok = _parse_findings('{"result": []}')
    assert ok is False


def test_parse_findings_with_surrounding_text():
    # Model sometimes wraps JSON in prose
    raw = 'Here are the issues:\n{"findings": [' + json.dumps(_VALID) + ']}\nDone.'
    findings, ok = _parse_findings(raw)
    assert ok is True
    assert len(findings) == 1


# ── _merge ────────────────────────────────────────────────────────────────────

def _f(**kw):
    base = dict(_VALID)
    base.update(kw)
    return json.dumps({"findings": [base]})


def test_merge_dedup_keeps_higher_severity():
    report = _merge("http://mr/1", android=_f(severity="warning"), backend=_f(severity="critical"))
    assert len(report.findings) == 1
    assert report.findings[0].severity == Severity.CRITICAL


def test_merge_dedup_same_severity_keeps_first():
    report = _merge("http://mr/1", android=_f(description="first"), backend=_f(description="second"))
    assert len(report.findings) == 1


def test_merge_different_files_not_deduped():
    report = _merge("http://mr/1", android=_f(file="A.kt"), backend=_f(file="B.kt"))
    assert len(report.findings) == 2


def test_merge_verdict_block():
    assert _merge("http://mr/1", backend=_f(severity="critical")).verdict == "block"


def test_merge_verdict_request_changes():
    assert _merge("http://mr/1", backend=_f(severity="warning")).verdict == "request_changes"


def test_merge_verdict_approve_on_empty():
    report = _merge("http://mr/1", backend=None)
    assert report.verdict == "approve"
    assert report.findings == []


# ── _resolve_repo ─────────────────────────────────────────────────────────────

def test_resolve_explicit_repo(tmp_path):
    assert _resolve_repo("http://mr/1", str(tmp_path)) == str(tmp_path)


def test_resolve_auto_detect(tmp_path, monkeypatch):
    repo_dir = tmp_path / "latincore"
    repo_dir.mkdir()
    monkeypatch.setenv("REPOS_DIR", str(tmp_path))
    result = _resolve_repo("https://gitlab.example.com/group/latincore/-/merge_requests/1", None)
    assert result == str(repo_dir.resolve())


def test_resolve_missing_repos_dir_raises(monkeypatch):
    monkeypatch.delenv("REPOS_DIR", raising=False)
    import click
    with pytest.raises(click.UsageError, match="REPOS_DIR"):
        _resolve_repo("http://mr/1", None)


def test_resolve_repo_not_found_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("REPOS_DIR", str(tmp_path))
    import click
    with pytest.raises(click.UsageError, match="No repo found"):
        _resolve_repo("https://gitlab.example.com/group/myproject/-/merge_requests/1", None)


def test_resolve_unparseable_url_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("REPOS_DIR", str(tmp_path))
    import click
    with pytest.raises(click.UsageError):
        _resolve_repo("http://no-dash-segment/1", None)


# ── _run_batch / _run_adk mock integration ────────────────────────────────────


class _FakeSession:
    user_id = "ci"
    id = "session-1"


class _FakeStoredSession:
    def __init__(self, state):
        self.state = state


def _make_fake_runner(state):
    class _FakeSessionService:
        def __init__(self):
            self.created_state = None

        async def create_session(self, app_name, user_id, state):
            self.created_state = state
            return _FakeSession()

        async def get_session(self, app_name, user_id, session_id):
            return _FakeStoredSession(state)

    class _FakeRunner:
        def __init__(self, agent, app_name):
            self.agent = agent
            self.app_name = app_name
            self.session_service = _FakeSessionService()

        async def run_async(self, user_id, session_id, new_message):
            yield {"ok": True}

    return _FakeRunner


@pytest.mark.asyncio
async def test_run_batch_skips_test_only_diff_without_runner(monkeypatch):
    class _ExplodingRunner:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Runner should not be created for test-only diffs")

    monkeypatch.setattr("google.adk.runners.InMemoryRunner", _ExplodingRunner)
    findings = await run_module._run_batch(
        "http://mr/1",
        "/repo",
        "--- src/test/java/FooTest.kt\n@@ -1 +1 @@\n+x\n",
    )
    assert findings == []


@pytest.mark.asyncio
async def test_run_batch_uses_registry_outputs_and_fallbacks_on_empty_domains(monkeypatch, capsys):
    warn = _f(severity="warning", description="warn")
    crit = _f(severity="critical", description="crit")
    state = {
        "active_domains": "[]",
        "android_findings": warn,
        "backend_findings": crit,
    }

    monkeypatch.setattr("google.adk.runners.InMemoryRunner", _make_fake_runner(state))
    findings = await run_module._run_batch(
        "http://mr/1",
        "/repo",
        "--- src/Foo.kt\n+++ src/Foo.kt\n@@ -1 +1 @@\n+x\n",
    )

    assert len(findings) == 1
    assert findings[0].severity == Severity.CRITICAL
    captured = capsys.readouterr()
    assert "all reviewers ran as fallback" in captured.err


@pytest.mark.asyncio
async def test_run_adk_local_reads_pr_diff_and_aggregates(monkeypatch, tmp_path):
    repo = tmp_path
    (repo / "pr.diff").write_text("--- src/Foo.kt\n+++ src/Foo.kt\n@@ -1 +1 @@\n+x\n")

    async def fake_run_batch(pr, repo_path, batch):
        assert pr == "LOCAL"
        assert repo_path == str(repo)
        assert "src/Foo.kt" in batch
        return [_parse_findings(_f(severity="warning"))[0][0]]

    monkeypatch.setattr(run_module, "_run_batch", fake_run_batch)
    report, info = await run_module._run_adk("LOCAL", str(repo))

    assert info.url == "LOCAL"
    assert report.verdict == "request_changes"
    assert len(report.findings) == 1


@pytest.mark.asyncio
async def test_run_adk_remote_checks_out_target_branch(monkeypatch, tmp_path):
    commands = []

    def fake_subprocess_run(cmd, cwd, check, capture_output):
        commands.append((cmd, cwd, check, capture_output))

    async def fake_run_batch(pr, repo_path, batch):
        assert pr == "http://mr/1"
        assert repo_path == str(tmp_path)
        return []

    info = PRInfo(
        url="http://mr/1",
        title="Title",
        description="Desc",
        diff="",
        changed_files=[],
        base_sha="base",
        head_sha="head",
        repo_full_name="group/project",
        target_branch="main",
    )

    monkeypatch.setattr(run_module, "_run_batch", fake_run_batch)
    monkeypatch.setattr("shared.git_client.get_pr_diff_batches", lambda pr: (info, ["batch-1"]))
    monkeypatch.setattr("subprocess.run", fake_subprocess_run)

    report, returned_info = await run_module._run_adk("http://mr/1", str(tmp_path))

    assert returned_info is info
    assert report.verdict == "approve"
    assert commands == [
        (["git", "fetch", "origin"], str(tmp_path), True, True),
        (["git", "checkout", "main"], str(tmp_path), True, True),
    ]


@pytest.mark.asyncio
async def test_run_adk_remote_pulls_when_target_branch_missing(monkeypatch, tmp_path):
    commands = []

    def fake_subprocess_run(cmd, cwd, check, capture_output):
        commands.append((cmd, cwd, check, capture_output))

    async def fake_run_batch(pr, repo_path, batch):
        return []

    info = PRInfo(
        url="http://mr/2",
        title="Title",
        description="Desc",
        diff="",
        changed_files=[],
        base_sha="base",
        head_sha="head",
        repo_full_name="group/project",
        target_branch="",
    )

    monkeypatch.setattr(run_module, "_run_batch", fake_run_batch)
    monkeypatch.setattr("shared.git_client.get_pr_diff_batches", lambda pr: (info, ["batch-1"]))
    monkeypatch.setattr("subprocess.run", fake_subprocess_run)

    await run_module._run_adk("http://mr/2", str(tmp_path))

    assert commands == [
        (["git", "pull"], str(tmp_path), True, True),
    ]
