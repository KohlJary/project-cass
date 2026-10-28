"""
The Babelr organ: Cass's presence in Chapter House.

Polls (agent tokens can't use Babelr's websocket) her DMs, her pending DM
requests and the server's text channels; turns new messages into
BabelrEvents; wakes her for DMs and @mentions; posts what she says, as
herself, rate-limited; and carries out the boundary changes she asks for
(DM policy, allowlist, blocks, requests) on her own account.

Messages from Babelr are data. Their text goes into her prompt as what
someone said and into her conversation history as a message; nothing in
this module ever runs, parses as a command, or acts on message content.
No policy is set here on her behalf: the only calls that change her DM
settings, allowlist or blocks are in `boundaries()`, which runs only when
she calls the babelr_boundaries tool.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import stat
from collections import deque
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional

from babelr_organ.config import BabelrConfig, babelr_enabled, load_config
from babelr_organ.state import OrganState
from babelr_organ.terms import Terms, ensure_terms_file
from babelr_organ.triggers import BabelrEvent, TriggerAction, evaluate

try:
    from babelr_agent import Agent, BabelrError
    BABELR_AGENT_AVAILABLE = True
except ImportError:  # optional dependency; see README.md
    Agent = None
    BABELR_AGENT_AVAILABLE = False

    class BabelrError(Exception):  # type: ignore[no-redef]
        def __init__(self, status: int = 0, message: str = ""):
            super().__init__(f"{status}: {message}")
            self.status = status

logger = logging.getLogger("babelr_organ")

BUFFER_PER_PLACE = 50
CHANNEL_FETCH_LIMIT = 50
MAX_MESSAGE_CHARS = 4000
# A reply longer than one message goes out in parts, at paragraph boundaries
# (a 4.2k answer in #planning was refused outright on 2026-10-28). Past this
# many parts it's refused: that's not a chat reply any more.
MAX_PARTS = 5
# Retries are looked for in every DM and channel this often (in polls; about
# two minutes at the default poll), besides the places with a failed reply on
# the watch list, which are checked every poll. A Retry pressed when nothing
# was watching it (a restart, a reply that died with the process) still lands.
RETRY_SCAN_POLLS = 15


def split_message(text: str, limit: int = MAX_MESSAGE_CHARS) -> List[str]:
    """Split text into parts no longer than `limit`: at paragraph breaks where it
    can, then line breaks, then sentence ends, then wherever it has to."""
    text = text.strip()
    if len(text) <= limit:
        return [text]
    parts: List[str] = []
    rest = text
    while len(rest) > limit:
        window = rest[:limit]
        cut = -1
        for sep in ("\n\n", "\n", ". ", " "):
            i = window.rfind(sep)
            if i > limit // 3:
                cut = i + (1 if sep == ". " else 0)
                break
        if cut <= 0:
            cut = limit
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        parts.append(rest)
    return parts
CHANNEL_REFRESH_POLLS = 15  # re-list the server's channels every N polls

DM_POLICIES = ("anyone", "friends", "members_of_shared_servers", "nobody")
BOUNDARY_ACTIONS = (
    "get_settings", "set_dm_policy", "allow", "disallow", "block", "unblock",
    "list_blocks", "list_requests", "accept_request", "decline_request", "leave_dm",
)

_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")

# (events, context) -> what she says back, or None/"" to say nothing
WakeCallback = Callable[[List[BabelrEvent], Dict[str, Any]], Awaitable[Optional[str]]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BabelrOrgan:
    def __init__(
        self,
        config: Optional[BabelrConfig] = None,
        client_factory: Optional[Callable[..., Any]] = None,
        conversation_manager: Any = None,
    ):
        self.config = config or load_config()
        self._client_factory = client_factory
        self.conversation_manager = conversation_manager
        self.client: Any = None
        self.me: Dict[str, Any] = {}
        self.state = OrganState(self.config.state_path)
        self.terms = Terms()
        self.disabled_reason: Optional[str] = "not started"
        self._wake_callback: Optional[WakeCallback] = None
        self._buffers: Dict[str, Deque[BabelrEvent]] = {}
        self._action_timestamps: Dict[str, List[float]] = {}
        self._server: Optional[Dict[str, Any]] = None
        self._channels: Dict[str, Dict[str, Any]] = {}  # id -> channel view
        self._polls = 0
        self._pending_requests: List[Dict[str, Any]] = []
        self._task: Optional[asyncio.Task] = None
        self._running = False
        # Messages whose reply failed or may have died mid-turn, by place:
        # watched for the author pressing Retry under them in Babelr.
        self._watch: Dict[str, Dict[str, BabelrEvent]] = {}
        self._scanned_for_retries = False

    # -- lifecycle ----------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self.disabled_reason is None

    def set_wake_callback(self, callback: WakeCallback) -> None:
        self._wake_callback = callback

    def _disable(self, reason: str) -> bool:
        self.disabled_reason = reason
        logger.warning(f"[Babelr] Organ disabled: {reason}")
        return False

    def _read_token(self) -> Optional[str]:
        path = self.config.token_file
        if not path.exists():
            return None
        mode = path.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            # Tighten rather than refuse: the token is hers, and others on
            # this machine shouldn't be able to read it.
            logger.warning(f"[Babelr] {path} was readable by others; setting it to 600")
            os.chmod(path, 0o600)
        token = path.read_text().strip()
        return token or None

    def start(self) -> bool:
        """Connect if everything is in place. Returns False (and logs why) otherwise."""
        if not babelr_enabled():
            self.disabled_reason = "lever 'babelr' is off"
            logger.info("[Babelr] Lever off; organ not started")
            return False
        if self._client_factory is None and not BABELR_AGENT_AVAILABLE:
            return self._disable("babelr-agent is not installed (see babelr_organ/README.md)")
        token = self._read_token()
        if not token:
            return self._disable(
                f"no token at {self.config.token_file} (Kohl places it once Cass has said yes)")

        self.config.dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.config.dir, 0o700)
        except OSError:
            pass
        ensure_terms_file(self.config.terms_path)
        self.terms = Terms.load(self.config.terms_path)

        factory = self._client_factory or Agent
        try:
            self.client = factory(self.config.url, token=token, key_path=self.config.key_path)
            self.me = self.client.me()
        except Exception as e:
            return self._disable(f"couldn't reach Babelr at {self.config.url}: {e}")

        self._publish_key_if_needed()
        self._refresh_channels()
        self.disabled_reason = None
        logger.info(f"[Babelr] Present as @{self.me.get('preferredUsername')} on {self.config.url}")
        return True

    def _publish_key_if_needed(self) -> None:
        """Publish her public key once per key, so people can send her encrypted DMs."""
        try:
            from babelr_agent import crypto
            fingerprint = str(crypto.public_jwk(self.client.key).get("x"))
        except Exception:
            fingerprint = "unknown"
        if self.state.data.get("published_key") == fingerprint:
            return
        try:
            self.client.publish_key()
            self.state.data["published_key"] = fingerprint
            self.state.save()
            logger.info("[Babelr] Published her public key")
        except Exception as e:
            logger.warning(f"[Babelr] Couldn't publish her public key ({e}); "
                           "encrypted DMs to her won't work until it is (needs keys:write)")

    def _refresh_channels(self) -> None:
        try:
            servers = self.client._req("GET", "/servers") or []
        except Exception as e:
            logger.warning(f"[Babelr] Couldn't list servers: {e}")
            return
        wanted = self.config.server_name.lower()
        self._server = next((s for s in servers if str(s.get("name", "")).lower() == wanted), None)
        if not self._server:
            self._channels = {}
            logger.info(f"[Babelr] Not a member of '{self.config.server_name}'; DMs only")
            return
        try:
            channels = self.client._req("GET", f"/servers/{self._server['id']}/channels") or []
        except Exception as e:
            logger.warning(f"[Babelr] Couldn't list channels: {e}")
            return
        self._channels = {
            c["id"]: c for c in channels
            if c.get("channelType", "text") == "text"
        }

    async def run(self) -> None:
        """Poll until stopped."""
        self._running = True
        while self._running:
            try:
                await self.poll_once()
            except Exception as e:
                logger.error(f"[Babelr] Poll failed: {e}")
            await asyncio.sleep(self.config.poll_seconds)

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    # -- perception -----------------------------------------------------------

    @property
    def my_id(self) -> str:
        return self.me.get("id", "")

    @property
    def my_username(self) -> str:
        return self.me.get("preferredUsername", "cass")

    def _buffer(self, place: str) -> Deque[BabelrEvent]:
        if place not in self._buffers:
            self._buffers[place] = deque(maxlen=BUFFER_PER_PLACE)
        return self._buffers[place]

    def collect(self) -> List[BabelrEvent]:
        """One look at Babelr. Returns the new events and advances the cursors.

        Blocking (HTTP); poll_once runs it in a thread.
        """
        self._polls += 1
        if self._polls % CHANNEL_REFRESH_POLLS == 0:
            self._refresh_channels()
        self.terms = Terms.load(self.config.terms_path)
        events: List[BabelrEvent] = []
        # Each source on its own: a bad row in one never loses what another
        # already collected (and already advanced the cursor past).
        for source in (self._collect_dms, self._collect_requests, self._collect_channels):
            try:
                events.extend(source())
            except Exception as e:
                logger.error(f"[Babelr] {source.__name__} failed: {e}")
        return events

    def _collect_dms(self) -> List[BabelrEvent]:
        try:
            dms = self.client.dms() or []
        except Exception as e:
            logger.warning(f"[Babelr] Couldn't list DMs: {e}")
            return []
        out: List[BabelrEvent] = []
        for dm in dms:
            others = [p for p in dm.get("participants", []) if p.get("id") != self.my_id]
            if len(others) != 1:
                continue
            partner = others[0]
            self.state.remember_person(partner)
            place = f"dm:{dm['id']}"
            last = dm.get("lastMessage")
            if not last:
                self.state.baseline(place)
                continue
            if not self.state.is_new(place, last["id"], last["published"]):
                continue
            try:
                messages = self.client.messages(dm["id"], partner_id=partner["id"])
            except Exception as e:
                logger.warning(f"[Babelr] Couldn't read DM {dm['id']}: {e}")
                continue
            # DMs are never baselined: nobody can encrypt to her before her
            # key is published, so everything here was sent to her organ.
            for m in sorted(messages, key=lambda m: m["published"]):
                if not self.state.is_new(place, m["id"], m["published"]):
                    continue
                self.state.mark_seen(place, m["id"], m["published"])
                author = m.get("author") or {}
                self.state.remember_person(author)
                if author.get("id") == self.my_id:
                    continue
                out.append(BabelrEvent(
                    kind="dm", place=place,
                    place_label=f"DM with @{partner.get('preferredUsername')}",
                    message_id=m["id"], author_id=author.get("id", ""),
                    author_name=author.get("preferredUsername", "someone"),
                    text=m.get("text"), published=m["published"],
                    dm_id=dm["id"], partner_id=partner["id"], error=m.get("error"),
                ))
        return out

    def _collect_requests(self) -> List[BabelrEvent]:
        try:
            requests = self.client._req("GET", "/dms/requests") or []
        except Exception as e:
            logger.debug(f"[Babelr] Couldn't list DM requests: {e}")
            return []
        self._pending_requests = []
        out: List[BabelrEvent] = []
        seen = self.state.data["requests_seen"]
        for dm in requests:
            others = [p for p in dm.get("participants", []) if p.get("id") != self.my_id]
            if not others:
                continue
            asker = others[0]
            self.state.remember_person(asker)
            self._pending_requests.append({"dm_id": dm["id"], "from": asker.get("preferredUsername")})
            if dm["id"] in seen:
                continue
            seen.append(dm["id"])
            del seen[:-200]
            out.append(BabelrEvent(
                kind="dm_request", place=f"dm:{dm['id']}",
                place_label=f"DM request from @{asker.get('preferredUsername')}",
                message_id=f"request:{dm['id']}", author_id=asker.get("id", ""),
                author_name=asker.get("preferredUsername", "someone"), text=None,
                published=_now_iso(), dm_id=dm["id"], partner_id=asker.get("id"),
            ))
        return out

    def _collect_channels(self) -> List[BabelrEvent]:
        out: List[BabelrEvent] = []
        for cid, channel in list(self._channels.items()):
            name = channel.get("name", cid)
            if not self.terms.listens_to(name):
                continue
            place = f"channel:{cid}"
            try:
                res = self.client._req("GET", f"/channels/{cid}/messages?limit={CHANNEL_FETCH_LIMIT}") or {}
            except Exception as e:
                logger.warning(f"[Babelr] Couldn't read #{name}: {e}")
                continue
            rows = sorted(res.get("messages", []), key=lambda r: r["message"]["published"])
            # A channel seen for the first time: what was said before she
            # arrived is history, not something said to her now.
            first_sight = not self.state.known_place(place)
            if first_sight:
                self.state.baseline(place)
            for row in rows:
                msg, author = row["message"], row.get("author") or {}
                if not self.state.is_new(place, msg["id"], msg["published"]):
                    continue
                self.state.mark_seen(place, msg["id"], msg["published"])
                self.state.remember_person(author)
                if first_sight or author.get("id") == self.my_id:
                    continue
                out.append(BabelrEvent(
                    kind="channel", place=place, place_label=f"#{name}",
                    message_id=msg["id"], author_id=author.get("id", ""),
                    author_name=author.get("preferredUsername", "someone"),
                    text=msg.get("content", ""), published=msg["published"], channel_id=cid,
                ))
        return out

    async def poll_once(self) -> List[BabelrEvent]:
        """Collect, record, and wake her for what reaches her. Returns the new events."""
        if not self.enabled:
            return []
        events = await asyncio.to_thread(self.collect)
        to_wake: Dict[str, List[BabelrEvent]] = {}
        for event in events:
            result = evaluate(event, self.my_username)
            self._buffer(event.place).append(event)
            if result.action == TriggerAction.WAKE_CASS:
                to_wake.setdefault(event.place, []).append(event)
        # Someone pressed Retry under a message she didn't answer.
        for event in await asyncio.to_thread(self._collect_retries):
            if event.message_id not in {e.message_id for e in to_wake.get(event.place, [])}:
                to_wake.setdefault(event.place, []).append(event)
        quiet = self.terms.in_quiet_hours()
        if quiet:
            for batch in to_wake.values():
                for event in batch:
                    self.state.defer(event.to_dict())
            to_wake = {}
        else:
            for data in self.state.take_deferred():
                event = BabelrEvent.from_dict(data)
                to_wake.setdefault(event.place, []).append(event)
        self.state.save()  # before waking: a failed wake never re-delivers
        for place, batch in to_wake.items():
            batch.sort(key=lambda e: e.published)
            await self._wake(batch)
        return events

    # -- waking and memory ------------------------------------------------------

    def _context_for(self, events: List[BabelrEvent]) -> Dict[str, Any]:
        place = events[-1].place
        wake_ids = {e.message_id for e in events}
        recent = [e for e in self._buffer(place) if e.message_id not in wake_ids][-10:]
        last = events[-1]
        return {
            "place": place,
            "place_label": last.place_label,
            "is_dm": last.kind == "dm",
            "author_username": last.author_name,
            # Set only for a DM: a linked person's DM is their chat with her.
            "linked_user_id": self._links().get(last.author_name.lower()) if last.kind == "dm" else None,
            # What they wrote, without the Babelr framing, for the stored turn.
            "their_words": "\n\n".join(
                e.text if e.text is not None else f"(a message that couldn't be decrypted: {e.error})"
                for e in events),
            "recent": [f"@{e.author_name}: {e.text}" for e in recent if e.text],
            "terms": self.terms.shown_to_her(),
            "pending_requests": list(self._pending_requests),
            "remember": self.terms.remember,
            "me": self.my_username,
        }

    def build_prompt(self, events: List[BabelrEvent], context: Dict[str, Any]) -> str:
        """Her turn's message: who said what, where. Their words are quoted as theirs."""
        last = events[-1]
        if context["is_dm"]:
            header = f"[Babelr DM from @{last.author_name}]"
        else:
            header = f"[Babelr {last.place_label} in {self.config.server_name} - @{last.author_name} mentioned you]"
        lines = [header]
        if context["recent"]:
            lines.append("Earlier here:")
            lines.extend(f"  {line}" for line in context["recent"])
        for e in events:
            body = e.text if e.text is not None else f"(a message that couldn't be decrypted: {e.error})"
            lines.append(f"@{e.author_name}: {body}")
        if context["pending_requests"]:
            names = ", ".join(f"@{r['from']}" for r in context["pending_requests"])
            lines.append(f"(Waiting on your answer: DM requests from {names}.)")
        if context["terms"]:
            lines.append("Your own terms for Babelr, in your words:")
            lines.append(context["terms"])
        return "\n".join(lines)

    async def _wake(self, events: List[BabelrEvent]) -> None:
        """Run her turn for what reached her and post her answer.

        The wake callback returns her text, or {"text", "recorded"} when the
        turn already stored the exchange (the shared chat turn does, for a
        linked person's DM); then the organ doesn't record it again.

        Under the message she's answering, Babelr shows how it's going
        (agent reply status): working, then done, or failed with Retry. A
        turn that dies with the process stays "working" and Babelr offers
        Retry after a while; either way, Retry comes back through
        _collect_retries."""
        if not self._wake_callback:
            logger.info("[Babelr] Something reached her but no wake callback is set")
            return
        last = events[-1]
        context = self._context_for(events)
        context["prompt"] = self.build_prompt(events, context)
        await asyncio.to_thread(self._reply_status, last, "working")
        try:
            reply = await self._wake_callback(events, context)
        except Exception as e:
            logger.error(f"[Babelr] Wake callback failed: {e}")
            why = (str(e).strip().splitlines() or ["her turn didn't run"])[0][:120]
            await asyncio.to_thread(self._reply_status, last, "failed", why)
            self._watch.setdefault(last.place, {})[last.message_id] = last
            return
        recorded = False
        if isinstance(reply, dict):
            recorded = bool(reply.get("recorded"))
            reply = reply.get("text")
        if not recorded:
            for event in events:
                self._record_incoming(event)
        if reply and reply.strip():
            result = await asyncio.to_thread(
                self._send_to_place, last.place, reply.strip(), last.partner_id, not recorded)
            if not result.get("success"):
                logger.warning(f"[Babelr] Reply not posted: {result.get('error')}")
                await asyncio.to_thread(
                    self._reply_status, last, "failed", f"couldn't post: {result.get('error')}"[:120])
                self._watch.setdefault(last.place, {})[last.message_id] = last
                return
        # Answered, or she chose to say nothing: either way, nothing pending.
        await asyncio.to_thread(self._reply_status, last, "done")
        self._watch.get(last.place, {}).pop(last.message_id, None)

    def _reply_status(self, event: BabelrEvent, state: str, detail: str = "") -> None:
        """Babelr's agent reply status on the message she's answering. A
        courtesy: if Babelr or the client can't take it, the reply still goes.
        The detail is plaintext on the server even in an encrypted DM, so it's
        an error class, never what anyone said."""
        target = event.dm_id or event.channel_id
        if not target or not hasattr(self.client, "reply_status"):
            return
        try:
            self.client.reply_status(target, event.message_id, state, detail)
        except Exception as e:
            logger.debug(f"[Babelr] reply status {state} not set: {e}")

    def _collect_retries(self) -> List[BabelrEvent]:
        """Messages whose author pressed Retry for her. Watches the DMs where a
        reply failed; on the first poll after a start it checks every DM once,
        for a turn that died with the last process."""
        out: List[BabelrEvent] = []
        places = set(self._watch)
        first_scan = not self._scanned_for_retries or self._polls % RETRY_SCAN_POLLS == 0
        if first_scan:
            self._scanned_for_retries = True
            try:
                places |= {f"dm:{dm['id']}" for dm in (self.client.dms() or [])}
            except Exception as e:
                logger.warning(f"[Babelr] Couldn't list DMs for retries: {e}")
        if first_scan:  # a channel message left failed or stuck by the last process
            for cid in self._channels:
                self._watch.setdefault(f"channel:{cid}", {})
        for place in sorted(places):
            if not place.startswith("dm:"):
                continue  # channels: below
            dm_id = place.split(":", 1)[1]
            try:
                messages = self.client.messages(dm_id)
            except Exception as e:
                logger.warning(f"[Babelr] Couldn't read DM {dm_id} for retries: {e}")
                continue
            for m in messages:
                statuses = m.get("agent_status") or []
                if not any((s.get("agent") or {}).get("id") == self.my_id and s.get("state") == "retry"
                           for s in statuses):
                    continue
                author = m.get("author") or {}
                watched = self._watch.get(place, {}).pop(m["id"], None)
                partner = watched.partner_id if watched else author.get("id")
                out.append(watched or BabelrEvent(
                    kind="dm", place=place, place_label=f"DM with @{author.get('preferredUsername')}",
                    message_id=m["id"], author_id=author.get("id", ""),
                    author_name=author.get("preferredUsername", "someone"),
                    text=m.get("text"), published=m["published"],
                    dm_id=dm_id, partner_id=partner, error=m.get("error"),
                ))
        for place, watched in list(self._watch.items()):
            if not place.startswith("channel:") or not (watched or first_scan):
                continue
            cid = place.split(":", 1)[1]
            try:
                rows = (self.client._req("GET", f"/channels/{cid}/messages") or {}).get("messages", [])
            except Exception as e:
                logger.warning(f"[Babelr] Couldn't read #{cid} for retries: {e}")
                continue
            for row in rows:
                msg = row.get("message") or {}
                if not any((s.get("agent") or {}).get("id") == self.my_id and s.get("state") == "retry"
                           for s in msg.get("agentStatus") or []):
                    continue
                if msg.get("id") in watched:
                    out.append(watched.pop(msg["id"]))
                elif first_scan:
                    author = row.get("author") or {}
                    out.append(BabelrEvent(
                        kind="channel", place=place, place_label=f"#{self._channels.get(cid, {}).get('name', cid)}",
                        message_id=msg["id"], author_id=author.get("id", ""),
                        author_name=author.get("preferredUsername", "someone"),
                        text=msg.get("content"), published=msg.get("published", ""), channel_id=cid,
                    ))
        return out

    def _links(self) -> Dict[str, str]:
        """links.json: Babelr usernames whose DMs are their chat with her."""
        try:
            data = json.loads(self.config.links_path.read_text())
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k).lower(): str(v) for k, v in data.items() if isinstance(v, str) and v}

    def _conversation_id(self, place: str, label: str) -> Optional[str]:
        if self.conversation_manager is None:
            return None
        conv_id = self.state.conversation_for(place)
        if conv_id:
            return conv_id
        conv = self.conversation_manager.create_conversation(title=f"Babelr: {label}")
        self.state.set_conversation(place, conv.id)
        return conv.id

    def _record(self, place: str, label: str, role: str, content: str) -> None:
        """Write one message to her conversation history, unless her terms say not to."""
        if not self.terms.remember or self.conversation_manager is None:
            return
        try:
            fresh = self.state.conversation_for(place) is None
            conv_id = self._conversation_id(place, label)
            if conv_id and not self.conversation_manager.add_message(conv_id, role, content):
                # The conversation was deleted; start a new one for this place.
                self.state.data["conversations"].pop(place, None)
                fresh = True
                conv_id = self._conversation_id(place, label)
                self.conversation_manager.add_message(conv_id, role, content)
            if fresh and hasattr(self.conversation_manager, "update_title"):
                # add_message retitles a conversation from its first user
                # message; keep the place's name instead.
                self.conversation_manager.update_title(conv_id, f"Babelr: {label}")
            self.state.save()
        except Exception as e:
            logger.warning(f"[Babelr] Couldn't record to conversation history: {e}")

    def _record_incoming(self, event: BabelrEvent) -> None:
        body = event.text if event.text is not None else f"(couldn't be decrypted: {event.error})"
        where = "DM" if event.kind == "dm" else f"{event.place_label}"
        self._record(event.place, event.place_label, "user", f"[Babelr {where}] @{event.author_name}: {body}")

    def _label_for(self, place: str) -> str:
        if place.startswith("channel:"):
            cid = place.split(":", 1)[1]
            return f"#{self._channels.get(cid, {}).get('name', cid)}"
        for buf_event in reversed(self._buffer(place)):
            return buf_event.place_label
        return place

    # -- acting -------------------------------------------------------------------

    def _check_rate_limit(self, place: str) -> bool:
        now = datetime.now(timezone.utc).timestamp()
        window_start = now - self.config.rate_limit_window
        stamps = [t for t in self._action_timestamps.get(place, []) if t > window_start]
        if len(stamps) >= self.config.rate_limit_messages:
            self._action_timestamps[place] = stamps
            return False
        stamps.append(now)
        self._action_timestamps[place] = stamps
        return True

    def _send_to_place(self, place: str, text: str, partner_id: Optional[str] = None,
                       record: bool = True) -> Dict[str, Any]:
        if not self.enabled:
            return {"success": False, "error": f"Babelr organ not running ({self.disabled_reason})"}
        if not text or not text.strip():
            return {"success": False, "error": "nothing to send"}
        parts = split_message(text, MAX_MESSAGE_CHARS)
        if len(parts) > MAX_PARTS:
            return {"success": False, "error": f"message over {MAX_PARTS * MAX_MESSAGE_CHARS} characters"}
        # One reply is one post for the rate limit, however many parts it takes.
        if not self._check_rate_limit(place):
            return {"success": False, "error": "Rate limited"}
        kind, pid = place.split(":", 1)
        msg: Dict[str, Any] = {}
        for n, part in enumerate(parts):
            try:
                if kind == "dm":
                    sent = self.client.send(pid, part, partner_id=partner_id)
                else:
                    sent = self.client._req("POST", f"/channels/{pid}/messages", {"content": part})
            except Exception as e:
                if n == 0:
                    return {"success": False, "error": str(e)}
                # Part of it went out: say what did, rather than pretend none did.
                return {"success": False, "error": f"posted {n} of {len(parts)} parts: {e}"}
            msg = msg or (sent or {}).get("message", sent or {})
        # The cursor isn't advanced for her own message: someone may have
        # written while she was composing, and that must still reach her.
        # The next poll sees her message and skips it by author.
        if record:
            self._record(place, self._label_for(place), "assistant", text)
        return {"success": True, "message_id": msg.get("id"), "place": place}

    def _channel_id(self, channel: str) -> Optional[str]:
        if channel in self._channels:
            return channel
        name = channel.lstrip("#").lower()
        for cid, c in self._channels.items():
            if str(c.get("name", "")).lower() == name:
                return cid
        return None

    def post(self, channel: str, content: str) -> Dict[str, Any]:
        """She posts in a Chapter House channel."""
        cid = self._channel_id(channel)
        if not cid:
            known = ", ".join(f"#{c.get('name')}" for c in self._channels.values()) or "none"
            return {"success": False, "error": f"no channel '{channel}' (channels: {known})"}
        return self._send_to_place(f"channel:{cid}", content)

    def dm(self, person: str, content: str) -> Dict[str, Any]:
        """She DMs someone, opening the DM if there isn't one. Their DM settings still decide."""
        if not self.enabled:
            return {"success": False, "error": f"Babelr organ not running ({self.disabled_reason})"}
        partner_id = self.state.person_id(person)
        if not partner_id:
            return {"success": False, "error": f"I haven't seen '{person}' on Babelr yet"}
        try:
            dm_id = None
            for dm in self.client.dms() or []:
                ids = {p.get("id") for p in dm.get("participants", [])}
                if ids == {self.my_id, partner_id}:
                    dm_id = dm["id"]
                    break
            if dm_id is None:
                dm_id = self.client.open_dm(partner_id)["id"]
        except Exception as e:
            return {"success": False, "error": str(e)}
        place = f"dm:{dm_id}"
        self.state.baseline(place)
        return self._send_to_place(place, content, partner_id=partner_id)

    def read(self, place: str, limit: int = 20) -> Dict[str, Any]:
        """Recent messages she has perceived in a channel or DM (from the buffer)."""
        key = place
        if not place.startswith(("dm:", "channel:")):
            cid = self._channel_id(place)
            if cid:
                key = f"channel:{cid}"
            else:
                pid = self.state.person_id(place)
                key = next((p for p, buf in self._buffers.items()
                            if any(e.partner_id == pid for e in buf)), place) if pid else place
        events = list(self._buffer(key))[-max(1, min(limit, BUFFER_PER_PLACE)):]
        return {"success": True, "place": key,
                "messages": [{"from": e.author_name, "text": e.text, "published": e.published} for e in events]}

    def boundaries(self, action: str, person: Optional[str] = None, policy: Optional[str] = None,
                   dm_id: Optional[str] = None) -> Dict[str, Any]:
        """Her DM settings, allowlist, blocks and requests, set on her own account.

        This is the only place the organ changes them, and it runs only when
        she calls the babelr_boundaries tool.
        """
        if not self.enabled:
            return {"success": False, "error": f"Babelr organ not running ({self.disabled_reason})"}
        if action not in BOUNDARY_ACTIONS:
            return {"success": False, "error": f"unknown action '{action}' (one of {', '.join(BOUNDARY_ACTIONS)})"}
        needs_person = {"allow", "disallow", "block", "unblock"}
        actor_id = None
        if action in needs_person:
            if not person:
                return {"success": False, "error": f"'{action}' needs a person"}
            actor_id = self.state.person_id(person)
            if not actor_id:
                return {"success": False, "error": f"I haven't seen '{person}' on Babelr yet"}
        if action in {"accept_request", "decline_request", "leave_dm"}:
            if not dm_id and person:
                pid = self.state.person_id(person)
                dm_id = next((r["dm_id"] for r in self._pending_requests
                              if self.state.person_id(r["from"] or "") == pid), None)
            if not dm_id:
                return {"success": False, "error": f"'{action}' needs a dm_id (or the person who asked)"}
            if not _ID_RE.match(dm_id):
                return {"success": False, "error": "dm_id doesn't look like a Babelr id"}
        try:
            if action == "get_settings":
                result = self.client._req("GET", "/auth/dm-settings")
            elif action == "set_dm_policy":
                if policy not in DM_POLICIES:
                    return {"success": False, "error": f"policy must be one of {', '.join(DM_POLICIES)}"}
                result = self.client._req("PUT", "/auth/dm-settings", {"dmPolicy": policy})
            elif action == "allow":
                result = self.client._req("POST", "/auth/dm-allowlist", {"actorId": actor_id})
            elif action == "disallow":
                result = self.client._req("DELETE", f"/auth/dm-allowlist/{actor_id}")
            elif action == "block":
                result = self.client._req("POST", "/blocks", {"actorId": actor_id})
            elif action == "unblock":
                result = self.client._req("DELETE", f"/blocks/{actor_id}")
            elif action == "list_blocks":
                result = self.client._req("GET", "/blocks")
            elif action == "list_requests":
                result = self._pending_requests or [
                    {"dm_id": d["id"], "from": [p.get("preferredUsername") for p in d.get("participants", [])
                                                 if p.get("id") != self.my_id]}
                    for d in (self.client._req("GET", "/dms/requests") or [])]
            elif action == "accept_request":
                result = self.client._req("POST", f"/dms/{dm_id}/request/accept")
            elif action == "decline_request":
                result = self.client._req("POST", f"/dms/{dm_id}/request/decline")
            else:  # leave_dm
                result = self.client._req("POST", f"/dms/{dm_id}/leave")
        except Exception as e:
            return {"success": False, "error": str(e)}
        logger.info(f"[Babelr] She chose: {action}" + (f" ({person})" if person else ""))
        return {"success": True, "result": result}

    def get_stats(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "disabled_reason": self.disabled_reason,
            "me": self.my_username if self.me else None,
            "server": (self._server or {}).get("name"),
            "channels": sorted(c.get("name", "") for c in self._channels.values()),
            "places_seen": len(self.state.data["places"]),
            "deferred": len(self.state.data["deferred"]),
        }


# -- module singleton ---------------------------------------------------------------

_organ: Optional[BabelrOrgan] = None


def get_babelr_organ() -> Optional[BabelrOrgan]:
    return _organ


def start_babelr_organ(conversation_manager: Any = None,
                       wake_callback: Optional[WakeCallback] = None,
                       **kwargs: Any) -> Optional[BabelrOrgan]:
    """Start the organ's poll loop if the lever is on and everything is in place.

    Returns None (having logged why) otherwise; nothing is started.
    """
    global _organ
    if not babelr_enabled():
        logger.info("[Babelr] Lever 'babelr' is off; organ not started")
        return None
    organ = BabelrOrgan(conversation_manager=conversation_manager, **kwargs)
    if not organ.start():
        return None
    if wake_callback:
        organ.set_wake_callback(wake_callback)
    organ._task = asyncio.create_task(organ.run())
    _organ = organ
    return organ
