"""Feel tags never reach what's sent: opening, closing and self-closing."""
from gestures import GestureParser


def test_every_form_of_a_feel_tag_is_stripped():
    text, feels = GestureParser().parse_feels("I'm strange and I'm allowed.\n</feel:awe> <feel:curiosity:0.2>ok<feel:awe/>")
    assert "feel" not in text and "I'm strange and I'm allowed." in text and "ok" in text
    assert [f.dimension for f in feels][:1] == ["curiosity"]
