import json
import pytest

from shared.schemas import Finding, Severity
from adk.diff_parser import parse_diff
from adk.agents.gate import _parse_active_domains, ALL_DOMAINS
from adk.run import _parse_findings, _merge


# ── parse_diff ────────────────────────────────────────────────────────────────

def test_parse_diff_basic():
    diff = """\
--- src/main/java/Foo.kt
+++ src/main/java/Foo.kt
@@ -1,3 +1,4 @@
+import android.util.Log
 class Foo
"""
    result = parse_diff("http://example.com/mr/1", diff)
    assert result["pr_url"] == "http://example.com/mr/1"
    assert len(result["hunks"]) == 1
    assert result["hunks"][0]["file"] == "src/main/java/Foo.kt"
    assert result["hunks"][0]["lang"] == "kotlin"


def test_parse_diff_multiple_files():
    diff = """\
--- a.py
+++ a.py
@@ -1 +1 @@
-old
+new
--- b.ts
+++ b.ts
@@ -1 +1 @@
-x
+y
"""
    result = parse_diff("http://mr/1", diff)
    assert len(result["hunks"]) == 2
    assert result["hunks"][0]["file"] == "a.py"
    assert result["hunks"][0]["lang"] == "python"
    assert result["hunks"][1]["file"] == "b.ts"
    assert result["hunks"][1]["lang"] == "typescript"


def test_parse_diff_skips_dev_null():
    diff = """\
--- /dev/null
+++ src/New.kt
@@ -0,0 +1,3 @@
+class New
--- src/Existing.kt
+++ src/Existing.kt
@@ -1 +1 @@
-old
+new
"""
    result = parse_diff("http://mr/1", diff)
    # /dev/null line should not start a hunk; only Existing.kt
    assert len(result["hunks"]) == 1
    assert result["hunks"][0]["file"] == "src/Existing.kt"


def test_parse_diff_unknown_extension():
    diff = "--- config.yaml\n+++ config.yaml\n@@ -1 +1 @@\n-a\n+b\n"
    result = parse_diff("http://mr/1", diff)
    assert result["hunks"][0]["lang"] == "other"


# ── _parse_active_domains ─────────────────────────────────────────────────────

def test_parse_active_domains_list():
    assert _parse_active_domains(["android", "backend"]) == ["android", "backend"]


def test_parse_active_domains_json_list():
    assert _parse_active_domains('["android", "backend"]') == ["android", "backend"]


def test_parse_active_domains_json_dict():
    raw = json.dumps({"active_domains": ["security"]})
    assert _parse_active_domains(raw) == ["security"]


def test_parse_active_domains_invalid_returns_none():
    assert _parse_active_domains("not json") is None
    assert _parse_active_domains(None) is None
    assert _parse_active_domains(42) is None
    assert _parse_active_domains("{}") is None  # dict with no active_domains key → None


def test_parse_active_domains_empty_list():
    assert _parse_active_domains("[]") == []


# ── _parse_findings ───────────────────────────────────────────────────────────

_VALID_FINDING = {
    "file": "Foo.kt",
    "line_start": 10,
    "line_end": 10,
    "severity": "critical",
    "category": "null_deref",
    "description": "desc",
    "suggestion": "fix",
}


def test_parse_findings_valid():
    raw = json.dumps({"findings": [_VALID_FINDING]})
    findings, ok = _parse_findings(raw)
    assert ok is True
    assert len(findings) == 1
    assert findings[0].severity == Severity.CRITICAL


def test_parse_findings_empty_gated_output():
    findings, ok = _parse_findings('{"findings": []}')
    assert ok is True
    assert findings == []


def test_parse_findings_none_input():
    findings, ok = _parse_findings(None)
    assert ok is True
    assert findings == []


def test_parse_findings_invalid_json():
    findings, ok = _parse_findings("not json at all")
    assert ok is False
    assert findings == []


def test_parse_findings_missing_findings_key():
    findings, ok = _parse_findings('{"result": []}')
    assert ok is False
    assert findings == []


# ── _merge dedup ──────────────────────────────────────────────────────────────

def _finding(**kwargs) -> dict:
    base = dict(_VALID_FINDING)
    base.update(kwargs)
    return base


def test_merge_dedup_keeps_higher_severity():
    warn = json.dumps({"findings": [_finding(severity="warning")]})
    crit = json.dumps({"findings": [_finding(severity="critical")]})
    report = _merge("http://mr/1", android=warn, backend=crit)
    assert len(report.findings) == 1
    assert report.findings[0].severity == Severity.CRITICAL


def test_merge_dedup_same_severity_keeps_first():
    a = json.dumps({"findings": [_finding(description="first")]})
    b = json.dumps({"findings": [_finding(description="second")]})
    report = _merge("http://mr/1", android=a, backend=b)
    assert len(report.findings) == 1


def test_merge_different_files_not_deduped():
    a = json.dumps({"findings": [_finding(file="A.kt")]})
    b = json.dumps({"findings": [_finding(file="B.kt")]})
    report = _merge("http://mr/1", android=a, backend=b)
    assert len(report.findings) == 2


def test_merge_verdict_block_on_critical():
    raw = json.dumps({"findings": [_finding(severity="critical")]})
    report = _merge("http://mr/1", backend=raw)
    assert report.verdict == "block"


def test_merge_verdict_request_changes_on_warning():
    raw = json.dumps({"findings": [_finding(severity="warning")]})
    report = _merge("http://mr/1", backend=raw)
    assert report.verdict == "request_changes"


def test_merge_verdict_approve_on_empty():
    report = _merge("http://mr/1", backend=None)
    assert report.verdict == "approve"
    assert report.findings == []
