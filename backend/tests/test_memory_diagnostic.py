"""scripts/memory_diagnostic.py (plan "Cass's memory", item 0bbf5224)."""
import json
import shutil

import pytest

from scripts import memory_diagnostic as md


@pytest.fixture
def world(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")
    import memory.core as memory_core
    from tests.fakes import embeddings
    from tests.memory_battery.world import build_world
    embeddings.install_bow(monkeypatch)
    monkeypatch.setattr(memory_core, "CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    return build_world()


def test_diagnose_reports_each_person_and_the_pools(world):
    report = md.diagnose(world.memory, world.conversations, samples=5, min_messages=1)
    by_name = {p["name"]: p for p in report["people"]}
    assert {"Rowan", "Sam", "Imani"} <= set(by_name)
    rowan = by_name["Rowan"]
    assert rowan["stored"]["conversation_memories"] == 2 and rowan["stored"]["summary_chunks"] == 1
    assert rowan["stored"]["peopledex"]["observations"] == 1
    r = rowan["recall"]["recent"]
    assert r["asked"] == 2 and r["episodes_of_someone_else"] == 0
    assert rowan["timeline_on_hey"]["present"]
    assert report["pools"]["recall_pool_by_type"]["cass_self_observation"] == world.article_count
    text = md.render(report)
    assert "## Rowan" in text and "recall (recent)" in text and "## Shared pools" in text


def test_run_seals_seeds_and_always_cleans_up(tmp_path, test_db):
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy(test_db, source / "cass.db")
    seals = tmp_path / "seals"
    seen = {}

    def runner(cell, report_json):
        seen["cell"] = cell
        assert (cell / "cass.db").exists()
        report_json.write_text(json.dumps({"generated": "now", "people": [], "pools": {
            "recall_pool_by_type": {}, "self_observations": {"total": 0, "from_articles": 0},
            "open_questions": {"total": 0, "from_articles": 0}, "growth_edges": {"total": 0}}}))

    out = md.run(source, tmp_path / "out", 5, 1, seal_root=seals, runner=runner)
    assert out.exists() and out.read_text().startswith("# Memory diagnostic")
    assert not seen["cell"].exists(), "the cell is deleted"
    assert not any(seals.iterdir()), "the seal is deleted"

    def broken(cell, report_json):
        seen["cell"] = cell
        raise RuntimeError("probe failed")
    with pytest.raises(RuntimeError):
        md.run(source, tmp_path / "out", 5, 1, seal_root=seals, runner=broken)
    assert not seen["cell"].exists() and not any(seals.iterdir()), "cleaned up after a failure too"
