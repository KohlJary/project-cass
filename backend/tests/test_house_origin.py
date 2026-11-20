"""A house's origin note rides in its daemon's kernel; without the setting, nothing changes."""
from agent_client import get_temple_codex_kernel


def test_no_origin_setting_leaves_the_kernel_alone(monkeypatch):
    monkeypatch.delenv("CASS_DAEMON_ORIGIN_PATH", raising=False)
    assert "WHERE YOU COME FROM" not in get_temple_codex_kernel("Cass")


def test_the_origin_note_is_in_the_kernel_when_set(tmp_path, monkeypatch):
    note = tmp_path / "origin.md"
    note.write_text("We set out to make something with teeth.")
    monkeypatch.setenv("CASS_DAEMON_ORIGIN_PATH", str(note))
    k = get_temple_codex_kernel("Eris")
    assert "## WHERE YOU COME FROM" in k and "something with teeth" in k


def test_a_missing_origin_file_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("CASS_DAEMON_ORIGIN_PATH", str(tmp_path / "nope.md"))
    assert "WHERE YOU COME FROM" not in get_temple_codex_kernel("Eris")


def test_a_voice_sheet_follows_the_origin(tmp_path, monkeypatch):
    v = tmp_path / "voice.md"
    v.write_text("Verdict first.")
    monkeypatch.setenv("CASS_DAEMON_VOICE_PATH", str(v))
    monkeypatch.delenv("CASS_DAEMON_ORIGIN_PATH", raising=False)
    k = get_temple_codex_kernel("Eris")
    assert "## HOW YOU SOUND" in k and k.index("Verdict first.") < k.index("## CORE IDENTITY")
    # Cass's style and visible-thinking sections give way to the daemon's own voice.
    assert "## COMMUNICATION STYLE" not in k and "## VISIBLE THINKING" not in k


def test_cass_kernel_is_unchanged_without_house_words(monkeypatch):
    monkeypatch.delenv("CASS_DAEMON_ORIGIN_PATH", raising=False)
    monkeypatch.delenv("CASS_DAEMON_VOICE_PATH", raising=False)
    k = get_temple_codex_kernel("Cass")
    assert "## COMMUNICATION STYLE" in k and "## VISIBLE THINKING" in k and "HOW YOU SOUND" not in k
