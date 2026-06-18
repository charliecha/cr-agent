"""Tests for adk/agents/gate.py — _parse_active_domains and make_domain_gate."""

import json
from unittest.mock import MagicMock

from adk.agents.gate import _parse_active_domains, make_domain_gate, ALL_DOMAINS


# ── _parse_active_domains ─────────────────────────────────────────────────────

def test_parse_list_passthrough():
    assert _parse_active_domains(["android", "backend"]) == ["android", "backend"]


def test_parse_json_list():
    assert _parse_active_domains('["security"]') == ["security"]


def test_parse_json_dict_with_key():
    raw = json.dumps({"active_domains": ["db_schema"]})
    assert _parse_active_domains(raw) == ["db_schema"]


def test_parse_empty_list():
    assert _parse_active_domains("[]") == []


def test_parse_invalid_string_returns_none():
    assert _parse_active_domains("not json") is None


def test_parse_none_returns_none():
    assert _parse_active_domains(None) is None


def test_parse_int_returns_none():
    assert _parse_active_domains(42) is None


def test_parse_dict_without_key_returns_none():
    assert _parse_active_domains("{}") is None


# ── make_domain_gate ──────────────────────────────────────────────────────────

def _ctx(active_domains_value):
    ctx = MagicMock()
    ctx.state = {"active_domains": active_domains_value}
    return ctx


def test_gate_allows_when_domain_active():
    gate = make_domain_gate("backend")
    result = gate(_ctx('["backend", "security"]'))
    assert result is None  # None = let reviewer run


def test_gate_blocks_when_domain_inactive():
    gate = make_domain_gate("android")
    result = gate(_ctx('["backend"]'))
    assert result is not None  # Content = skip reviewer
    assert '{"findings": []}' in result.parts[0].text


def test_gate_failsafe_on_none():
    # Unparseable value → let all reviewers run
    gate = make_domain_gate("android")
    result = gate(_ctx("not valid json"))
    assert result is None


def test_gate_failsafe_on_empty_list():
    # Planner returned [] despite prompt saying "always include at least one domain"
    gate = make_domain_gate("backend")
    result = gate(_ctx("[]"))
    assert result is None


def test_gate_failsafe_on_missing_state():
    # active_domains key absent entirely
    ctx = MagicMock()
    ctx.state = {}
    gate = make_domain_gate("security")
    result = gate(ctx)
    assert result is None


def test_all_domains_list_is_complete():
    # Sanity: ALL_DOMAINS matches the 7 defined reviewers
    assert set(ALL_DOMAINS) == {"android", "backend", "security", "concurrency", "caching", "db_schema", "frontend"}
