"""Reviewer registry: single source of truth for all domain reviewer specs.

Adding a new reviewer only requires adding one entry here — no need to create
a new module, update root_agent.py, or manually align output_key/file_filter.
"""

import os
from dataclasses import dataclass, field
from collections.abc import Sequence

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool

from shared.tools import file_read as _file_read, grep as _grep
from shared.model_config import litellm_kwargs
from adk.agents.gate import make_domain_gate
from adk.agents.instruction_builder import make_instruction
import adk.prompts as prompts


@dataclass
class ReviewerSpec:
    domain: str
    instruction: str
    file_filter: list[str] = field(default_factory=list)

    @property
    def output_key(self) -> str:
        return f"{self.domain}_findings"

    @property
    def agent_name(self) -> str:
        return f"{self.domain}_reviewer"


REVIEWER_SPECS: list[ReviewerSpec] = [
    ReviewerSpec(
        domain="android",
        instruction=prompts.ANDROID_REVIEWER_INSTRUCTION,
        file_filter=[".kt", ".java"],
    ),
    ReviewerSpec(
        domain="backend",
        instruction=prompts.BACKEND_REVIEWER_INSTRUCTION,
        file_filter=[".kt", ".java", ".py", ".go", ".ts", ".sql", "migration/", "flyway/", "changelog/", "liquibase/", "db/migrate/"],
    ),
    ReviewerSpec(
        domain="security",
        instruction=prompts.SECURITY_REVIEWER_INSTRUCTION,
    ),
    ReviewerSpec(
        domain="concurrency",
        instruction=prompts.CONCURRENCY_REVIEWER_INSTRUCTION,
    ),
    ReviewerSpec(
        domain="caching",
        instruction=prompts.CACHING_REVIEWER_INSTRUCTION,
    ),
    ReviewerSpec(
        domain="db_schema",
        instruction=prompts.DB_SCHEMA_REVIEWER_INSTRUCTION,
        file_filter=[".sql", "migration/", "flyway/", "changelog/", "liquibase/", "db/migrate/"],
    ),
    ReviewerSpec(
        domain="frontend",
        instruction=prompts.FRONTEND_REVIEWER_INSTRUCTION,
        file_filter=[".vue", ".ts", ".tsx"],
    ),
]


def _make_tools(domain: str) -> Sequence:
    def file_read_tool(repo_root: str, filepath: str, start_line: int = 1, end_line: int = 0) -> str:
        return _file_read(repo_root, filepath, start_line, end_line)

    def grep_tool(repo_root: str, pattern: str, file_glob: str = "**/*") -> str:
        return _grep(repo_root, pattern, file_glob)

    # Give each tool a unique name per domain to avoid ADK tool registry conflicts
    file_read_tool.__name__ = f"file_read_{domain}"
    grep_tool.__name__ = f"grep_{domain}"
    return [FunctionTool(file_read_tool), FunctionTool(grep_tool)]


def build_reviewer_agent(spec: ReviewerSpec) -> LlmAgent:
    # Patch tool names in the prompt to match actual registered names (file_read_<domain> / grep_<domain>)
    patched = (
        spec.instruction
        .replace("file_read(", f"file_read_{spec.domain}(")
        .replace("grep(", f"grep_{spec.domain}(")
    )
    return LlmAgent(
        name=spec.agent_name,
        model=LiteLlm(model=os.environ["CR_MODEL"], **litellm_kwargs()),
        output_key=spec.output_key,
        tools=_make_tools(spec.domain),
        instruction=make_instruction(patched, file_filter=spec.file_filter or None),
        before_agent_callback=make_domain_gate(spec.domain),
    )


reviewer_agents = [build_reviewer_agent(spec) for spec in REVIEWER_SPECS]
