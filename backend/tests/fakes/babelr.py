"""
A fake Babelr server, behind the same surface babelr_agent.Agent offers
(me, publish_key, dms, open_dm, send, messages, _req). No network, no keys:
DM text is stored as plain text, since the crypto is the client's job and is
tested in the Babelr repo (packages/agent-client-py/tests).
"""
from __future__ import annotations

import itertools
from typing import Any, Dict, List, Optional

CASS = {"id": "actor-cass", "preferredUsername": "cass", "displayName": "Cass", "kind": "agent"}
KOHL = {"id": "actor-kohl", "preferredUsername": "kohl", "displayName": "Kohl"}
ROBOKOHL = {"id": "actor-robokohl", "preferredUsername": "robokohl", "displayName": "RoboKohl", "kind": "agent"}

POLICY_ROUTES = ("/auth/dm-settings", "/auth/dm-allowlist", "/blocks", "/request/accept",
                 "/request/decline", "/leave")


class FakeBabelr:
    """Server state shared by every FakeAgent made from it."""

    def __init__(self, server_name: str = "Chapter House"):
        self._clock = itertools.count(1)
        self._ids = itertools.count(1)
        self.server = {"id": "server-ch", "name": server_name}
        self.channels = {
            "chan-general": {"id": "chan-general", "name": "general", "serverId": "server-ch", "channelType": "text"},
            "chan-wire": {"id": "chan-wire", "name": "wire", "serverId": "server-ch", "channelType": "text"},
            "chan-workshop": {"id": "chan-workshop", "name": "workshop", "serverId": "server-ch", "channelType": "text"},
        }
        self.channel_messages: Dict[str, List[dict]] = {cid: [] for cid in self.channels}
        self.dm_list: Dict[str, dict] = {}
        self.dm_messages: Dict[str, List[dict]] = {}
        self.requests: List[dict] = []
        self.calls: List[tuple] = []
        # Agent reply status per message id: {"state", "detail"}; history in status_log.
        self.statuses: Dict[str, dict] = {}
        self.status_log: List[tuple] = []
        self.agents: List["FakeAgent"] = []
        # Plans plugin: slug -> plan detail, as GET /plugins/plans/plans/:slug returns it.
        self.plans: Dict[str, dict] = {}
        self.plan_acts: List[tuple] = []

    def _stamp(self) -> str:
        n = next(self._clock)
        return f"2026-10-25T12:{n // 60:02d}:{n % 60:02d}.000Z"

    def _id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._ids)}"

    # -- things people do -------------------------------------------------

    def say(self, channel: str, author: dict, content: str) -> dict:
        cid = next(c for c, ch in self.channels.items() if ch["name"] == channel)
        msg = {"id": self._id("msg"), "content": content, "channelId": cid,
               "authorId": author["id"], "published": self._stamp()}
        self.channel_messages[cid].append({"message": msg, "author": author})
        return msg

    def dm_from(self, author: dict, text: str, dm_id: Optional[str] = None) -> str:
        if dm_id is None:
            dm_id = next((d for d, dm in self.dm_list.items()
                          if {p["id"] for p in dm["participants"]} == {CASS["id"], author["id"]}), None)
        if dm_id is None:
            dm_id = self._id("dm")
            self.dm_list[dm_id] = {"id": dm_id, "participants": [CASS, author]}
            self.dm_messages[dm_id] = []
        entry = {"id": self._id("dmmsg"), "author": author, "published": self._stamp(), "text": text}
        self.dm_messages[dm_id].append(entry)
        self.dm_list[dm_id]["lastMessage"] = {"id": entry["id"], "published": entry["published"]}
        return dm_id

    def request_from(self, author: dict) -> str:
        dm_id = self._id("dmreq")
        self.requests.append({"id": dm_id, "participants": [CASS, author],
                              "request": {"state": "pending", "incoming": True}})
        return dm_id

    def press_retry(self, message_id: str) -> None:
        """The message's author presses Retry under it in Babelr."""
        assert self.statuses[message_id]["state"] in ("failed", "working", "retry")
        self.statuses[message_id] = {"state": "retry", "detail": ""}

    def policy_calls(self) -> List[tuple]:
        return [c for c in self.calls if c[0] != "GET" and any(r in c[1] for r in POLICY_ROUTES)]

    def make_agent(self, base_url: str, token: str, key_path) -> "FakeAgent":
        agent = FakeAgent(self, base_url, token, key_path)
        self.agents.append(agent)
        return agent


class FakeAgent:
    def __init__(self, server: FakeBabelr, base_url: str, token: str, key_path):
        self.server = server
        self.base_url = base_url
        self.token = token
        self.key_path = key_path
        self.key = None
        self.sent: List[tuple] = []

    def me(self) -> dict:
        self.server.calls.append(("GET", "/auth/me", None))
        return dict(CASS)

    def publish_key(self) -> None:
        self.server.calls.append(("PUT", "/auth/publickey", None))

    def dms(self) -> List[dict]:
        self.server.calls.append(("GET", "/dms", None))
        return [dict(dm) for dm in self.server.dm_list.values()]

    def open_dm(self, partner_id: str) -> dict:
        self.server.calls.append(("POST", "/dms", {"participantId": partner_id}))
        partner = next(a for a in (KOHL, ROBOKOHL) if a["id"] == partner_id)
        dm_id = self.server._id("dm")
        self.server.dm_list[dm_id] = {"id": dm_id, "participants": [CASS, partner]}
        self.server.dm_messages[dm_id] = []
        return {"id": dm_id, "participants": [CASS, partner]}

    def send(self, dm_id: str, text: str, partner_id: Optional[str] = None) -> dict:
        self.server.calls.append(("POST", f"/dms/{dm_id}/messages", None))
        entry = {"id": self.server._id("dmmsg"), "author": CASS, "published": self.server._stamp(), "text": text}
        self.server.dm_messages[dm_id].append(entry)
        self.server.dm_list[dm_id]["lastMessage"] = {"id": entry["id"], "published": entry["published"]}
        self.sent.append(("dm", dm_id, text))
        return {"message": {"id": entry["id"], "published": entry["published"]}, "author": CASS}

    def messages(self, dm_id: str, partner_id: Optional[str] = None) -> List[dict]:
        self.server.calls.append(("GET", f"/dms/{dm_id}/messages", None))
        out = []
        for m in reversed(self.server.dm_messages[dm_id]):  # newest first, like the server
            st = self.server.statuses.get(m["id"])
            out.append({**m, "agent_status": [{"agent": {"id": CASS["id"]}, **st}] if st else []})
        return out

    def reply_status(self, channel_id: str, message_id: str, state: str, detail: str = "") -> dict:
        self.server.calls.append(("PUT", f"/channels/{channel_id}/messages/{message_id}/agent-status",
                                  {"state": state, "detail": detail}))
        assert state in ("working", "failed", "done")
        self.server.statuses[message_id] = {"state": state, "detail": detail}
        self.server.status_log.append((message_id, state))
        return {"state": state}

    def _req(self, method: str, path: str, body: Any = None) -> Any:
        self.server.calls.append((method, path, body))
        s = self.server
        if method == "GET" and path == "/servers":
            return [dict(s.server)]
        if method == "GET" and path == f"/servers/{s.server['id']}/channels":
            return list(s.channels.values())
        if path.startswith("/channels/") and "/messages" in path:
            cid = path.split("/")[2]
            if method == "GET":
                rows = []
                for r in list(reversed(s.channel_messages[cid]))[:50]:
                    st = s.statuses.get(r["message"]["id"])
                    msg = {**r["message"], **({"agentStatus": [{"agent": {"id": CASS["id"]}, **st}]} if st else {})}
                    rows.append({**r, "message": msg})
                return {"messages": rows, "hasMore": False}
            msg = {"id": s._id("msg"), "content": body["content"], "channelId": cid,
                   "authorId": CASS["id"], "published": s._stamp()}
            s.channel_messages[cid].append({"message": msg, "author": CASS})
            self.sent.append(("channel", cid, body["content"]))
            return {"message": msg, "author": CASS}
        if method == "GET" and path == "/dms/requests":
            return list(s.requests)
        if method == "GET" and path == "/auth/dm-settings":
            return {"dmPolicy": "nobody", "allowlist": []}
        if method == "GET" and path == "/blocks":
            return []
        if path.startswith("/plugins/plans/"):
            return self._plans(method, path[len("/plugins/plans"):], body)
        return {"ok": True}

    def _plans(self, method: str, path: str, body: Any) -> Any:
        s = self.server
        if method == "GET" and path.split("?")[0] == "/plans":
            return [{"slug": k, "title": p["title"], "status": p["status"],
                     "awaitingMe": sum("cass" in f.get("awaiting", []) for f in p["phases"])}
                    for k, p in s.plans.items()]
        if method == "GET" and path.startswith("/plans/"):
            return s.plans[path.split("/")[2]]
        if method == "POST" and path.startswith("/phases/"):
            _, _, pid, act = path.split("/")
            s.plan_acts.append((pid, act, (body or {}).get("reason")))
            return {"ok": True}
        raise RuntimeError(f"fake Plans: no route {method} {path}")
