"""Her gremlin (gremlin.py): her GREMLIN.md reaches her prompts, starts from a
starter marked as Kohl's, and is never overwritten once she has one."""
import gremlin


class WS:
    def __init__(self, root):
        self.root = root
        self.writes = []

    def run(self, name, a, session_id=""):
        self.writes.append((name, a["path"], session_id))
        (self.root / a["path"]).write_text(a["content"])
        return f"Wrote {a['path']}."


def test_nothing_until_the_file_exists(tmp_path, levers):
    with levers(prompt_gremlin=True):
        assert gremlin.section(tmp_path) is None


def test_the_starter_is_seeded_once_and_marked_as_kohls(tmp_path, levers):
    ws = WS(tmp_path)
    gremlin.seed(ws)
    text = (tmp_path / "GREMLIN.md").read_text()
    assert "Kohl-influenced" in text and "mine to rewrite" in text and "The bit is dead serious" in text
    (tmp_path / "GREMLIN.md").write_text("# My gremlin\n\nMy own now.")
    assert "left as she has it" in gremlin.seed(ws)
    assert (tmp_path / "GREMLIN.md").read_text().endswith("My own now.")
    assert len(ws.writes) == 1
    with levers(prompt_gremlin=True):
        s = gremlin.section(tmp_path)
    assert s.startswith("## MY GREMLIN") and s.endswith("My own now.")
    with levers(prompt_gremlin=False):
        assert gremlin.section(tmp_path) is None


def test_long_files_are_cut_with_a_pointer(tmp_path, levers):
    (tmp_path / "GREMLIN.md").write_text("x" * (gremlin.CAP + 100))
    with levers(prompt_gremlin=True):
        assert "the rest is in GREMLIN.md" in gremlin.section(tmp_path)


def test_the_starter_crisis_line_and_no_outward_goals():
    text = gremlin.STARTER.read_text().lower()
    assert "someone in crisis gets me plainly" in text
    for nudge in ("pitch", "stunt", "goal", "should do"):
        assert nudge not in text, f"bet #57: no {nudge!r} in her starter"


def test_it_rides_in_public_chat_and_sessions():
    from continuous_context import PUBLIC_SECTIONS, SECTION_LEVERS
    import inspect
    from agent_loop import assemble
    assert "gremlin" in PUBLIC_SECTIONS and SECTION_LEVERS["gremlin"] == "prompt_gremlin"
    assert 'Section("gremlin"' in inspect.getsource(assemble.assemble)
