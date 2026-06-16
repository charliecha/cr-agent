"""
backend_reviewer_agent: reviews Python/Go/TypeScript hunks for backend issues.
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


class BackendReviewResult(BaseModel):
    findings: list[Finding]


def _file_read_tool(repo_root: str, filepath: str, start_line: int = 1, end_line: int = 0) -> str:
    return _file_read(repo_root, filepath, start_line, end_line)


def _grep_tool(repo_root: str, pattern: str, file_glob: str = "**/*") -> str:
    return _grep(repo_root, pattern, file_glob)


backend_reviewer_agent = LlmAgent(
    name="backend_reviewer",
    model=LiteLlm(model=os.environ["CR_MODEL"], **litellm_kwargs()),
    output_key="backend_findings",
    tools=[FunctionTool(_file_read_tool), FunctionTool(_grep_tool)],
    instruction="""\
You are a backend expert. The session state contains "diff_summary" with per-file diff hunks.
Review only Python/Go/TypeScript hunks for backend-specific problems:
- SQL injection or raw query construction with user input
- Missing database transactions around multi-step writes
- N+1 query patterns
- Race conditions / missing mutex in concurrent code
- Missing auth/authz checks on new endpoints
- API contract mismatches (field renamed or type changed on one side only)
- Unhandled error returns (especially in Go)

RULE: If any method/function signature changes (new/removed/renamed parameter),
you MUST call grep to find all callers before concluding there is no bug.

Use file_read and grep to look up callers, schema definitions, or route handlers when needed.
Skip style, formatting, and Android issues.
If there are no Python/Go/TypeScript hunks, output: {"findings": []}

After completing all tool calls, output a JSON object:
{ "findings": [ { "file": ..., "line_start": ..., "line_end": ..., "severity": "critical"|"warning"|"info", "category": "logic_bug"|"null_deref"|"resource_leak"|"concurrency_bug"|"api_mismatch"|"memory_leak"|"security", "description": ..., "suggestion": ... } ] }

IMPORTANT: category must be exactly one of those snake_case values — no spaces, no other strings.
""",
)
