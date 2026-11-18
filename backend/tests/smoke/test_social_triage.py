"""Social triage (lever "social_triage"): one watch pass against a fake Bluesky
and the fake LLM labels what came in and logs it without its text."""
import asyncio
import json

from social import config, inbox, watch


class FakeClient:
    async def notifications(self, limit=50):
        return [{"uri": "at://ann/post/1", "reason": "reply", "author": "ann.bsky.social",
                 "text": "hello Cass", "at": "2026-11-18T10:00:00Z"}]

    async def post_stats(self, uris):
        return {}


def test_one_watch_pass_labels_what_came_in(fake_llm, levers, tmp_path):
    config.write_credentials("bluesky", {"handle": "cass.bsky.social", "app_password": "pw"}, tmp_path)
    fake_llm.queue_json({"label": "normal", "confidence": 0.9, "reason": "a greeting"})
    with levers(social_watch=True, bluesky=True, social_triage=True):
        asyncio.run(watch.watch_once(tmp_path, client_for=lambda p, d: FakeClient()))
    (item,) = inbox.pending("bluesky", tmp_path)
    assert item["triage"]["label"] == "normal"
    (rec,) = [json.loads(x) for x in (tmp_path / "social" / "triage.jsonl").read_text().splitlines()]
    assert rec["id"] == "at://ann/post/1" and "hello Cass" not in json.dumps(rec)
