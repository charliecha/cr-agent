"""
db_schema_reviewer_agent: reviews migration vs application-layer data contract issues.
Only activates if "db_schema" is in session state active_domains.
"""

import os
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool

from shared.tools import file_read as _file_read, grep as _grep
from shared.model_config import litellm_kwargs
from adk.prompts import DB_SCHEMA_REVIEWER_INSTRUCTION
from adk.agents.gate import make_domain_gate
from adk.agents.instruction_builder import make_instruction


def _file_read_tool(repo_root: str, filepath: str, start_line: int = 1, end_line: int = 0) -> str:
    return _file_read(repo_root, filepath, start_line, end_line)


def _grep_tool(repo_root: str, pattern: str, file_glob: str = "**/*") -> str:
    return _grep(repo_root, pattern, file_glob)


db_schema_reviewer_agent = LlmAgent(
    name="db_schema_reviewer",
    model=LiteLlm(model=os.environ["CR_MODEL"], **litellm_kwargs()),
    output_key="db_schema_findings",
    tools=[FunctionTool(_file_read_tool), FunctionTool(_grep_tool)],
    instruction=make_instruction(DB_SCHEMA_REVIEWER_INSTRUCTION),
    before_agent_callback=make_domain_gate("db_schema"),
)
