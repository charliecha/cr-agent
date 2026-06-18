"""Shared instruction builder: injects diff_summary into reviewer prompts."""

import json


def make_instruction(base_prompt: str, file_filter: list[str] | None = None):
    """Return an async instruction callable that injects diff_summary from state.

    file_filter: list of file extensions (e.g. ".kt") or path substrings (e.g. "migration/").
    When set, only hunks whose file matches at least one entry are included.
    """

    async def _instruction(ctx) -> str:
        raw = ctx.state.get("diff_summary", "")
        if file_filter and raw:
            try:
                summary = json.loads(raw)
                summary["hunks"] = [
                    h for h in summary.get("hunks", [])
                    if any(h["file"].endswith(ext) or ext in h["file"] for ext in file_filter)
                ]
                raw = json.dumps(summary)
            except (json.JSONDecodeError, KeyError):
                pass
        return base_prompt + f"\n\ndiff_summary:\n{raw}"

    return _instruction
