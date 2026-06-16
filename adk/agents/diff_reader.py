"""
diff_reader_agent: first stage in the ADK pipeline.

Receives diff text directly in the message (pre-loaded by run.py),
parses it into per-file hunks, and stores the result in session state
under output_key="diff_summary" for downstream reviewer agents.
"""

import os
from pydantic import BaseModel
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from shared.model_config import litellm_kwargs


class DiffHunk(BaseModel):
    file: str
    lang: str   # "kotlin" | "java" | "python" | "go" | "typescript" | "other"
    diff_text: str


class DiffSummary(BaseModel):
    pr_url: str
    hunks: list[DiffHunk]


diff_reader_agent = LlmAgent(
    name="diff_reader",
    model=LiteLlm(model=os.environ["CR_MODEL"], **litellm_kwargs()),
    output_key="diff_summary",
    instruction="""\
You receive a unified diff in the message.
Parse it into per-file hunks and output a JSON object with this exact structure:
{
  "pr_url": "<the pr_url from the message>",
  "hunks": [
    { "file": "<relative path>", "lang": "<kotlin|java|python|go|typescript|other>", "diff_text": "<the hunk text for this file>" }
  ]
}
Include only files that have actual code changes (skip files with no diff lines).
Infer lang from the file extension.
Output only the JSON — no explanation text.
""",
)
