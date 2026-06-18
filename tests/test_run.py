"""Tests for adk/run.py — _filter_test_files, _parse_findings, _merge, _resolve_repo."""

import json
import os
import pytest

from shared.schemas import Severity
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
