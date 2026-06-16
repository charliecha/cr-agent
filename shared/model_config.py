"""Shared litellm config, read from environment variables."""

import os


def _setup_langfuse() -> None:
    """Enable Langfuse tracing if credentials are present in the environment."""
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return
    import litellm
    if "langfuse" not in (litellm.success_callback or []):
        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]


_setup_langfuse()


def litellm_kwargs() -> dict:
    """
    Return kwargs to pass to both ChatLiteLLM and LiteLlm.
    CR_BASE_URL is optional — omit the env var if using a standard provider endpoint.
    """
    kwargs = {}
    if base_url := os.environ.get("CR_BASE_URL"):
        kwargs["api_base"] = base_url
    if api_key := os.environ.get("CR_API_KEY"):
        kwargs["api_key"] = api_key
    return kwargs
