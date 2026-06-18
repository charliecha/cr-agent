"""Tests for adk/agents/registry.py — build_reviewer_agent and REVIEWER_SPECS."""

import asyncio
from unittest.mock import patch, MagicMock

from adk.agents.registry import REVIEWER_SPECS, build_reviewer_agent, reviewer_agents


# ── REVIEWER_SPECS sanity ─────────────────────────────────────────────────────

def test_all_domains_have_specs():
    domains = {s.domain for s in REVIEWER_SPECS}
    assert domains == {"android", "backend", "security", "concurrency", "caching", "db_schema", "frontend"}


def test_output_key_convention():
    for spec in REVIEWER_SPECS:
        assert spec.output_key == f"{spec.domain}_findings"


def test_agent_name_convention():
    for spec in REVIEWER_SPECS:
        assert spec.agent_name == f"{spec.domain}_reviewer"


def test_backend_file_filter_includes_migration_paths():
    spec = next(s for s in REVIEWER_SPECS if s.domain == "backend")
    assert ".sql" in spec.file_filter
    assert "migration/" in spec.file_filter


def test_db_schema_file_filter():
    spec = next(s for s in REVIEWER_SPECS if s.domain == "db_schema")
    assert ".sql" in spec.file_filter
    assert "migration/" in spec.file_filter


# ── build_reviewer_agent: prompt tool-name patch ──────────────────────────────

def _resolve_instruction(agent, domain):
    """Extract instruction string from an LlmAgent (may be a callable)."""
    instr = agent.instruction
    if callable(instr):
        class FakeCtx:
            state = {"diff_summary": ""}
        instr = asyncio.run(instr(FakeCtx()))
    return instr


def test_tool_names_patched_in_prompt():
    for spec in REVIEWER_SPECS:
        agent = build_reviewer_agent(spec)
        instr = _resolve_instruction(agent, spec.domain)
        # Patched names present
        assert f"file_read_{spec.domain}(" in instr
        assert f"grep_{spec.domain}(" in instr
        # No bare unpatched names remain
        bare_file_read = instr.replace(f"file_read_{spec.domain}(", "")
        bare_grep = instr.replace(f"grep_{spec.domain}(", "")
        assert "file_read(" not in bare_file_read
        assert "grep(" not in bare_grep


def test_registered_tool_names_match_prompt():
    for spec in REVIEWER_SPECS:
        agent = build_reviewer_agent(spec)
        tool_names = {t.name for t in agent.tools}
        assert f"file_read_{spec.domain}" in tool_names
        assert f"grep_{spec.domain}" in tool_names


def test_reviewer_agents_count():
    assert len(reviewer_agents) == len(REVIEWER_SPECS)
