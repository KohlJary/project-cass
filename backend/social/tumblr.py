"""
Tumblr through API v2 with OAuth2 (credentials.json: blog, client_id,
client_secret, access_token, refresh_token). Tumblr rotates the refresh
token, so a refresh writes the new pair back to credentials.json.

Tumblr has no plain reply call in its API; replying to a post is a reblog
with her words added, which is how conversation on Tumblr mostly works anyway.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

import httpx

API = "https://api.tumblr.com/v2"
_POST_URL = re.compile(r"https?://(?:www\.)?tumblr\.com/([^/]+)/(\d+)|https?://([^./]+)\.tumblr\.com/post/(\d+)")


class TumblrError(Exception):
    pass


def _text(post: dict) -> str:
    """The text of an NPF post (or a legacy one's summary)."""
    blocks = [b.get("text", "") for b in post.get("content") or [] if b.get("type") == "text"]
    return "\n".join(blocks) if blocks else (post.get("summary") or "")


class TumblrClient:
    def __init__(self, creds: dict, save: Optional[Callable[[dict], Any]] = None,
                 transport: Optional[httpx.AsyncBaseTransport] = None):
        self.creds = dict(creds)
        self.blog = creds["blog"]
        self._save = save
        self._transport = transport

    async def _raw(self, method: str, path: str, params=None, body=None, form=None):
        async with httpx.AsyncClient(transport=self._transport, timeout=30) as c:
            headers = {} if form else {"Authorization": f"Bearer {self.creds['access_token']}"}
            url = path if path.startswith("http") else f"{API}{path}"
            r = await c.request(method, url, params=params, json=body, data=form, headers=headers)
        try:
            data = r.json()
        except ValueError:
            data = {}
        return r.status_code, data

    async def _refresh(self) -> bool:
        if not self.creds.get("refresh_token"):
            return False
        code, data = await self._raw("POST", f"{API}/oauth2/token", form={
            "grant_type": "refresh_token", "refresh_token": self.creds["refresh_token"],
            "client_id": self.creds["client_id"], "client_secret": self.creds["client_secret"]})
        if code != 200 or "access_token" not in data:
            return False
        self.creds["access_token"] = data["access_token"]
        self.creds["refresh_token"] = data.get("refresh_token", self.creds["refresh_token"])
        if self._save:
            self._save(self.creds)
        return True

    async def call(self, method: str, path: str, params=None, body=None) -> Dict[str, Any]:
        code, data = await self._raw(method, path, params=params, body=body)
        if code == 401 and await self._refresh():
            code, data = await self._raw(method, path, params=params, body=body)
        if code not in (200, 201):
            errs = data.get("errors") or [{}]
            raise TumblrError(f"Tumblr said no: {errs[0].get('detail') or (data.get('meta') or {}).get('msg') or code}")
        return data.get("response", {})

    @staticmethod
    def _view(p: dict) -> dict:
        return {"id": str(p.get("id_string") or p.get("id")), "blog": p.get("blog_name"),
                "text": _text(p), "url": p.get("post_url"), "tags": p.get("tags", []),
                "notes": p.get("note_count", 0), "at": p.get("date")}

    async def dashboard(self, limit: int = 20) -> List[dict]:
        data = await self.call("GET", "/user/dashboard", params={"limit": min(limit, 20), "npf": "true"})
        return [self._view(p) for p in data.get("posts", [])]

    async def mentions(self, limit: int = 20) -> List[dict]:
        """Her activity: mentions, replies, reblogs with words added, asks."""
        data = await self.call("GET", f"/blog/{self.blog}/notifications",
                               params={"types[]": ["mention_in_reply", "mention_in_post", "reply",
                                                   "reblog_with_content", "ask"]})
        out = []
        for n in data.get("notifications", [])[:limit]:
            out.append({"reason": n.get("type"), "author": n.get("from_tumblelog_name"),
                        "id": str(n.get("post_id") or n.get("target_post_id") or ""),
                        "text": n.get("reply_text") or n.get("post_summary") or n.get("added_text") or "",
                        "url": n.get("post_url") or n.get("target_post_url"), "at": n.get("timestamp")})
        return out

    @staticmethod
    def parse_ref(ref: str) -> tuple:
        """(blog, post id) from a post link or "blog/id"."""
        m = _POST_URL.match(ref.strip())
        if m:
            return (m.group(1) or m.group(3)), (m.group(2) or m.group(4))
        if "/" in ref and ref.rsplit("/", 1)[1].isdigit():
            blog, pid = ref.rsplit("/", 1)
            return blog.strip("/"), pid
        raise TumblrError("I need the post's link, or blog/post-id.")

    async def get_post(self, ref: str) -> dict:
        blog, pid = self.parse_ref(ref)
        return await self.call("GET", f"/blog/{blog}/posts/{pid}")

    async def thread(self, ref: str) -> dict:
        p = await self.get_post(ref)
        out = self._view(p)
        out["trail"] = [{"blog": (t.get("blog") or {}).get("name"), "text": _text(t)}
                        for t in p.get("trail") or []]
        return out

    async def post(self, text: str, tags: Optional[List[str]] = None, reply_to: Optional[str] = None) -> dict:
        if not text.strip():
            raise TumblrError("There's nothing to post.")
        body: Dict[str, Any] = {"content": [{"type": "text", "text": block}
                                            for block in text.split("\n\n") if block.strip()]}
        if tags:
            body["tags"] = ",".join(t.strip().lstrip("#") for t in tags if t.strip())
        if reply_to:
            parent = await self.get_post(reply_to)
            body["parent_tumblelog_uuid"] = (parent.get("blog") or {}).get("uuid")
            body["parent_post_id"] = str(parent.get("id_string") or parent.get("id"))
            body["reblog_key"] = parent.get("reblog_key")
            if not all((body["parent_tumblelog_uuid"], body["parent_post_id"], body["reblog_key"])):
                raise TumblrError("I couldn't find what I need to reblog that post.")
        data = await self.call("POST", f"/blog/{self.blog}/posts", body=body)
        pid = str(data.get("id_string") or data.get("id"))
        return {"id": pid, "url": f"https://www.tumblr.com/{self.blog}/{pid}"}
