"""
root_agent: orchestrates the ADK CR pipeline.

Flow:
  SequentialAgent:
    1. diff_reader
    2. ParallelAgent([android_reviewer, backend_reviewer])
    3. summarizer (LlmAgent with output_schema=CRReport)

NOTE: SequentialAgent and ParallelAgent are deprecated in google-adk 2.x
in favor of Workflow+Edge API, but the Workflow API has known issues with
LlmAgent pipelines in 2.2.0 (context overflow, session state propagation).
Revisit when google-adk stabilizes the Workflow+LlmAgent integration.
"""

import os
import warnings
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from shared.schemas import CRReport
from adk.agents.diff_reader import diff_reader_agent
from adk.agents.android_reviewer import android_reviewer_agent
from adk.agents.backend_reviewer import backend_reviewer_agent
from shared.model_config import litellm_kwargs

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from google.adk.agents import SequentialAgent, ParallelAgent

    _parallel_reviewers = ParallelAgent(
        name="parallel_reviewers",
        sub_agents=[android_reviewer_agent, backend_reviewer_agent],
    )

_summarizer = LlmAgent(
    name="cr_summarizer",
    model=LiteLlm(model=os.environ["CR_MODEL"], **litellm_kwargs()),
    output_schema=CRReport,
    output_key="cr_report",
    instruction="""\
The session state contains:
- "android_findings": findings from the Android reviewer
- "backend_findings": findings from the backend reviewer
- "diff_summary": the parsed diff with pr_url

Merge all findings into a single CRReport JSON:
- pr_url: from diff_summary.pr_url
- findings: merged and deduplicated (same file+line_start+category → keep more severe)
- summary: 2-3 sentence overall assessment
- verdict: "approve" | "request_changes" | "block"

Rules:
- verdict=block only for security or data-loss bugs
- verdict=approve only if findings is empty or all INFO severity
""",
)

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    root_agent = SequentialAgent(
        name="cr_root",
        sub_agents=[diff_reader_agent, _parallel_reviewers, _summarizer],
    )
