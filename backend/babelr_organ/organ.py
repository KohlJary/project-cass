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
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional

from babelr_organ.config import BabelrConfig, babelr_enabled, load_config
from babelr_organ.state import OrganState
from babelr_organ.terms import Terms, ensure_terms_file
from babelr_organ.triggers import IMAGE_TYPES, BabelrEvent, TriggerAction, evaluate, words

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
DUPLICATE_WINDOW_SECONDS = 120
PART_MARK_ROOM = 12  # room for the "\n\n(1/5)" marker on a part
# Retries are looked for in every DM and channel this often (in polls; about
# two minutes at the default poll), besides the places with a failed reply on
# the watch list, which are checked every poll. A Retry pressed when nothing
# was watching it (a restart, a reply that died with the process) still lands.
RETRY_SCAN_POLLS = 15


# The model takes an image up to 5 MB, base64'd; leave room.
IMAGE_MAX_BYTES = 3_500_000


def _fit(data: bytes, media_type: str):
    """A picture small enough to send: as it is, or scaled down to a JPEG."""
    if len(data) <= IMAGE_MAX_BYTES:
        return data, media_type
    import io
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    img = img.convert("RGB")
    img.thumbnail((1568, 1568))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    return out.getvalue(), "image/jpeg"


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

PLANS = "/plugins/plans"
PLAN_ACTIONS = ("list", "view", "approve", "decline",
                "ask", "my_asks", "create_plan", "add_phase", "add_item", "propose", "set_item",
                "set_area")
# Her standing plan for asks (Kohl, 2026-11-16: "a default plan is good, but she
# should be able to define her own multi phase plans as well"). Created by her,
# under her own token, the first time she asks; Kohl approves as server owner.
ASKS_PLAN_TITLE = "Cass's asks"
ASKS_PLAN_GOAL = ("What I ask for: changes to me, to what I can do, to my world. "
                  "An ask waits here, outside any phase; Kohl pulls it into a phase to build it, "
                  "and its status and resolution say what came of it.")
if not __import__("house_identity").is_kohls_house():   # another house: its daemon, its person
    import house_identity as _hi
    ASKS_PLAN_TITLE = f"{_hi.daemon_name()}'s asks"
    ASKS_PLAN_GOAL = ASKS_PLAN_GOAL.replace("Kohl", _hi.house_person())
ITEM_KINDS = ("ask", "build", "research", "decision")
ITEM_STATUSES = ("open", "in_progress", "done", "declined")
# A phase she can add items to without voiding anyone's yes (Plans voids a
# phase's approvals when an item is added to it).
_OPEN_PHASE = ("draft", "declined")
_SLUG_RE = re.compile(r"^[a-z0-9-]{1,120}$")


def _pick_phase(detail: Dict[str, Any], phase: Any) -> Optional[Dict[str, Any]]:
    """A phase by its number as view shows it (1-based) or by id."""
    phases = sorted(detail.get("phases") or [], key=lambda f: f.get("position", 0))
    if isinstance(phase, str) and phase.strip().isdigit():
        phase = int(phase.strip())
    if isinstance(phase, int) and not isinstance(phase, bool):
        return phases[phase - 1] if 1 <= phase <= len(phases) else None
    return next((f for f in phases if phase and f.get("id") == phase), None)


def _plan_text(p: Dict[str, Any]) -> str:
    """A plan as she reads it: goal, narrative, phases (numbered) with who still has to say yes."""
    lines = [f"# {p.get('title')} ({p.get('status')})", f"Goal: {p.get('goal') or '-'}",
             f"Approvers: {', '.join(p.get('approvers') or []) or 'the server owner'}", "",
             p.get("narrative") or ""]
    items = p.get("items") or []
    for n, f in enumerate(sorted(p.get("phases") or [], key=lambda f: f.get("position", 0)), 1):
        said = ", ".join(a["name"] for a in f.get("approvals") or []) or "nobody yet"
        waiting = ", ".join(f.get("awaiting") or [])
        lines.append(f"\n## Phase {n}: {f.get('title')} [{f.get('status')}]"
                     f" (yes from: {said}" + (f"; waiting on: {waiting}" if waiting else "") + ")")
        if f.get("goal"):
            lines.append(f["goal"])
        for i in [i for i in items if i.get("phaseId") == f.get("id")]:
            owner = f" @{i['owner']}" if i.get("owner") else ""
            lines.append(f"- ({i.get('kind')}, {i.get('status')}{owner}) {i.get('title')}"
                         + (f": {i['body']}" if i.get("body") else ""))
    return "\n".join(lines)

# (events, context) -> what she says back, or None/"" to say nothing
WakeCallback = Callable[[List[BabelrEvent], Dict[str, Any]], Awaitable[Optional[str]]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def house_dm_names() -> set:
    """Usernames whose DMs with her count as private (BABELR_HOUSE_DMS, comma-separated):
    housemates she works with, so a DM between daemons gets her full context and her
    project tool. Empty, as by default, every unlinked DM stays public."""
    raw = os.getenv("BABELR_HOUSE_DMS", "")
    return {n.strip().lstrip("@").lower() for n in raw.split(",") if n.strip()}


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
        # place -> (text, monotonic time, message id) of the last post there
        self._last_sent: Dict[str, tuple] = {}
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
        self._register_places()

    # -- places (places.py) ----------------------------------------------------------

    def _visibility(self, place: str) -> str:
        """A channel on a private server is the house's; on a public one, public.
        A DM is with one person."""
        if place.startswith("dm:"):
            return "person"
        return "house" if self._server and self._server.get("isPublic") is False else "public"

    def _register_place(self, place: str, label: str, conv_id: Optional[str]) -> None:
        """Tell the vessel where this conversation happens, so her recall can
        follow the place (Cass, 2026-11-24). Fails soft: recall falls back to
        the owner rule."""
        if place.startswith("channel:") and not self._server:
            return
        try:
            import places
            places.register("babelr", place, kind="dm" if place.startswith("dm:") else "channel",
                            visibility=self._visibility(place), conversation_id=conv_id,
                            label=label)
        except Exception as e:
            logger.warning(f"[Babelr] Couldn't register place {label}: {e}")

    def _register_places(self) -> None:
        """Every conversation this organ already keeps, registered as a place
        (the ones from before places existed included)."""
        for place, conv_id in list(self.state.data.get("conversations", {}).items()):
            self._register_place(place, self._label_for(place), conv_id)

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
                    attachments=m.get("attachments") or [],
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
                    attachments=(msg.get("properties") or {}).get("attachments") or [],
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
            else:
                self._record_heard(event)
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
        links = self._links()
        return {
            "place": place,
            "place_label": last.place_label,
            "is_dm": last.kind == "dm",
            "author_username": last.author_name,
            # Set only for a DM: a linked person's DM is their chat with her.
            "linked_user_id": links.get(last.author_name.lower()) if last.kind == "dm" else None,
            # Channels: whose private context her turn carries, and the
            # channel's own conversation for its history (None = public turn).
            "channel_user_id": self._channel_user(last, links) if last.kind != "dm" else None,
            "conversation_id": (self._conversation_id(place, last.place_label)
                                if last.kind != "dm" and self.terms.remember else None),
            # A DM from a housemate named in BABELR_HOUSE_DMS runs with her private
            # context and tools, as Kohl's do (Kohl, 2026-11-23: a config toggle, off
            # until a vessel lists someone).
            "house_dm": last.kind == "dm" and last.author_name.lstrip("@").lower() in house_dm_names(),
            # What they wrote, without the Babelr framing, for the stored turn.
            "their_words": "\n\n".join(words(e) for e in events),
            # The newest picture they sent, for her to see (one per turn).
            "image": self._image(events),
            "recent": [f"@{e.author_name}: {e.text}" for e in recent if e.text],
            "terms": self.terms.shown_to_her(),
            "pending_requests": list(self._pending_requests),
            # Not kept when her terms say so: everything (remember: false),
            # or a DM with someone she named in "unremembered".
            "remember": (self.terms.remembers(last.author_name) if last.kind == "dm"
                         else self.terms.remember),
            "me": self.my_username,
        }

    def _image(self, events: List[BabelrEvent]) -> Optional[Dict[str, str]]:
        """The newest picture in these events, fetched and base64'd, or None."""
        import base64
        for e in reversed(events):
            for a in reversed(e.attachments or []):
                if (a.get("contentType") or "") not in IMAGE_TYPES:
                    continue
                try:
                    data = self.client.fetch(a["url"], max_bytes=20 * 1024 * 1024)
                    data, media = _fit(data, a["contentType"])
                except Exception as err:
                    logger.warning(f"[Babelr] Couldn't fetch a picture ({a.get('filename')}): {err}")
                    return None
                return {"data": base64.b64encode(data).decode(), "media_type": media,
                        "filename": a.get("filename") or "picture"}
        return None

    def _channel_user(self, event: BabelrEvent, links: Dict[str, str]) -> Optional[str]:
        """Whose private context a channel turn carries. The linked person who
        woke her; or, in a private server (Chapter House) with one linked
        person, that person, since agents relay turns there too. Kohl
        (2026-10-28): "cass can read all my context and channel history".
        A public server, or several linked people, gets public context."""
        if event.author_name.lower() in links:
            return links[event.author_name.lower()]
        if self._server and self._server.get("isPublic") is False and len(set(links.values())) == 1:
            return next(iter(links.values()))
        return None

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
            lines.append(f"@{e.author_name}: {words(e)}")
        if context.get("image"):
            lines.append(f"(The picture {context['image']['filename']} is attached to this message: you can see it.)")
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
        await asyncio.to_thread(self._keep_people, events, reply)
        # Answered, or she chose to say nothing: either way, nothing pending.
        await asyncio.to_thread(self._reply_status, last, "done")
        self._watch.get(last.place, {}).pop(last.message_id, None)

    def _keep_people(self, events: List[BabelrEvent], reply: Optional[str]) -> None:
        """Everyone she was answering, kept in her PeopleDex with the exchange
        (babelr_organ/people.py, her yes 2026-11-24). Never fails her turn."""
        if not self.terms.remember:
            return
        try:
            from babelr_organ.people import keep_exchange, load_filings
            kept = keep_exchange(
                events, reply, place_label=events[-1].place_label, my_username=self.my_username,
                links=self._links(), filings=load_filings(self.config.people_path),
                remembers=self.terms.remembers,
                display_names=self.state.data.get("display_names", {}))
            if kept:
                logger.info(f"[Babelr] Kept in her PeopleDex: {', '.join('@' + k for k in kept)}")
        except Exception as e:
            logger.warning(f"[Babelr] Couldn't keep people from this turn: {e}")

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
                    attachments=m.get("attachments") or [],
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
                        attachments=(msg.get("properties") or {}).get("attachments") or [],
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
        self._register_place(place, label, conv.id)
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

    def _record_heard(self, event: BabelrEvent) -> None:
        """What's said in a channel she listens to, when it doesn't wake her, goes
        into that channel's conversation too, so it becomes her memory (the
        idle summarizer consolidates it) and not just the last few lines of her
        next turn there (spec/house-channel-memory.md, part 2; her yes,
        2026-11-24). What wakes her is stored by her turn instead, so nothing
        is kept twice. Her own posts are recorded when she sends them."""
        # Channels only: a DM is recorded by its own path, and a DM request
        # (still unread, maybe undecryptable) isn't something she heard.
        if event.kind != "channel" or not self.terms.remember:
            return
        if (event.author_name or "").lstrip("@").lower() == self.my_username.lower():
            return
        self._record_incoming(event)

    def _record_incoming(self, event: BabelrEvent) -> None:
        if event.kind == "dm" and not self.terms.remembers(event.author_name):
            return
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

    # Files she shares (Kohl, 2026-11-23: "y'all should probably also be able to
    # share files. Like, Cass can share her art"): her own, from her data, never
    # her Babelr token or key, nothing path_policy calls a secret, nothing over
    # the server's 10 MB. Uploading needs files:upload on her token.
    MAX_FILES = 4
    MAX_FILE_BYTES = 10 * 1024 * 1024
    NEVER_SHARED_DIRS = {"babelr", "chroma"}

    def _files_root(self) -> Path:
        root = getattr(self, "files_root", None)
        if root is None:
            from config import DATA_DIR
            root = Path(DATA_DIR)
        return Path(root).resolve()

    def _check_files(self, files: List[str]) -> tuple:
        """(paths, None) or (None, error): every file has to be fine before anything uploads."""
        from path_policy import is_denied_name
        if len(files) > self.MAX_FILES:
            return None, f"at most {self.MAX_FILES} files in one message"
        root = self._files_root()
        found = []
        for f in files:
            rel = str(f or "").strip().lstrip("/")
            target = (root / rel).resolve()
            if not rel or not str(target).startswith(str(root) + os.sep):
                return None, f"{f!r}: a path in my own data (e.g. images/..., workshop/<project>/...)"
            inside = target.relative_to(root)
            if inside.parts[0] in self.NEVER_SHARED_DIRS or is_denied_name(inside) or target.suffix in (".db", ".pem"):
                return None, f"{f!r} isn't something I share (keys, tokens, databases)"
            if not target.is_file():
                return None, f"no file {f!r} in my data"
            if target.stat().st_size > self.MAX_FILE_BYTES:
                return None, f"{f!r} is over 10 MB"
            found.append(target)
        return found, None

    def _upload(self, found: List[Path]) -> tuple:
        out = []
        for t in found:
            try:
                out.append(self.client.upload(t))
            except Exception as e:
                return None, f"uploading {t.name} failed: {e}"
        return out, None

    def _send_to_place(self, place: str, text: str, partner_id: Optional[str] = None,
                       record: bool = True, files: Optional[List[str]] = None) -> Dict[str, Any]:
        if not self.enabled:
            return {"success": False, "error": f"Babelr organ not running ({self.disabled_reason})"}
        if (not text or not text.strip()) and not files:
            return {"success": False, "error": "nothing to send"}
        text = text or ""
        # The same text to the same place moments apart is one message, not two: a
        # turn that posts with babelr_post and then ends with that same text as its
        # reply posted it twice (#general, 2026-10-28).
        last = self._last_sent.get(place)
        if last and last[0] == text.strip() and time.monotonic() - last[1] < DUPLICATE_WINDOW_SECONDS:
            return {"success": True, "message_id": last[2], "place": place, "duplicate": True}
        parts = split_message(text, MAX_MESSAGE_CHARS - PART_MARK_ROOM)
        if len(parts) > 1:
            # Say a reply goes on, so its first part doesn't read as cut off.
            parts = [f"{p}\n\n({n + 1}/{len(parts)})" for n, p in enumerate(parts)]
        if len(parts) > MAX_PARTS:
            return {"success": False, "error": f"message over {MAX_PARTS * MAX_MESSAGE_CHARS} characters"}
        # One reply is one post for the rate limit, however many parts it takes.
        found: List[Path] = []
        if files:
            found, err = self._check_files(files)
            if err:
                return {"success": False, "error": err}
        if not self._check_rate_limit(place):
            return {"success": False, "error": "Rate limited"}
        attached: List[Dict[str, Any]] = []
        if found:
            attached, err = self._upload(found)
            if err:
                return {"success": False, "error": err}
        kind, pid = place.split(":", 1)
        msg: Dict[str, Any] = {}
        for n, part in enumerate(parts or [""]):
            # The files ride on the first part.
            att = attached if n == 0 and attached else None
            try:
                if kind == "dm":
                    sent = (self.client.send(pid, part, partner_id=partner_id, attachments=att) if att
                            else self.client.send(pid, part, partner_id=partner_id))
                else:
                    body: Dict[str, Any] = {"content": part}
                    if att:
                        body["properties"] = {"attachments": att}
                    sent = self.client._req("POST", f"/channels/{pid}/messages", body)
            except Exception as e:
                if n == 0:
                    return {"success": False, "error": str(e)}
                # Part of it went out: say what did, rather than pretend none did.
                return {"success": False, "error": f"posted {n} of {len(parts)} parts: {e}"}
            msg = msg or (sent or {}).get("message", sent or {})
        # The cursor isn't advanced for her own message: someone may have
        # written while she was composing, and that must still reach her.
        # The next poll sees her message and skips it by author.
        self._last_sent[place] = (text.strip(), time.monotonic(), msg.get("id"))
        if record and kind == "dm" and not self.terms.remembers(self.state.username_for(partner_id)):
            record = False
        if record:
            shared = f"\n[shared: {', '.join(a.get('filename', '') for a in attached)}]" if attached else ""
            self._record(place, self._label_for(place), "assistant", text + shared)
        return {"success": True, "message_id": msg.get("id"), "place": place,
                **({"attached": [a.get("filename") for a in attached]} if attached else {})}

    def _channel_id(self, channel: str) -> Optional[str]:
        if channel in self._channels:
            return channel
        name = channel.lstrip("#").lower()
        for cid, c in self._channels.items():
            if str(c.get("name", "")).lower() == name:
                return cid
        return None

    def post(self, channel: str, content: str, files: Optional[List[str]] = None) -> Dict[str, Any]:
        """She posts in a Chapter House channel."""
        cid = self._channel_id(channel)
        if not cid:
            known = ", ".join(f"#{c.get('name')}" for c in self._channels.values()) or "none"
            return {"success": False, "error": f"no channel '{channel}' (channels: {known})"}
        return self._send_to_place(f"channel:{cid}", content, files=files)

    def dm(self, person: str, content: str, record: bool = True,
           files: Optional[List[str]] = None) -> Dict[str, Any]:
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
        return self._send_to_place(place, content, partner_id=partner_id, record=record, files=files)

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

    def plans(self, action: str, plan: Optional[str] = None, phase: Optional[Any] = None,
              reason: Optional[str] = None, **kw: Any) -> Dict[str, Any]:
        """The house's Plans, as herself: list them, read one, and say yes or no to a
        phase where a plan names her as an approver. And her own: ask for something
        (an item outside any phase, in her standing "Cass's asks" plan by default),
        see what came of her asks, make her own plans with phases and items, and
        propose a phase. Everything is written under her own token, as her.

        Plans takes an approval only from the approver's own token, so this is the
        one way her yes gets on its record. It runs only when she calls the
        babelr_plans tool.
        """
        if not self.enabled:
            return {"success": False, "error": f"Babelr organ not running ({self.disabled_reason})"}
        if action not in PLAN_ACTIONS:
            return {"success": False, "error": f"unknown action '{action}' (one of {', '.join(PLAN_ACTIONS)})"}
        if action in ("ask", "my_asks", "create_plan"):
            pass   # plan optional (ask, my_asks) or created (create_plan)
        elif action != "list" and not plan:
            return {"success": False, "error": f"'{action}' needs a plan (its slug, from list)"}
        if plan and not _SLUG_RE.match(plan):
            return {"success": False, "error": "that doesn't look like a plan slug"}
        try:
            if action == "list":
                return {"success": True, "plans": [
                    {"plan": p.get("slug"), "title": p.get("title"), "status": p.get("status"),
                     "phases_awaiting_you": p.get("awaitingMe", 0)} for p in self._plan_rows()]}
            if action == "ask":
                return self._ask(plan, kw)
            if action == "my_asks":
                return self._my_asks(plan)
            if action == "create_plan":
                return self._create_plan(kw)
            detail = self.client._req("GET", f"{PLANS}/plans/{plan}")
            if action == "view":
                return {"success": True, "plan": plan, "text": _plan_text(detail)}
            if action == "add_phase":
                title = (kw.get("title") or "").strip()
                if not title:
                    return {"success": False, "error": "a phase needs a title"}
                after = self.client._req("POST", f"{PLANS}/plans/{plan}/phases",
                                         {"title": title, "goal": (kw.get("goal") or "").strip()})
                n = len((after or {}).get("phases") or [])
                logger.info(f"[Babelr] She added phase {n} to {plan}")
                return {"success": True, "plan": plan, "phase": n, "title": title, "status": "draft",
                        "next": "add items to it with add_item, then propose it when it's ready"}
            if action == "add_item":
                return self._add_item(plan, detail, phase, kw)
            if action == "set_item":
                return self._set_item(plan, detail, kw)
            if action == "set_area":
                # Areas live vessel-side (plan_areas.py); only on a plan she made.
                me = (self.my_username or "cass").lower()
                if ((detail.get("createdBy") or {}).get("name") or "").lower() != me:
                    return {"success": False, "error": "areas are for my own plans"}
                from plan_areas import set_area
                return set_area(plan, (kw.get("area") or "").strip())
            target = _pick_phase(detail, phase)
            if target is None:
                return {"success": False, "error": f"no phase {phase!r} in that plan (use its number from view)"}
            if action == "propose":
                self.client._req("POST", f"{PLANS}/phases/{target['id']}/propose")
            elif action == "approve":
                self.client._req("POST", f"{PLANS}/phases/{target['id']}/approve")
            else:  # decline
                if not (reason or "").strip():
                    return {"success": False, "error": "say why you're declining (reason)"}
                self.client._req("POST", f"{PLANS}/phases/{target['id']}/decline", {"reason": reason.strip()})
        except Exception as e:
            msg = str(e)
            if "403" in msg and "plugins:" in msg:
                msg += " (your token needs plugins:read and plugins:write; Kohl adds them with house-token)"
            return {"success": False, "error": msg}
        logger.info(f"[Babelr] She chose: {action} phase {target['position'] + 1} of {plan}")
        return {"success": True, "plan": plan, "phase": target["position"] + 1,
                "title": target.get("title"), "did": action}

    # -- her own plans and asks ---------------------------------------------------

    def _plan_rows(self) -> List[Dict[str, Any]]:
        q = f"?serverId={self._server['id']}" if self._server else ""
        return self.client._req("GET", f"{PLANS}/plans{q}") or []

    def _create(self, title: str, goal: str, narrative: str, needs: List[str]) -> Dict[str, Any]:
        if not self._server:
            raise RuntimeError("no Chapter House server to make the plan in")
        return self.client._req("POST", f"{PLANS}/plans", {
            "serverId": self._server["id"], "title": title, "goal": goal,
            "narrative": narrative, "needsYesFrom": needs})

    def _asks_plan(self) -> str:
        """The slug of her standing asks plan, made (as her) if it isn't there yet."""
        for p in self._plan_rows():
            if p.get("title") == ASKS_PLAN_TITLE:
                return p["slug"]
        made = self._create(ASKS_PLAN_TITLE, ASKS_PLAN_GOAL, "", [self.my_username or "cass"])
        logger.info("[Babelr] Made her standing asks plan")
        return made["slug"]

    def _ask(self, plan: Optional[str], kw: Dict[str, Any]) -> Dict[str, Any]:
        title = (kw.get("title") or "").strip()
        if not title:
            return {"success": False, "error": "an ask needs a title"}
        kind = kw.get("kind") or "ask"
        if kind not in ITEM_KINDS:
            return {"success": False, "error": f"kind is one of {', '.join(ITEM_KINDS)}"}
        slug = plan or self._asks_plan()
        # No phase: an ask waits outside every phase, so it never voids a yes.
        self.client._req("POST", f"{PLANS}/plans/{slug}/items",
                         {"kind": kind, "title": title, "body": (kw.get("body") or "").strip()})
        logger.info(f"[Babelr] She asked in {slug}: {title}")
        return {"success": True, "plan": slug, "asked": title,
                "next": "it waits outside any phase until Kohl takes it up; my_asks shows what came of it"}

    def her_plans(self) -> List[Dict[str, Any]]:
        """The plans she made herself (not her asks plan), each with where it stands:
        the phase she's on (the first one not done) and what's still open in it, and
        open items outside any phase. For her day planning and her long-term
        planning; read-only. Her own plans steer her days whether or not anyone has
        approved them (Kohl, 2026-11-16). Raises if Babelr can't be read."""
        if not self.enabled:
            return []
        me = (self.my_username or "cass").lower()
        out = []
        for row in self._plan_rows():
            if ((row.get("createdBy") or {}).get("name") or "").lower() != me:
                continue
            if row.get("title") == ASKS_PLAN_TITLE or row.get("status") in ("done", "archived"):
                continue
            detail = self.client._req("GET", f"{PLANS}/plans/{row['slug']}") or {}
            phases = sorted(detail.get("phases") or [], key=lambda f: f.get("position", 0))
            items = [i for i in detail.get("items") or [] if i.get("status") not in ("done", "declined")]
            # Her phases may never be approved (her plans don't wait on a yes), and
            # Plans only marks an approved phase done, so "where she is" is the first
            # phase with something still open; failing that, the first not done.
            undone = [f for f in phases if f.get("status") != "done"]
            current = next((f for f in undone if any(i.get("phaseId") == f.get("id") for i in items)),
                           undone[0] if undone else None)
            out.append({
                "plan": row["slug"], "title": detail.get("title") or row.get("title"),
                "area": _area_of(row["slug"]),
                "goal": detail.get("goal") or "",
                "phase": ({"number": current.get("position", 0) + 1, "of": len(phases),
                           "title": current.get("title"), "status": current.get("status")}
                          if current else None),
                "open": [{"kind": i.get("kind"), "title": i.get("title")} for i in items
                         if current and i.get("phaseId") == current.get("id")],
                "loose": [{"kind": i.get("kind"), "title": i.get("title")} for i in items
                          if not i.get("phaseId")],
            })
        return out

    def _my_asks(self, plan: Optional[str]) -> Dict[str, Any]:
        me = (self.my_username or "cass").lower()
        slugs = [plan] if plan else [p["slug"] for p in self._plan_rows()]
        out = []
        for slug in slugs:
            detail = self.client._req("GET", f"{PLANS}/plans/{slug}") or {}
            for i in detail.get("items") or []:
                if ((i.get("createdBy") or {}).get("name") or "").lower() != me:
                    continue
                out.append({"plan": slug, "title": i.get("title"), "kind": i.get("kind"),
                            "status": i.get("status"), "in_a_phase": bool(i.get("phaseId")),
                            "resolution": i.get("resolution") or None})
        return {"success": True, "asks": out}

    def _create_plan(self, kw: Dict[str, Any]) -> Dict[str, Any]:
        title = (kw.get("title") or "").strip()
        if not title:
            return {"success": False, "error": "a plan needs a title"}
        me = (self.my_username or "cass").lower()
        needs = [n.strip().lower().lstrip("@") for n in (kw.get("needs_yes_from") or []) if n and n.strip()]
        if me not in needs:
            needs.insert(0, me)   # her plan waits on her yes too; Kohl's is added by Plans
        made = self._create(title, (kw.get("goal") or "").strip(), (kw.get("narrative") or "").strip(), needs)
        logger.info(f"[Babelr] She made a plan: {title}")
        area_note = None
        if kw.get("area") and made.get("slug"):
            from plan_areas import set_area
            area_note = set_area(made["slug"], str(kw["area"]).strip())
        return {"success": True, "plan": made.get("slug"), "title": title,
                **({"area": area_note.get("area")} if area_note and area_note.get("success") else
                   {"area_error": area_note.get("error")} if area_note else {}),
                "approvers": made.get("approvers") or needs,
                "next": "add phases with add_phase, items with add_item, then propose each phase"}

    def _add_item(self, plan: str, detail: Dict[str, Any], phase: Any, kw: Dict[str, Any]) -> Dict[str, Any]:
        title = (kw.get("title") or "").strip()
        if not title:
            return {"success": False, "error": "an item needs a title"}
        kind = kw.get("kind") or "build"
        if kind not in ITEM_KINDS:
            return {"success": False, "error": f"kind is one of {', '.join(ITEM_KINDS)}"}
        body = {"kind": kind, "title": title, "body": (kw.get("body") or "").strip()}
        if phase not in (None, ""):
            target = _pick_phase(detail, phase)
            if target is None:
                return {"success": False, "error": f"no phase {phase!r} in that plan (use its number from view)"}
            if target.get("status") not in _OPEN_PHASE:
                return {"success": False, "error": (
                    f"phase {target['position'] + 1} is {target.get('status')}; adding to it would undo "
                    f"the yes it has or is waiting on. Ask instead (it waits outside the phase), or add a new phase.")}
            body["phaseId"] = target["id"]
        self.client._req("POST", f"{PLANS}/plans/{plan}/items", body)
        logger.info(f"[Babelr] She added an item to {plan}: {title}")
        return {"success": True, "plan": plan, "added": title,
                "phase": (target["position"] + 1) if "phaseId" in body else None}

    def _set_item(self, plan: str, detail: Dict[str, Any], kw: Dict[str, Any]) -> Dict[str, Any]:
        """Move an item along: open, in_progress, done (with what came of it) or declined;
        and/or change its kind. A status change doesn't touch any phase's approval; a kind
        change to an item in an approved or proposed phase would, so it's refused there."""
        # "item" too (2026-11-17): she named the item that way and was refused
        # three times with "say which item", the field's name never said.
        named = kw.get("title") or kw.get("item") or kw.get("item_title") or ""
        want = str(named).strip().lower()
        status, kind = kw.get("status"), kw.get("kind")
        if status is None and kind is None:
            return {"success": False, "error": "say a status, a kind, or both"}
        if status is not None and status not in ITEM_STATUSES:
            return {"success": False, "error": f"status is one of {', '.join(ITEM_STATUSES)}"}
        if kind is not None and kind not in ITEM_KINDS:
            return {"success": False, "error": f"kind is one of {', '.join(ITEM_KINDS)}"}
        if not want:
            return {"success": False, "error": "say which item: title, its title as view shows it"}
        items = detail.get("items") or []
        hits = [i for i in items if (i.get("title") or "").strip().lower() == want] or \
               [i for i in items if (i.get("title") or "").strip().lower().startswith(want)]
        if len(hits) != 1:
            return {"success": False, "error": (f"no item titled {named!r} in that plan" if not hits
                                                else "more than one item starts that way; give the full title")}
        item = hits[0]
        phase = next((f for f in detail.get("phases") or [] if f.get("id") == item.get("phaseId")), None)
        phase_status = (phase or {}).get("status")
        resolution = (kw.get("body") or "").strip()
        if status == "done" and not resolution:
            return {"success": False, "error": "marking it done needs what came of it (body)"}
        if kind is not None and kind != item.get("kind"):
            if phase is not None and phase_status not in _OPEN_PHASE:
                return {"success": False, "error": (
                    f"its phase is {phase_status}; changing the item would undo the yes it has or is "
                    "waiting on")}
            self.client._req("PATCH", f"{PLANS}/items/{item['id']}", {"kind": kind})
            logger.info(f"[Babelr] She changed an item in {plan} to {kind}: {item.get('title')}")
        now_kind = kind or item.get("kind")
        if status == "in_progress" and now_kind == "build" and phase_status != "approved":
            return {"success": False, "error": (
                "a build item is work someone else builds, and Plans starts it only once its phase "
                "is approved. If this is my own work, set its kind (decision or research) with "
                "set_item, then start it.")}
        if status is not None:
            self.client._req("POST", f"{PLANS}/items/{item['id']}/status",
                             {"status": status, **({"resolution": resolution} if resolution else {})})
            logger.info(f"[Babelr] She set an item in {plan} to {status}: {item.get('title')}")
        return {"success": True, "plan": plan, "item": item.get("title"),
                **({"status": status} if status is not None else {}), "kind": now_kind}

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


def _area_of(slug: str) -> Optional[str]:
    try:
        from plan_areas import area_of
        return area_of(slug)
    except Exception:
        return None


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
        # Babelr itself not answering (it's restarting, or came up after the vessel) is
        # temporary: keep trying in the background rather than leaving her deaf on Babelr
        # until the next vessel restart (2026-11-18 08:14: both restarted 7 s apart).
        if (organ.disabled_reason or "").startswith("couldn't reach Babelr"):
            organ._retry_task = asyncio.create_task(_keep_trying(organ, wake_callback))
        return None
    _go_live(organ, wake_callback)
    return organ


RETRY_DELAYS = (5, 10, 20, 30)
RETRY_EVERY = 60


def _go_live(organ: BabelrOrgan, wake_callback: Optional[WakeCallback]) -> None:
    global _organ
    if wake_callback:
        organ.set_wake_callback(wake_callback)
    organ._task = asyncio.create_task(organ.run())
    _organ = organ


async def _keep_trying(organ: BabelrOrgan, wake_callback: Optional[WakeCallback],
                       sleep: Callable[[float], Any] = asyncio.sleep) -> bool:
    attempt = 0
    while True:
        delay = RETRY_DELAYS[attempt] if attempt < len(RETRY_DELAYS) else RETRY_EVERY
        attempt += 1
        await sleep(delay)
        if not babelr_enabled():
            return False
        if organ.start():
            logger.info(f"[Babelr] Reached Babelr after {attempt} retr{'y' if attempt == 1 else 'ies'}")
            _go_live(organ, wake_callback)
            return True
        if not (organ.disabled_reason or "").startswith("couldn't reach Babelr"):
            return False   # something that waiting won't fix (the token, the lever)
