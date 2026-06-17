"""Shared instruction builder: injects diff_summary into reviewer prompts."""


def make_instruction(base_prompt: str):
    """Return an async instruction callable that injects diff_summary from state."""

    async def _instruction(ctx) -> str:
        diff_summary = ctx.state.get("diff_summary", "")
        return base_prompt + f"\n\ndiff_summary:\n{diff_summary}"

    return _instruction
