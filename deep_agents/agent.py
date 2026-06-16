"""
Deep Agents implementation of the CR agent.

Uses create_deep_agent (LangGraph-based) with three tools:
git_diff, file_read, grep. The agent autonomously decides how many
tool rounds it needs before producing the final CRReport.
"""

import os
from langchain_core.tools import tool as lc_tool
from langchain_core.messages import HumanMessage

from shared.tools import git_diff as _git_diff, file_read as _file_read, grep as _grep
from shared.schemas import CRReport
from deep_agents.prompts import CR_SYSTEM_PROMPT


# ── Tool wrappers (LangChain @tool format) ────────────────────────────────────

@lc_tool
def git_diff(pr_url: str) -> str:
    """Fetch the unified diff for a pull request. Accepts a PR URL (https://...) or a local .diff file path."""
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

    # Search all AI messages from last to first — the final JSON report may not
    # always be in the very last message (model sometimes appends analysis after).
    # For each message, scan right-to-left for a { that starts a valid CRReport JSON.
    import json as _json
    from langchain_core.messages import AIMessage
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        text = msg.content if isinstance(msg.content, str) else ""
        if not text:
            continue
        for i in range(len(text) - 1, -1, -1):
            if text[i] != '{':
                continue
            brace_end = text.rfind('}', i)
            if brace_end == -1:
                continue
            candidate = text[i:brace_end + 1]
            try:
                _json.loads(candidate)
                return CRReport.model_validate_json(candidate)
            except Exception:
                continue

    all_text = " | ".join(
        m.content[:200] for m in messages
        if isinstance(m, AIMessage) and isinstance(m.content, str)
    )
    raise ValueError(f"No valid CRReport JSON in any AI message:\n{all_text[:500]}")
