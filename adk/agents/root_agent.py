"""
root_agent: orchestrates the ADK CR pipeline.

Flow:
  SequentialAgent:
    1. diff_reader  — parses diff into per-file hunks, stores in session state
    2. ParallelAgent([android_reviewer, backend_reviewer])  — review in parallel
  Findings are merged by Python code in run.py (no summarizer LLM call).

NOTE: SequentialAgent and ParallelAgent are deprecated in google-adk 2.x
in favor of Workflow+Edge API, but the Workflow API has known issues with
LlmAgent pipelines in 2.2.0 (context overflow, session state propagation).
Revisit when google-adk stabilizes the Workflow+LlmAgent integration.
"""

import warnings

from adk.agents.diff_reader import diff_reader_agent
from adk.agents.android_reviewer import android_reviewer_agent
from adk.agents.backend_reviewer import backend_reviewer_agent

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from google.adk.agents import SequentialAgent, ParallelAgent

    _parallel_reviewers = ParallelAgent(
        name="parallel_reviewers",
        sub_agents=[android_reviewer_agent, backend_reviewer_agent],
    )

    root_agent = SequentialAgent(
        name="cr_root",
        sub_agents=[diff_reader_agent, _parallel_reviewers],
    )
