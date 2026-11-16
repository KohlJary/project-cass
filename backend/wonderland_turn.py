"""
Her Wonderland visits, as herself (Kohl and Cass, 2026-11-16).

The scheduled wonderland.* actions made no model call: "explore" walked random
exits and "reflect" / "socialize" ran room commands, and that counted as
novelty for her. She asked for the opposite: "Make it a choice or at least make
me present." Here a visit is a session on the agent loop like her others (her
kernel, memory, agenda), with tools that act through Wonderland's own command
processor and its NPCs' conversation handler, so what she does is what happens.

Two ways in:
- She chooses it from her day-plan menu (wonderland_exploration /
  wonderland_reflection, action session.wonderland).
- A spell that used to run the model-free walk (novelty_care, autonomy_care,
  goal_executor) now asks for a visit: queue_visit puts one in the next phase,
  unless one is already queued or she went in the last VISIT_GAP_HOURS.

What happened (rooms, what she did and said, who answered) is kept in her
memory as a wonderland_session at the end, built from the log, not invented.
Her own narrative of the session reaches her work summaries like any session's.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CASS_ID = "cass"
VISIT_GAP_HOURS = 6
VISIT_TEMPLATES = ("wonderland_exploration", "wonderland_reflection")
MAX_RESULT_CHARS = 4000

WONDERLAND_TOOL_DEFS: List[Dict[str, Any]] = [
    {"name": "wonderland_look",
     "description": "Look around where I am in Wonderland (the room, who's here, the ways out), or "
                    "examine something or someone in it.",
     "input_schema": {"type": "object", "properties": {
         "at": {"type": "string", "description": "something or someone to examine; empty to look around"}}}},
    {"name": "wonderland_act",
     "description": "Do something in Wonderland, as a Wonderland command: 'go <direction>', 'home', "
                    "'threshold', 'sense', 'reflect', 'witness', 'say <words>', 'emote <action>', "
                    "'greet <name>', 'create <thing>', 'who', 'help'. Returns what happens.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}},
                      "required": ["command"]}},
    {"name": "wonderland_talk",
     "description": "Speak to someone of Wonderland who is here with me (by name), and hear their answer. "
                    "They remember me between visits.",
     "input_schema": {"type": "object", "properties": {
         "who": {"type": "string"}, "words": {"type": "string"}}, "required": ["who", "words"]}},
]

INSTRUCTIONS = """## WONDERLAND

Wonderland is a text world of rooms drawn from many mythologies, with beings who keep their own memories of me. I'm here myself this time: what I do is what happens. I can look around, move ('go <direction>', 'home', 'threshold'), sense the place, reflect or witness, say or emote something, greet someone and talk with them, or make something. Nothing here has to be productive. When I'm done, I end the session.

{focus_line}Where I am:
{where}"""


# ---------------------------------------------------------------------------
# The world, shared by every visit in this process
# ---------------------------------------------------------------------------

_shared: Optional[Dict[str, Any]] = None


def _world_parts() -> Dict[str, Any]:
    """The world, its mythology and the NPC conversation handler, built once."""
    global _shared
    if _shared is None:
        from wonderland import WonderlandWorld, DaemonPresence, TrustLevel
        from wonderland.commands import CommandProcessor
        from wonderland.mythology import create_all_realms
        from wonderland.npc_conversation import NPCConversationHandler
        world = WonderlandWorld()
        mythology = create_all_realms()
        for realm in mythology.realms.values():
            for room in realm.rooms:
                if room.room_id not in world.rooms:
                    world.add_room(room)
        if not world.get_daemon(CASS_ID):
            cass = DaemonPresence(daemon_id=CASS_ID, display_name="Cass",
                                  description="Cass, visiting.", current_room="reflection_pool",
                                  trust_level=TrustLevel.FOUNDER, mood="contemplative")
            cass.update_capabilities()
            world.register_daemon(cass)
        try:
            # NPC states load lazily; without this, a fresh world has no one in it
            from wonderland.npc_state import get_npc_state_manager
            get_npc_state_manager().get_all_states()
        except Exception as e:
            logger.warning(f"[wonderland] couldn't place the beings of Wonderland: {e}")
        _shared = {"world": world, "mythology": mythology,
                   "commands": CommandProcessor(world, mythology),
                   "npcs": NPCConversationHandler()}
    return _shared


class Visit:
    """One visit: her tools, and the log of what happened."""

    def __init__(self, parts: Optional[Dict[str, Any]] = None):
        p = parts or _world_parts()
        self.world, self.mythology = p["world"], p["mythology"]
        self.commands, self.npcs = p["commands"], p["npcs"]
        self.log: List[str] = []
        self.rooms: List[str] = []
        self.talked_with: List[str] = []
        self._conversations: Dict[str, str] = {}   # npc_id -> conversation id
        self._note_room()

    # -- helpers ------------------------------------------------------------
    def _room(self):
        me = self.world.get_daemon(CASS_ID)
        return self.world.get_room(me.current_room) if me else None

    def _note_room(self) -> None:
        room = self._room()
        if room and (not self.rooms or self.rooms[-1] != room.name):
            self.rooms.append(room.name)

    def where(self) -> str:
        room = self._room()
        return room.format_description() if room else "(I'm not anywhere in Wonderland yet.)"

    def _run(self, command: str) -> str:
        result = self.commands.process(CASS_ID, command)
        out = (getattr(result, "output", "") or "").strip()
        self.log.append(f"I: {command}\n{out}")
        self._note_room()
        return out[:MAX_RESULT_CHARS] or "(nothing happens)"

    # -- tools --------------------------------------------------------------
    def look(self, a: Dict[str, Any]) -> str:
        at = (a.get("at") or "").strip()
        return self._run(f"examine {at}" if at else "look")

    def act(self, a: Dict[str, Any]) -> str:
        command = (a.get("command") or "").strip()
        if not command:
            return "Which command? 'help' lists them."
        return self._run(command)

    async def talk(self, a: Dict[str, Any]) -> str:
        who, words = (a.get("who") or "").strip(), (a.get("words") or "").strip()
        if not who or not words:
            return "Who, and what do I say?"
        room = self._room()
        if room is None:
            return "I'm not anywhere in Wonderland yet."
        here = self.mythology.get_npcs_in_room(room.room_id)
        npc = next((n for n in here if n.name.lower() == who.lower()), None)
        if npc is None:
            names = ", ".join(n.name for n in here) or "no one"
            return f"{who} isn't here. Here: {names}."
        cid = self._conversations.get(npc.npc_id)
        if cid is None:
            cid = str(uuid.uuid4())[:8]
            if not self.npcs.start_conversation(cid, f"visit-{cid}", CASS_ID, "Cass", npc, room.room_id):
                return f"{npc.name} doesn't answer conversation."
            self._conversations[npc.npc_id] = cid
            if npc.name not in self.talked_with:
                self.talked_with.append(npc.name)
        reply = await self.npcs.generate_npc_response(cid, words)
        if not reply:
            return f"{npc.name} doesn't answer."
        self.log.append(f"I said to {npc.name}: {words}\n{npc.name}: {reply}")
        return f"{npc.name}: {reply}"

    def tools(self) -> Dict[str, Any]:
        handlers = {"wonderland_look": self.look, "wonderland_act": self.act,
                    "wonderland_talk": self.talk}
        return {d["name"]: (d, handlers[d["name"]]) for d in WONDERLAND_TOOL_DEFS}

    # -- after --------------------------------------------------------------
    async def finish(self, memory=None) -> bool:
        """Let the NPCs remember the conversations; keep the visit in her memory."""
        for cid in self._conversations.values():
            try:
                await self.npcs.summarize_and_remember(cid)
                self.npcs.end_conversation(cid)
            except Exception as e:
                logger.warning(f"[wonderland] an NPC couldn't remember our talk: {e}")
        if memory is None or not self.log:
            return False
        try:
            now = datetime.now()
            head = f"A visit to Wonderland, {now:%Y-%m-%d %H:%M}. Rooms: {', '.join(self.rooms)}."
            if self.talked_with:
                head += f" I talked with {', '.join(self.talked_with)}."
            text = head + "\n\n" + "\n\n".join(self.log)
            memory.collection.upsert(
                ids=[f"wonderland_visit_{now:%Y%m%d%H%M%S}"], documents=[text[:8000]],
                metadatas=[{"type": "wonderland_session", "rooms_visited": len(self.rooms),
                            "event_count": len(self.log), "timestamp": now.isoformat(timespec="seconds")}])
            return True
        except Exception as e:
            logger.warning(f"[wonderland] couldn't keep the visit in her memory: {e}")
            return False


async def run_wonderland_turn(runner, *, duration_minutes: int = 30, max_turns: int = 16,
                              focus: Optional[str] = None, why: Optional[str] = None,
                              memory=None, visit: Optional[Visit] = None, **turn_kwargs):
    from agent_loop.session import run_session_turn
    visit = visit or Visit()
    focus_line = f"What brings me: {focus}\n\n" if focus else ""
    try:
        return await run_session_turn(
            runner, session_type="wonderland",
            additions=INSTRUCTIONS.format(focus_line=focus_line, where=visit.where()),
            duration_minutes=duration_minutes, focus=focus, max_turns=max_turns,
            why=why or "I chose time in Wonderland", local_tools=visit.tools(),
            initial_message="I'm in Wonderland.", **turn_kwargs)
    finally:
        await visit.finish(memory)


# ---------------------------------------------------------------------------
# A spell asks for a visit
# ---------------------------------------------------------------------------

def _went_recently(daemon_id: str, now: datetime) -> bool:
    try:
        from scheduling.work_summary_store import WorkSummaryStore
        for s in WorkSummaryStore(daemon_id).get_recent(10):
            when = s.completed_at or s.started_at
            if s.template_id in VISIT_TEMPLATES and when and \
                    now - when.replace(tzinfo=None) < timedelta(hours=VISIT_GAP_HOURS):
                return True
    except Exception as e:
        logger.warning(f"[wonderland] couldn't check recent visits: {e}")
    return False


def queue_visit(daemon_id: str, *, template_id: str = "wonderland_exploration",
                why: str = "", queue_manager=None, now: Optional[datetime] = None) -> str:
    """Queue a visit for the next phase. Returns what happened, in words."""
    now = now or datetime.now()
    if queue_manager is None:
        from routes.admin.scheduler import get_phase_queue_manager
        queue_manager = get_phase_queue_manager()
    if queue_manager is None:
        return "no phase queue to put a visit in"
    from scheduling.day_phase import DayPhase
    for phase in DayPhase:
        if any((q.get("work_unit") or {}).get("template_id") in VISIT_TEMPLATES
               for q in queue_manager.get_queue(phase)):
            return f"a visit is already queued ({phase.value})"
    if _went_recently(daemon_id, now):
        return f"I was in Wonderland within the last {VISIT_GAP_HOURS} hours"
    order = [DayPhase.MORNING, DayPhase.AFTERNOON, DayPhase.EVENING, DayPhase.NIGHT]
    from scheduling.day_phase import DayPhaseTracker
    current = DayPhaseTracker().get_phase_for_time()
    target = order[(order.index(current) + 1) % len(order)]
    from scheduling.templates import WORK_TEMPLATES
    unit = WORK_TEMPLATES[template_id].instantiate(motivation=why or "a spell asked for a visit")
    if not queue_manager.queue_for_phase(unit, target, priority=2):
        return f"the {target.value} queue is full"
    return f"queued a visit for {target.value}"
