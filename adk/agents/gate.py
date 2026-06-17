"""Domain gate: skip reviewer agents whose domain is not in active_domains."""

from google.genai import types


def make_domain_gate(domain: str):
    """Return a before_agent_callback that skips the agent if domain is inactive."""

    def _gate(callback_context):
        active = callback_context.state.get("active_domains") or []
        if domain not in active:
            return types.Content(
                role="model",
                parts=[types.Part(text='{"findings": []}')],
            )
        return None

    return _gate
