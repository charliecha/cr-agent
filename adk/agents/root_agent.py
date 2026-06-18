"""
root_agent: orchestrates the ADK CR pipeline.

Flow:
  SequentialAgent:
    1. planner            — determines active_domains from diff_summary in session state
    2. ParallelAgent([    — all reviewers run concurrently; each gates on active_domains
         ...reviewer_agents from registry
       ])
  diff_summary is pre-populated in session state by Python (parse_diff) before the runner starts.
  Findings are merged by Python code in run.py (no summarizer LLM call).
  Reviewer agents are built from REVIEWER_SPECS in registry.py — add new reviewers there.

NOTE: SequentialAgent and ParallelAgent are deprecated in google-adk 2.x
in favor of Workflow+Edge API, but the Workflow API has known issues with
LlmAgent pipelines in 2.2.0 (context overflow, session state propagation).
Revisit when google-adk stabilizes the Workflow+LlmAgent integration.
"""

import warnings

from adk.agents.planner import planner_agent
from adk.agents.registry import reviewer_agents

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from google.adk.agents import SequentialAgent, ParallelAgent

    _parallel_reviewers = ParallelAgent(
        name="parallel_reviewers",
        sub_agents=reviewer_agents,
    )

    root_agent = SequentialAgent(
        name="cr_root",
        sub_agents=[planner_agent, _parallel_reviewers],
    )
