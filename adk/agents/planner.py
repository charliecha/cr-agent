"""
planner_agent: reads diff_summary from session state and determines which
review domains are relevant. Outputs active_domains list to session state.
"""

import os
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from shared.model_config import litellm_kwargs
from adk.prompts import PLANNER_INSTRUCTION

planner_agent = LlmAgent(
    name="planner",
    model=LiteLlm(model=os.environ["CR_MODEL"], **litellm_kwargs()),
    output_key="active_domains",
    instruction=PLANNER_INSTRUCTION,
)
