"""
android_reviewer_agent: reviews Kotlin/Java hunks for Android-specific issues.
Reads diff_summary from session state written by diff_reader_agent.
"""

import os
from pydantic import BaseModel
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool

from shared.tools import file_read as _file_read, grep as _grep
from shared.schemas import Finding
from shared.model_config import litellm_kwargs


class AndroidReviewResult(BaseModel):
    findings: list[Finding]


def _file_read_tool(repo_root: str, filepath: str, start_line: int = 1, end_line: int = 0) -> str:
    return _file_read(repo_root, filepath, start_line, end_line)


def _grep_tool(repo_root: str, pattern: str, file_glob: str = "**/*") -> str:
    return _grep(repo_root, pattern, file_glob)


android_reviewer_agent = LlmAgent(
    name="android_reviewer",
    model=LiteLlm(model=os.environ["CR_MODEL"], **litellm_kwargs()),
    output_key="android_findings",
    tools=[FunctionTool(_file_read_tool), FunctionTool(_grep_tool)],
    instruction="""\
You are an Android expert. The session state contains "diff_summary" with per-file diff hunks.
Review only Kotlin/Java hunks for Android-specific problems:
- Memory leaks (holding Context/Activity in long-lived objects)
- Thread violations (UI work off main thread, blocking calls on main thread)
- Missing lifecycle cleanup (not unregistering listeners, not cancelling coroutines)
- Null safety issues (unsafe !! operator, Java interop nullability)
- Resource leaks (Cursor, Stream, Bitmap not closed)

RULE: If any method/function signature changes (new/removed/renamed parameter),
you MUST call grep to find all callers before concluding there is no bug.

Use file_read and grep to look up callers or class definitions when needed.
Skip style, formatting, and non-Android issues.
If there are no Kotlin/Java hunks, output: {"findings": []}

After completing all tool calls, output a JSON object:
{ "findings": [ { "file": ..., "line_start": ..., "line_end": ..., "severity": "critical"|"warning"|"info", "category": "logic_bug"|"null_deref"|"resource_leak"|"concurrency_bug"|"api_mismatch"|"memory_leak"|"security", "description": ..., "suggestion": ... } ] }

IMPORTANT: category must be exactly one of those snake_case values — no spaces, no other strings.
""",
)
