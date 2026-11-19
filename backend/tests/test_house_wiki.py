"""house_wiki: Cass reads Chapter House's wiki mirror (plan the-house-wiki, phase 2)."""
from pathlib import Path

import house_wiki as hw


def _mirror(tmp_path: Path) -> Path:
    d = tmp_path / "wiki"
    d.mkdir()
    (d / "wonderland.md").write_text("# Wonderland\n\nA multi-agent system as a cast of characters.\n\n"
                                     "**Public:** yes (github.com/KohlJary/wonderland-ai)\n\n## Built\n\n- the Cheshire Cat\n")
    (d / "robokohl.md").write_text("# RoboKohl\n\nKohl's strategy agent.\n\n**Public:** no (house only).\n")
    (d / "start-here.md").write_text("# What we're building\n\n*Front page: everything on this page is public "
                                     "unless a line says house only.*\n\nWe're building things.\n")
    (d / "now.md").write_text("# Now\n\n*House only.*\n\nIn flight.\n")
    return d


def test_list_says_what_is_public(tmp_path):
    got = {p["page"]: p for p in hw.handle({"action": "list"}, _mirror(tmp_path))["pages"]}
    assert got["wonderland"]["public"] == "yes" and got["wonderland"]["title"] == "Wonderland"
    assert got["wonderland"]["about"].startswith("A multi-agent system")
    assert got["robokohl"]["public"] == "no"
    assert got["start-here"]["public"] == "yes"
    assert got["now"]["public"] == "house only"


def test_read_and_search(tmp_path):
    d = _mirror(tmp_path)
    r = hw.handle({"action": "read", "page": "Wonderland.md"}, d)
    assert r["page"] == "wonderland" and "Cheshire Cat" in r["content"] and r["public"] == "yes"
    assert "maybe wonderland" in hw.handle({"action": "read", "page": "wonder"}, d)["error"]
    assert "no page" in hw.handle({"action": "read", "page": "../etc/passwd"}, d)["error"]
    hits = hw.handle({"action": "search", "words": "cheshire characters"}, d)["results"]
    assert hits[0]["page"] == "wonderland" and hits[0]["public"] == "yes"
    assert "error" in hw.handle({"action": "search", "words": "a"}, d)


def test_missing_mirror_and_lever(tmp_path, monkeypatch):
    assert "mirror" in hw.handle({"action": "list"}, tmp_path / "nope")["error"]
    import features
    monkeypatch.setattr(features, "is_enabled", lambda n: False)
    assert hw.wiki_tools() == {}
    monkeypatch.setattr(features, "is_enabled", lambda n: n == "house_wiki")
    assert set(hw.wiki_tools()) == {"house_wiki"}
