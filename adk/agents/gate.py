"""Domain gate: skip reviewer agents whose domain is not in active_domains."""

import json
from google.genai import types


def _parse_active_domains(value) -> list:
    """Parse active_domains from session state (may be a JSON string or list)."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return parsed.get("active_domains", [])
        except (json.JSONDecodeError, ValueError):
            pass
    return []


def make_domain_gate(domain: str):
    """Return a before_agent_callback that skips the agent if domain is inactive."""

    def _gate(callback_context):
        raw = callback_context.state.get("active_domains")
        active = _parse_active_domains(raw)
        if domain not in active:
            return types.Content(
                role="model",
                parts=[types.Part(text='{"findings": []}')],
            )
        return None

    return _gate
