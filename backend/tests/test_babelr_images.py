"""Pictures sent on Babelr reach her: named in the text, and the newest one attached to her turn."""
import base64

from babelr_organ.organ import BabelrOrgan
from babelr_organ.triggers import BabelrEvent, words

PNG = {"url": "/uploads/raven.png", "filename": "raven.png", "contentType": "image/png"}


def ev(text="look", attachments=()):
    return BabelrEvent(kind="dm", place="dm:1", place_label="DM with @kohl", message_id="m", author_id="a",
                       author_name="kohl", text=text, published="", dm_id="1", attachments=list(attachments))


class FakeClient:
    def __init__(self, fail=False):
        self.fail, self.fetched = fail, []

    def fetch(self, url, max_bytes=None):
        self.fetched.append(url)
        if self.fail:
            raise OSError("gone")
        return b"\x89PNG..."


def organ(client):
    o = object.__new__(BabelrOrgan)
    o.client = client
    return o


def test_words_name_the_picture_even_without_text():
    assert words(ev("which one?", [PNG])) == "which one?\n[sent a picture: raven.png]"
    assert words(ev("", [PNG])) == "[sent a picture: raven.png]"
    assert words(ev("hi")) == "hi"


def test_the_newest_picture_is_fetched_and_encoded():
    c = FakeClient()
    older = dict(PNG, url="/uploads/a.png", filename="a.png")
    img = organ(c)._image([ev(attachments=[older]), ev(attachments=[PNG, {"url": "/uploads/x.pdf", "contentType": "application/pdf"}])])
    assert img == {"data": base64.b64encode(b"\x89PNG...").decode(), "media_type": "image/png", "filename": "raven.png"}
    assert c.fetched == ["/uploads/raven.png"]


def test_no_picture_or_a_failed_fetch_gives_none():
    assert organ(FakeClient())._image([ev()]) is None
    assert organ(FakeClient(fail=True))._image([ev(attachments=[PNG])]) is None


def test_a_big_picture_is_scaled_to_a_jpeg():
    import io
    from PIL import Image
    from babelr_organ.organ import _fit
    buf = io.BytesIO()
    Image.effect_noise((2400, 2400), 100).convert("RGB").save(buf, "PNG")
    data, media = _fit(buf.getvalue(), "image/png")
    assert len(buf.getvalue()) > 3_500_000 and media == "image/jpeg" and len(data) < 3_500_000
    assert Image.open(io.BytesIO(data)).size == (1568, 1568)
