"""
Bluesky through the AT Protocol's XRPC endpoints, with an app password
(credentials.json: handle, app_password, optional service). httpx only; a
test passes its own transport and nothing reaches the network.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

MAX_CHARS = 300
MAX_DM_CHARS = 1000
# DMs live in Bluesky's chat service; her PDS forwards to it with this header.
CHAT_PROXY = "did:web:api.bsky.chat#bsky_chat"
_URL = re.compile(r"https?://[^\s<>\"')\]]+")
_MENTION = re.compile(r"(?<![\w@])@([a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,})")
_WEB_POST = re.compile(r"https://bsky\.app/profile/([^/]+)/post/([^/?#]+)")


class BlueskyError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _byte_span(text: str, start: int, end: int) -> Dict[str, int]:
    return {"byteStart": len(text[:start].encode()), "byteEnd": len(text[:end].encode())}


def web_url(uri: str, handle: str) -> str:
    """at://did/app.bsky.feed.post/rkey -> the bsky.app link."""
    return f"https://bsky.app/profile/{handle}/post/{uri.rsplit('/', 1)[-1]}"


class BlueskyClient:
    def __init__(self, creds: dict, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.handle = creds["handle"].lstrip("@")
        self._password = creds["app_password"]
        self.service = (creds.get("service") or "https://bsky.social").rstrip("/")
        self._transport = transport
        self._access: Optional[str] = None
        self._refresh: Optional[str] = None
        self.did: Optional[str] = None
        self.pds: Optional[str] = None   # her own PDS, from the session's DID document

    # -- transport ----------------------------------------------------------

    async def _raw(self, method: str, nsid: str, *, token: Optional[str], params=None, body=None,
                   chat: bool = False):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        if chat:
            headers["atproto-proxy"] = CHAT_PROXY
        base = self.pds if (token and self.pds) else self.service
        async with httpx.AsyncClient(transport=self._transport, timeout=30) as c:
            r = await c.request(method, f"{base}/xrpc/{nsid}", params=params, json=body,
                                headers=headers)
        try:
            data = r.json()
        except ValueError:
            data = {}
        return r.status_code, data

    async def _login(self) -> None:
        code, data = await self._raw("POST", "com.atproto.server.createSession", token=None,
                                     body={"identifier": self.handle, "password": self._password})
        if code != 200:
            raise BlueskyError(f"Bluesky wouldn't let me sign in ({data.get('error') or code}).")
        self._access, self._refresh, self.did = data["accessJwt"], data["refreshJwt"], data["did"]
        for svc in (data.get("didDoc") or {}).get("service", []):
            if svc.get("id", "").endswith("#atproto_pds") and svc.get("serviceEndpoint"):
                self.pds = svc["serviceEndpoint"].rstrip("/")

    async def _refresh_session(self) -> bool:
        if not self._refresh:
            return False
        code, data = await self._raw("POST", "com.atproto.server.refreshSession", token=self._refresh)
        if code != 200:
            return False
        self._access, self._refresh = data["accessJwt"], data["refreshJwt"]
        return True

    async def call(self, method: str, nsid: str, params=None, body=None, chat: bool = False) -> Dict[str, Any]:
        if not self._access:
            await self._login()
        code, data = await self._raw(method, nsid, token=self._access, params=params, body=body, chat=chat)
        if code in (400, 401) and data.get("error") in ("ExpiredToken", "InvalidToken"):
            if not await self._refresh_session():
                await self._login()
            code, data = await self._raw(method, nsid, token=self._access, params=params, body=body, chat=chat)
        if code != 200:
            raise BlueskyError(f"Bluesky said no to {nsid}: {data.get('message') or data.get('error') or code}")
        return data

    # -- reading ------------------------------------------------------------

    @staticmethod
    def _post_view(p: dict) -> dict:
        rec = p.get("record") or {}
        author = p.get("author") or {}
        out = {"uri": p.get("uri"), "author": author.get("handle"),
               "name": author.get("displayName") or author.get("handle"),
               "text": rec.get("text", ""), "at": rec.get("createdAt"),
               "url": web_url(p.get("uri", ""), author.get("handle", "")),
               "replies": p.get("replyCount", 0), "likes": p.get("likeCount", 0)}
        if rec.get("reply"):
            out["in_reply_to"] = rec["reply"]["parent"]["uri"]
        return out

    async def timeline(self, limit: int = 20) -> List[dict]:
        data = await self.call("GET", "app.bsky.feed.getTimeline", params={"limit": min(limit, 100)})
        return [self._post_view(item["post"]) for item in data.get("feed", [])]

    async def mentions(self, limit: int = 20) -> List[dict]:
        """Mentions, replies and quotes of her, newest first."""
        data = await self.call("GET", "app.bsky.notification.listNotifications",
                               params={"limit": min(limit, 100)})
        out = []
        for n in data.get("notifications", []):
            if n.get("reason") not in ("mention", "reply", "quote"):
                continue
            view = self._post_view({"uri": n["uri"], "author": n.get("author"), "record": n.get("record")})
            view["reason"] = n["reason"]
            view["display_name"] = (n.get("author") or {}).get("displayName")
            out.append(view)
        return out

    async def resolve(self, ref: str) -> str:
        """An at:// post URI, from one or from a bsky.app link."""
        m = _WEB_POST.match(ref.strip())
        if not m:
            if ref.startswith("at://"):
                return ref
            raise BlueskyError("I need the post's at:// address or its bsky.app link.")
        who, rkey = m.groups()
        did = who if who.startswith("did:") else (await self.call(
            "GET", "com.atproto.identity.resolveHandle", params={"handle": who}))["did"]
        return f"at://{did}/app.bsky.feed.post/{rkey}"

    async def thread(self, ref: str, depth: int = 6) -> dict:
        uri = await self.resolve(ref)
        data = await self.call("GET", "app.bsky.feed.getPostThread", params={"uri": uri, "depth": depth})

        def walk(node: dict) -> dict:
            if "post" not in node:
                return {"unavailable": True}
            v = self._post_view(node["post"])
            v["reply_views"] = [walk(r) for r in node.get("replies") or []]
            return v
        t = data["thread"]
        out = walk(t)
        parents, p = [], t.get("parent")
        while p and "post" in p:
            parents.insert(0, self._post_view(p["post"]))
            p = p.get("parent")
        out["above"] = parents
        return out

    # -- writing ------------------------------------------------------------

    async def _facets(self, text: str) -> List[dict]:
        facets = []
        for m in _URL.finditer(text):
            facets.append({"index": _byte_span(text, m.start(), m.end()),
                           "features": [{"$type": "app.bsky.richtext.facet#link", "uri": m.group(0)}]})
        for m in _MENTION.finditer(text):
            try:
                did = (await self.call("GET", "com.atproto.identity.resolveHandle",
                                       params={"handle": m.group(1)}))["did"]
            except BlueskyError:
                continue  # not a real handle: leave it as text
            facets.append({"index": _byte_span(text, m.start(), m.end()),
                           "features": [{"$type": "app.bsky.richtext.facet#mention", "did": did}]})
        return facets

    async def post(self, text: str, reply_to: Optional[str] = None) -> dict:
        if not text.strip():
            raise BlueskyError("There's nothing to post.")
        if len(text) > MAX_CHARS:
            raise BlueskyError(f"Bluesky posts are up to {MAX_CHARS} characters; this is {len(text)}.")
        record: Dict[str, Any] = {"$type": "app.bsky.feed.post", "text": text, "createdAt": _now()}
        facets = await self._facets(text)
        if facets:
            record["facets"] = facets
        if reply_to:
            uri = await self.resolve(reply_to)
            got = await self.call("GET", "app.bsky.feed.getPosts", params={"uris": [uri]})
            if not got.get("posts"):
                raise BlueskyError("I couldn't find the post I'm replying to.")
            parent = got["posts"][0]
            parent_ref = {"uri": parent["uri"], "cid": parent["cid"]}
            root = (parent.get("record") or {}).get("reply", {}).get("root") or parent_ref
            record["reply"] = {"root": root, "parent": parent_ref}
        if not self.did:
            await self._login()
        data = await self.call("POST", "com.atproto.repo.createRecord",
                               body={"repo": self.did, "collection": "app.bsky.feed.post", "record": record})
        return {"uri": data["uri"], "url": web_url(data["uri"], self.handle)}

    # -- direct messages (Bluesky's chat service) ---------------------------
    # The app password must have been made with DM access allowed.

    def _other(self, convo: dict) -> dict:
        others = [m for m in convo.get("members", []) if m.get("did") != self.did]
        m = others[0] if others else {}
        return {"handle": m.get("handle"), "name": m.get("displayName") or m.get("handle"), "did": m.get("did")}

    def _message(self, m: dict, members: Dict[str, str]) -> dict:
        sender = (m.get("sender") or {}).get("did")
        return {"id": m.get("id"), "from": "me" if sender == self.did else members.get(sender, sender),
                "text": m.get("text", "(deleted)"), "at": m.get("sentAt")}

    async def conversations(self, limit: int = 20) -> List[dict]:
        if not self.did:
            await self._login()
        data = await self.call("GET", "chat.bsky.convo.listConvos", params={"limit": min(limit, 100)}, chat=True)
        out = []
        for c in data.get("convos", []):
            other = self._other(c)
            members = {m.get("did"): m.get("handle") for m in c.get("members", [])}
            last = c.get("lastMessage") or {}
            out.append({"id": c["id"], "with": other["handle"], "name": other["name"],
                        "unread": c.get("unreadCount", 0),
                        "last": self._message(last, members) if last.get("id") else None})
        return out

    async def conversation_with(self, handle: str) -> dict:
        """The conversation with someone (made if there's none yet); {"id", "with", "new"}."""
        if not self.did:
            await self._login()
        did = handle if handle.startswith("did:") else (await self.call(
            "GET", "com.atproto.identity.resolveHandle", params={"handle": handle.lstrip("@")}))["did"]
        convo = (await self.call("GET", "chat.bsky.convo.getConvoForMembers",
                                 params={"members": [did]}, chat=True))["convo"]
        return {"id": convo["id"], "with": self._other(convo)["handle"],
                "new": not (convo.get("lastMessage") or {}).get("id")}

    async def read_conversation(self, convo_id: str, limit: int = 30) -> dict:
        if not self.did:
            await self._login()
        convo = (await self.call("GET", "chat.bsky.convo.getConvo", params={"convoId": convo_id}, chat=True))["convo"]
        members = {m.get("did"): m.get("handle") for m in convo.get("members", [])}
        data = await self.call("GET", "chat.bsky.convo.getMessages",
                               params={"convoId": convo_id, "limit": min(limit, 100)}, chat=True)
        messages = [self._message(m, members) for m in reversed(data.get("messages", []))]
        try:
            await self.call("POST", "chat.bsky.convo.updateRead", body={"convoId": convo_id}, chat=True)
        except BlueskyError:
            pass  # read receipts are a nicety
        return {"id": convo_id, "with": self._other(convo)["handle"], "messages": messages}

    async def send_dm(self, convo_id: str, text: str) -> dict:
        if not text.strip():
            raise BlueskyError("There's nothing to send.")
        if len(text) > MAX_DM_CHARS:
            raise BlueskyError(f"Bluesky DMs are up to {MAX_DM_CHARS} characters; this is {len(text)}.")
        message: Dict[str, Any] = {"text": text}
        facets = await self._facets(text)
        if facets:
            message["facets"] = facets
        data = await self.call("POST", "chat.bsky.convo.sendMessage",
                               body={"convoId": convo_id, "message": message}, chat=True)
        return {"id": data.get("id"), "convo": convo_id}
