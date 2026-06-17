"""
android_reviewer_agent: reviews Kotlin/Java hunks for Android-specific issues.
Reads diff_summary from session state written by diff_reader_agent.
"""

import os
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool

from shared.tools import file_read as _file_read, grep as _grep
from shared.model_config import litellm_kwargs
from adk.prompts import ANDROID_REVIEWER_INSTRUCTION
from adk.agents.gate import make_domain_gate


def _file_read_tool(repo_root: str, filepath: str, start_line: int = 1, end_line: int = 0) -> str:
    return _file_read(repo_root, filepath, start_line, end_line)


def _grep_tool(repo_root: str, pattern: str, file_glob: str = "**/*") -> str:
    return _grep(repo_root, pattern, file_glob)


android_reviewer_agent = LlmAgent(
    name="android_reviewer",
    model=LiteLlm(model=os.environ["CR_MODEL"], **litellm_kwargs()),
    output_key="android_findings",
    tools=[FunctionTool(_file_read_tool), FunctionTool(_grep_tool)],
    instruction=ANDROID_REVIEWER_INSTRUCTION,
    before_agent_callback=make_domain_gate("android"),
)
