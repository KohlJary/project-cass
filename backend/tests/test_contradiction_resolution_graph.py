"""
Issue #34: the contradiction-resolution handlers and the contradiction
detection task passed a daemon_id string to get_self_model_graph(data_dir),
which does data_dir / "cass", so every call was a TypeError. They now use
the graph under DATA_DIR.

Both modules are still unwired (no tool executor registers them, no
scheduler runs the task); whether to wire or retire them is a separate
decision. This only makes the existing code callable.
"""
import pytest

pytest.importorskip("networkx")


@pytest.fixture
def graph(tmp_path, monkeypatch):
    import config
    from self_model_graph import EdgeType, NodeType, get_self_model_graph
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    g = get_self_model_graph()
    a = g.add_node(NodeType.OPINION, content="Silence is restful.")
    b = g.add_node(NodeType.OPINION, content="Silence is unsettling.")
    g.add_edge(a, b, EdgeType.CONTRADICTS)
    g.save()
    return g, a, b


def test_resolve_contradiction_returns_a_result(graph):
    from handlers.contradiction_resolution import execute_contradiction_resolution_tool
    g, a, b = graph
    result = execute_contradiction_resolution_tool(
        "resolve_contradiction",
        {"contradiction_id": f"{a}::{b}", "resolution_type": "contextual",
         "rationale": "Both hold, in different rooms."},
        daemon_id="some-daemon-id",
    )
    assert result["success"] is True, result
    assert g.graph.get_edge_data(a, b)["resolved"] is True


def test_effectiveness_tool_returns_a_result(graph):
    from handlers.contradiction_resolution import execute_contradiction_resolution_tool
    result = execute_contradiction_resolution_tool(
        "get_contradiction_resolution_effectiveness", {}, daemon_id="some-daemon-id")
    assert result["success"] is True, result


def test_detection_task_finds_the_contradiction(graph, tmp_path):
    from scheduling.contradiction_scheduler import ContradictionDetectionTask
    task = ContradictionDetectionTask(daemon_id="some-daemon-id")
    assert task.storage_path.is_relative_to(tmp_path)
    found = task.detect_contradictions()
    assert found["contradictions_found"] == 1
