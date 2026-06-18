"""Tests for adk/agents/instruction_builder.py."""

import asyncio
import json

from adk.agents.instruction_builder import make_instruction


class _Ctx:
    def __init__(self, diff_summary: str):
        self.state = {"diff_summary": diff_summary}


def _run_instruction(base_prompt: str, diff_summary: str, file_filter: list[str] | None = None) -> str:
    instruction = make_instruction(base_prompt, file_filter=file_filter)
    return asyncio.run(instruction(_Ctx(diff_summary)))


def test_make_instruction_injects_raw_diff_summary():
    raw = json.dumps({"pr_url": "http://mr/1", "hunks": [{"file": "src/Foo.kt", "lang": "kotlin"}]})
    result = _run_instruction("BASE", raw)
    assert result == f"BASE\n\ndiff_summary:\n{raw}"


def test_make_instruction_filters_matching_hunks():
    raw = json.dumps({
        "pr_url": "http://mr/1",
        "hunks": [
            {"file": "src/Foo.kt", "lang": "kotlin", "diff_text": "kt"},
            {"file": "db/migrate/V1__init.sql", "lang": "sql", "diff_text": "sql"},
            {"file": "web/App.vue", "lang": "typescript", "diff_text": "vue"},
        ],
    })
    result = _run_instruction("BASE", raw, file_filter=[".sql", "migration/", "db/migrate/"])
    injected = result.split("diff_summary:\n", 1)[1]
    parsed = json.loads(injected)
    assert [h["file"] for h in parsed["hunks"]] == ["db/migrate/V1__init.sql"]


def test_make_instruction_keeps_empty_hunks_when_no_filter_match():
    raw = json.dumps({
        "pr_url": "http://mr/1",
        "hunks": [{"file": "src/Foo.kt", "lang": "kotlin", "diff_text": "kt"}],
    })
    result = _run_instruction("BASE", raw, file_filter=[".sql"])
    injected = result.split("diff_summary:\n", 1)[1]
    parsed = json.loads(injected)
    assert parsed["hunks"] == []


def test_make_instruction_falls_back_to_raw_on_invalid_json():
    raw = "{not valid json"
    result = _run_instruction("BASE", raw, file_filter=[".kt"])
    assert result == f"BASE\n\ndiff_summary:\n{raw}"


def test_make_instruction_handles_missing_hunks_key():
    raw = json.dumps({"pr_url": "http://mr/1"})
    result = _run_instruction("BASE", raw, file_filter=[".kt"])
    injected = result.split("diff_summary:\n", 1)[1]
    parsed = json.loads(injected)
    assert parsed["hunks"] == []
