"""Shared litellm config, read from environment variables."""

import os

# Current review context — set by run.py before invoking the agent
_langfuse_tags: list[str] = []


def _setup_langfuse() -> None:
    """Enable Langfuse tracing if credentials are present in the environment."""
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return
    import litellm
    if "langfuse" not in (litellm.success_callback or []):
        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]


_setup_langfuse()


def set_langfuse_context(framework: str, pr_url: str) -> None:
    """
    Set tags for all subsequent litellm calls in this process.
    Each generation will be tagged with the framework and PR name in Langfuse.
    No-op if Langfuse is not configured.
    """
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return
    global _langfuse_tags
    pr_name = pr_url.split("/")[-1] if "/" in pr_url else pr_url
    _langfuse_tags = [framework, f"pr:{pr_name}"]


def litellm_kwargs() -> dict:
    """
    Return kwargs to pass to both ChatLiteLLM and LiteLlm.
    CR_BASE_URL is optional — omit the env var if using a standard provider endpoint.
    Includes Langfuse tags if set via set_langfuse_context().
    """
    kwargs: dict = {}
    if base_url := os.environ.get("CR_BASE_URL"):
        kwargs["api_base"] = base_url
    if api_key := os.environ.get("CR_API_KEY"):
        kwargs["api_key"] = api_key
    if _langfuse_tags:
        # ChatLiteLLM uses model_kwargs to pass extra params to litellm
        # LiteLlm (ADK) accepts metadata directly as a top-level kwarg
        kwargs["metadata"] = {"tags": _langfuse_tags}
    return kwargs
