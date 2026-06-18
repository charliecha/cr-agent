"""
root_agent: orchestrates the ADK CR pipeline.

Flow:
  SequentialAgent:
    1. planner            — determines active_domains from diff_summary in session state
    2. ParallelAgent([    — all specialists run concurrently; each gates on active_domains
         android_reviewer,
         backend_reviewer,
         security_reviewer,
         concurrency_reviewer,
         caching_reviewer,
         db_schema_reviewer,
         frontend_reviewer,
       ])
  diff_summary is pre-populated in session state by Python (parse_diff) before the runner starts.
  Findings are merged by Python code in run.py (no summarizer LLM call).

NOTE: SequentialAgent and ParallelAgent are deprecated in google-adk 2.x
in favor of Workflow+Edge API, but the Workflow API has known issues with
LlmAgent pipelines in 2.2.0 (context overflow, session state propagation).
Revisit when google-adk stabilizes the Workflow+LlmAgent integration.
"""

import warnings

from adk.agents.planner import planner_agent
from adk.agents.android_reviewer import android_reviewer_agent
from adk.agents.backend_reviewer import backend_reviewer_agent
from adk.agents.security_reviewer import security_reviewer_agent
from adk.agents.concurrency_reviewer import concurrency_reviewer_agent
from adk.agents.caching_reviewer import caching_reviewer_agent
from adk.agents.db_schema_reviewer import db_schema_reviewer_agent
from adk.agents.frontend_reviewer import frontend_reviewer_agent

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from google.adk.agents import SequentialAgent, ParallelAgent

    _parallel_reviewers = ParallelAgent(
        name="parallel_reviewers",
        sub_agents=[
            android_reviewer_agent,
            backend_reviewer_agent,
            security_reviewer_agent,
            concurrency_reviewer_agent,
            caching_reviewer_agent,
            db_schema_reviewer_agent,
            frontend_reviewer_agent,
        ],
    )

    root_agent = SequentialAgent(
        name="cr_root",
        sub_agents=[planner_agent, _parallel_reviewers],
    )
