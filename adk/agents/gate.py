"""Domain gate: skip reviewer agents whose domain is not in active_domains."""

import json
from google.genai import types

ALL_DOMAINS = ["android", "security", "concurrency", "caching", "db_schema", "backend", "frontend"]


def _parse_active_domains(value) -> list | None:
    """Parse active_domains from session state.

    Returns a list of domain strings on success, or None if parsing fails.
    Callers must treat None or [] as "unknown" — both trigger the fail-safe fallback.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                domains = parsed.get("active_domains")
                if isinstance(domains, list):
                    return domains
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def make_domain_gate(domain: str):
    """Return a before_agent_callback that skips the agent if domain is inactive.

    Fail-safe: if active_domains cannot be parsed, let the reviewer run
    (conservative fallback — better to over-review than to silently skip).
    """

    def _gate(callback_context):
        raw = callback_context.state.get("active_domains")
        active = _parse_active_domains(raw)
        if not active:
            # Planner output invalid or empty — let reviewer run (fail-safe)
            return None
        if domain not in active:
            return types.Content(
                role="model",
                parts=[types.Part(text='{"findings": []}')],
            )
        return None

    return _gate
