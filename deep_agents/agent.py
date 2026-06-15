"""
Deep Agents implementation of the CR agent.

Uses create_deep_agent (LangGraph-based) with three tools:
git_diff, file_read, grep. The agent autonomously decides how many
tool rounds it needs before producing the final CRReport.
"""

import os
import re
from langchain_core.tools import tool as lc_tool
from langchain_core.messages import HumanMessage

from shared.tools import git_diff as _git_diff, file_read as _file_read, grep as _grep
from shared.schemas import CRReport
from deep_agents.prompts import CR_SYSTEM_PROMPT


# ── Tool wrappers (LangChain @tool format) ────────────────────────────────────

@lc_tool
def git_diff(pr_url: str) -> str:
    """Fetch the unified diff for a pull request URL."""
    return _git_diff(pr_url)


@lc_tool
def file_read(repo_root: str, filepath: str, start_line: int = 1, end_line: int = 0) -> str:
    """Read lines from a file in the checked-out repo. end_line=0 means EOF."""
    return _file_read(repo_root, filepath, start_line, end_line)


@lc_tool
def grep(repo_root: str, pattern: str, file_glob: str = "**/*") -> str:
    """Search the repo for a regex pattern. Returns file:line matches."""
    return _grep(repo_root, pattern, file_glob)


# ── Agent factory ─────────────────────────────────────────────────────────────

def build_agent():
    from deepagents import create_deep_agent
    from langchain_litellm import ChatLiteLLM
    from shared.model_config import litellm_kwargs

    llm = ChatLiteLLM(model=os.environ["CR_MODEL"], **litellm_kwargs())
    return create_deep_agent(
        model=llm,
        tools=[git_diff, file_read, grep],
        system_prompt=CR_SYSTEM_PROMPT,
    )


def run_review(pr_url: str, repo_root: str) -> CRReport:
    agent = build_agent()
    result = agent.invoke({
        "messages": [HumanMessage(content=(
            f"Please review this pull request: {pr_url}\n"
            f"The repository is checked out at: {repo_root}"
        ))]
    })

    messages = result.get("messages", [])
    final_text = messages[-1].content if messages else ""

    # model may prefix the JSON with explanation text — extract the first {...} block
    m = re.search(r"\{.*\}", final_text, flags=re.DOTALL)
    if not m:
        raise ValueError(f"No JSON object found in agent output:\n{final_text[:500]}")
    return CRReport.model_validate_json(m.group())
