"""Tests for adk/agents/root_agent.py workflow assembly."""

from google.adk.workflow import START

from adk.agents.planner import planner_agent
from adk.agents.registry import reviewer_agents
from adk.agents.root_agent import _noop_sink, _parallel_reviewers_wf, root_agent


def test_root_workflow_has_expected_outer_edges():
    assert root_agent.name == "cr_root"
    assert len(root_agent.edges) == 2

    start_edge = next(edge for edge in root_agent.edges if edge.from_node == START)
    planner_edge = next(edge for edge in root_agent.edges if edge.from_node == planner_agent)

    assert start_edge.to_node == planner_agent
    assert planner_edge.to_node == _parallel_reviewers_wf


def test_parallel_workflow_connects_all_reviewers_to_sink():
    assert _parallel_reviewers_wf.name == "parallel_reviewers_wf"

    start_edges = [edge for edge in _parallel_reviewers_wf.edges if edge.from_node == START]
    sink_edges = [edge for edge in _parallel_reviewers_wf.edges if edge.to_node == _noop_sink]

    assert len(start_edges) == len(reviewer_agents)
    assert len(sink_edges) == len(reviewer_agents)
    assert {edge.to_node.name for edge in start_edges} == {agent.name for agent in reviewer_agents}
    assert {edge.from_node.name for edge in sink_edges} == {agent.name for agent in reviewer_agents}


def test_noop_sink_is_terminal_llm_agent():
    assert _noop_sink.name == "noop_sink"
    assert _noop_sink.tools == []
    assert _noop_sink.output_key is None
