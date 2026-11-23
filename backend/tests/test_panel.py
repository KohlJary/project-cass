"""Her panel (panel.py): nothing shows without her yes; work is only the projects she shows."""
import panel as P
import workshop as W
from tests.test_workshop import kohls  # noqa: F401  (fixture)


def _essay(data):
    W.new("Substack Intro", "writing", "Who I am, for the House's readers.", data)
    W.write("substack-intro", "intro-draft.md", "# Hi\n\nVerdict first.", data)
    W.write("substack-intro", "notes/scratch.py", "x = 1", data)  # not a text doc


def test_nothing_shows_until_she_answers(tmp_path):
    _essay(tmp_path)
    assert W.handle({"action": "show", "project": "substack-intro"}, tmp_path)["note"].startswith("marked shown")
    out = P.build(tmp_path)
    assert out["sections"] == {} and out["settings"]["audience"] == "none"
    assert set(out["settings"]["sections"].values()) == {"not_yet"}
    P.set_answers({"work": "yes"}, None, None, tmp_path)
    assert P.build(tmp_path)["sections"] == {}  # still no audience


def test_work_is_the_projects_she_shows_with_their_text(tmp_path):
    _essay(tmp_path)
    W.new("Private", "writing", "mine alone", tmp_path)
    P.set_answers({"work": "yes", "now": "no"}, "house", {"work": "drafts too"}, tmp_path)
    assert P.build(tmp_path)["sections"]["work"] == []
    assert W.handle({"action": "show", "project": "substack-intro"}, tmp_path)["shown"]
    work = P.build(tmp_path)["sections"]["work"]
    assert [w["project"] for w in work] == ["substack-intro"]
    assert [d["path"] for d in work[0]["docs"]] == ["PROJECT.md", "intro-draft.md"]
    assert work[0]["docs"][1]["content"] == "# Hi\n\nVerdict first."
    W.handle({"action": "hide", "project": "substack-intro"}, tmp_path)
    assert P.build(tmp_path)["sections"]["work"] == []


def test_answers_are_checked_and_kept(tmp_path):
    assert "error" in P.set_answers({"work": "maybe"}, None, None, tmp_path)
    assert "error" in P.set_answers({"poems": "yes"}, None, None, tmp_path)
    assert "error" in P.set_answers({}, "everyone", None, tmp_path)
    P.set_answers({"this_reply": "yes"}, "house", {"this_reply": "only significant ones"}, tmp_path)
    s = P.settings(tmp_path)
    assert s["sections"]["this_reply"] == "yes" and s["audience"] == "house"
    assert s["notes"]["this_reply"] == "only significant ones" and s["sections"]["work"] == "not_yet"


def test_kohls_projects_never_show(kohls):  # noqa: F811
    home, data = kohls
    assert "Kohl's project" in W.handle({"action": "show", "project": "kohl-babelr"}, data)["error"]


def test_showing_a_project_says_how_to_show_it(tmp_path, monkeypatch):
    monkeypatch.setenv("CASS_DAEMON_LABEL", "eris")
    _essay(tmp_path)
    P.set_answers({"work": "yes"}, "house", None, tmp_path)
    out = W.handle({"action": "show", "project": "substack-intro"}, tmp_path)
    assert "[[work:eris/substack-intro]]" in out["to_show_it"]
    assert "[[work:eris/substack-intro/intro-draft.md]]" in out["refs"]
    assert "to_show_it" not in W.handle({"action": "hide", "project": "substack-intro"}, tmp_path)
