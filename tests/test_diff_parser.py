"""Tests for adk/diff_parser.py"""

from adk.diff_parser import parse_diff


def test_basic_modified_file():
    diff = "--- src/Foo.kt\n+++ src/Foo.kt\n@@ -1,3 +1,4 @@\n+import X\n class Foo\n"
    result = parse_diff("http://mr/1", diff)
    assert result["pr_url"] == "http://mr/1"
    assert len(result["hunks"]) == 1
    assert result["hunks"][0]["file"] == "src/Foo.kt"
    assert result["hunks"][0]["lang"] == "kotlin"


def test_multiple_files():
    diff = "--- a.py\n+++ a.py\n@@ -1 +1 @@\n-old\n+new\n--- b.ts\n+++ b.ts\n@@ -1 +1 @@\n-x\n+y\n"
    result = parse_diff("http://mr/1", diff)
    assert len(result["hunks"]) == 2
    assert result["hunks"][0]["file"] == "a.py"
    assert result["hunks"][0]["lang"] == "python"
    assert result["hunks"][1]["file"] == "b.ts"
    assert result["hunks"][1]["lang"] == "typescript"


def test_batch_format_new_file():
    # _batch_changes in git_client.py produces "--- {new_path}\n{hunk}" for ALL files,
    # including new ones — no /dev/null, just the real path.
    diff = "--- src/New.kt\n@@ -0,0 +1,3 @@\n+package foo\n+class New\n"
    result = parse_diff("http://mr/1", diff)
    assert len(result["hunks"]) == 1
    assert result["hunks"][0]["file"] == "src/New.kt"
    assert result["hunks"][0]["lang"] == "kotlin"


def test_dev_null_not_used_as_filename():
    # If /dev/null appears (e.g. raw git diff pasted in), it must not produce a hunk
    # with /dev/null as the file; the following real file should still be captured.
    diff = (
        "--- /dev/null\n+++ src/New.kt\n@@ -0,0 +1 @@\n+class New\n"
        "--- src/Existing.kt\n+++ src/Existing.kt\n@@ -1 +1 @@\n-old\n+new\n"
    )
    result = parse_diff("http://mr/1", diff)
    files = [h["file"] for h in result["hunks"]]
    assert "/dev/null" not in files
    assert "src/Existing.kt" in files


def test_unknown_extension_lang_is_other():
    diff = "--- config.yaml\n+++ config.yaml\n@@ -1 +1 @@\n-a\n+b\n"
    result = parse_diff("http://mr/1", diff)
    assert result["hunks"][0]["lang"] == "other"


def test_sql_file_lang():
    diff = "--- db/migrate/V1__init.sql\n+++ db/migrate/V1__init.sql\n@@ -1 +1 @@\n+CREATE TABLE x;\n"
    result = parse_diff("http://mr/1", diff)
    assert result["hunks"][0]["lang"] == "sql"


def test_empty_diff_returns_no_hunks():
    result = parse_diff("http://mr/1", "")
    assert result["hunks"] == []


def test_diff_text_preserved():
    hunk_body = "@@ -1 +1 @@\n-old\n+new"
    diff = f"--- src/Foo.py\n+++ src/Foo.py\n{hunk_body}\n"
    result = parse_diff("http://mr/1", diff)
    assert hunk_body in result["hunks"][0]["diff_text"]
