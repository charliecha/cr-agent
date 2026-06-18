"""
root_agent: orchestrates the ADK CR pipeline.

Flow:
  Workflow (outer, sequential):
    1. planner_agent         — writes active_domains to session state
    2. parallel_reviewers_wf — all 7 reviewers run concurrently via inner Workflow;
                               each gates on active_domains; results written via output_key
  A noop_sink node collects all reviewer branches so the inner Workflow
  has a single terminal node (Workflow API requirement).

  diff_summary is pre-populated in session state by Python (parse_diff) before the runner starts.
  Findings are merged by Python code in run.py (no summarizer LLM call).
  Reviewer agents are built from REVIEWER_SPECS in registry.py — add new reviewers there.
"""

import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.workflow import Edge, START, Workflow

from adk.agents.planner import planner_agent
from adk.agents.registry import reviewer_agents
from shared.model_config import litellm_kwargs

_noop_sink = LlmAgent(
    name="noop_sink",
    model=LiteLlm(model=os.environ["CR_MODEL"], **litellm_kwargs()),
    instruction="Respond with exactly: done",
)

_parallel_reviewers_wf = Workflow(
    name="parallel_reviewers_wf",
    edges=[
        *[Edge(from_node=START, to_node=r) for r in reviewer_agents],
        *[Edge(from_node=r, to_node=_noop_sink) for r in reviewer_agents],
    ],
)

root_agent = Workflow(
    name="cr_root",
    edges=[
        Edge(from_node=START, to_node=planner_agent),
        Edge(from_node=planner_agent, to_node=_parallel_reviewers_wf),
    ],
)
