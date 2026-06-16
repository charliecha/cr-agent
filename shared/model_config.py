"""Shared litellm config, read from environment variables."""

import os
import uuid


# ── Token accumulator ─────────────────────────────────────────────────────────

class _TokenCounter:
    """Accumulates prompt/completion tokens across all litellm calls in this process."""
    def __init__(self):
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def add(self, usage) -> None:
        if usage is None:
            return
        self.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
        self.completion_tokens += getattr(usage, "completion_tokens", 0) or 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


token_counter = _TokenCounter()

# Current review context — set by run.py before invoking the agent
_langfuse_tags: list[str] = []
_langfuse_session_id: str = ""


def _setup_litellm() -> None:
    import litellm
    from litellm.integrations.custom_logger import CustomLogger

    class _TokenLogger(CustomLogger):
        def log_success_event(self, kwargs, response_obj, start_time, end_time):
            try:
                token_counter.add(response_obj.usage)
            except Exception:
                pass

        async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
            try:
                token_counter.add(response_obj.usage)
            except Exception:
                pass

    litellm.callbacks = [_TokenLogger()]

    if os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"):
        if "langfuse" not in (litellm.success_callback or []):
            litellm.success_callback = ["langfuse"]
            litellm.failure_callback = ["langfuse"]


_setup_litellm()


def set_langfuse_context(framework: str, pr_url: str) -> None:
    """
    Set tags and session_id for all subsequent litellm calls in this process.
    Each generation will be tagged with the framework and PR name in Langfuse,
    and grouped under a single session_id so all calls from one review run are linked.
    No-op if Langfuse is not configured.
    """
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return
    global _langfuse_tags, _langfuse_session_id
    pr_name = pr_url.split("/")[-1] if "/" in pr_url else pr_url
    _langfuse_tags = [framework, f"pr:{pr_name}"]
    _langfuse_session_id = str(uuid.uuid4())


def litellm_kwargs() -> dict:
    """
    Return kwargs to pass to both ChatLiteLLM and LiteLlm.
    CR_BASE_URL is optional — omit the env var if using a standard provider endpoint.
    Includes Langfuse tags and session_id if set via set_langfuse_context().
    """
    kwargs: dict = {}
    if base_url := os.environ.get("CR_BASE_URL"):
        kwargs["api_base"] = base_url
    if api_key := os.environ.get("CR_API_KEY"):
        kwargs["api_key"] = api_key
    if _langfuse_tags:
        kwargs["metadata"] = {"tags": _langfuse_tags, "session_id": _langfuse_session_id}
    return kwargs
