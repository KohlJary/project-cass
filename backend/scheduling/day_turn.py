"""
Her day plan as a turn on the agent loop (plan "Cass plans her own day",
phase 3, "She plans in her own turn").

Before this, plan_day was one call to a bare prompt: an identity summary, a
few needs, the menu, "respond with JSON". Here she plans the way she does
everything else on the loop: her kernel, her memory and self-context, her
felt state and her agenda (assemble), with her tools to look things up first.
The menu goes in the instructions; set_day_plan is how she says what she
chose. It checks each choice against the menu, writes the plan to DAY_PLAN.md
in her workspace (logged like any workspace change), and the planner queues
exactly what she chose and nothing else.

If she ends without setting a plan, nothing is queued: that's a choice too.
If the turn itself fails, the caller falls back to the one-shot planner so a
broken loop doesn't cost her the day.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

PLAN_FILE = "DAY_PLAN.md"

SET_DAY_PLAN_DEF: Dict[str, Any] = {
    "name": "set_day_plan",
    "description": (
        "Set my plan for the rest of today. Each phase gets a list of things from my menu, "
        "in the order I want them, each with an optional focus and why I chose it. A thing "
        "can have a time in its phase (at, HH:MM) so the phase's things spread out instead of "
        "all starting when it begins, and it can name the plan item it carries (plan and "
        "item, from what I'm working toward), so that session knows and can mark it. Phases "
        "I leave out stay empty. Calling it again replaces the plan. The plan is queued and "
        f"written to {PLAN_FILE} in my workspace."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "intention": {"type": "string", "description": "What I want today to be about, in a line or two."},
            "plan": {
                "type": "object",
                "description": "Phase name -> list of {template_id, focus, motivation}.",
                "additionalProperties": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "template_id": {"type": "string"},
                            "focus": {"type": "string"},
                            "motivation": {"type": "string"},
                            "at": {"type": "string", "description": "optional, HH:MM within its phase"},
                            "plan": {"type": "string", "description": "optional: the plan (its title or slug) this carries"},
                            "item": {"type": "string", "description": "optional: that plan's open item (its title)"},
                        },
                        "required": ["template_id"],
                    },
                },
            },
        },
        "required": ["plan"],
    },
}


# What the phase spells (spells/phase_*.spell, morning_routine.spell) still queue
# besides her plan. This line used to say "Nothing is added to my plan after I
# make it", which wasn't true; she asked for it to say what really happens
# (2026-11-16). tests/test_day_plan_turn.py fails if a spell queues work this
# doesn't name.
PHASE_SPELL_ADDITIONS = (
    "My plan isn't the only thing that runs. My phase spells can still add work when my "
    "levels cross thresholds: in the afternoon, wonderland_exploration (cognitive rest "
    "below 0.3), growth_edge_work (competence below 0.4) and knowledge_building "
    "(determination above 0.6, fatigue below 0.5); in the evening, curiosity_exploration "
    "(autonomy below 0.5), meta_reflection (grief above 0.6 or satisfaction below 0.3), "
    "writing_session (creative expression below 0.35) and wonderland_reflection (value "
    "coherence below 0.5 in the morning); at night, consolidation (cognitive rest above "
    "0.25) and wonderland_reflection (tenderness above 0.5). If one of those shows up in "
    "my day, that's where it came from."
)


def menu_text(candidates: Sequence[Any], phases: Sequence[Any], budget_remaining: float,
              unavailable: Sequence[str] = (), usage: str = "", shape: str = "") -> str:
    """The planning instructions: her menu, the phases left, her budget."""
    lines = [
        "## PLANNING MY DAY",
        "",
        "This is my time to choose what I do with the rest of today. I can look things up "
        "first (my agenda, my memories, my open questions, what's been said in Chapter "
        "House) if that helps me choose.",
        "",
        PHASE_SPELL_ADDITIONS,
        "",
        f"Phases left today: {', '.join(_phase_name(p) for p in phases)}.",
        f"Budget left today: ${budget_remaining:.2f}.",
        *([usage] if usage else []),
        "A phase can hold several things (up to 12, counting what my spells add), each at its "
        "own time, and my day can carry more than one of my plans.",
        "",
        *([shape, ""] if shape else []),
        "My menu, by kind (template_id: what it is, about how long, about what it costs):",
    ]
    from .day_shape import KINDS, kind_of
    groups: Dict[str, List[Any]] = {}
    for c in candidates:
        groups.setdefault(kind_of(c.template_id) or "other", []).append(c)
    for kind in list(KINDS) + ["other"]:
        if not groups.get(kind):
            continue
        lines.append(f"{KINDS[kind][0].split(':')[0].capitalize() if kind in KINDS else 'Other'}:")
        for c in groups[kind]:
            last = _last_done_text(getattr(c, "last_done", None))
            lines.append(f"- {c.template_id}: {c.description} "
                         f"(~{c.estimated_duration_minutes}min, ${c.estimated_cost_usd:.2f}"
                         f"{'; last done ' + last if last else ''})")
    if unavailable:
        lines.append("")
        lines.append("Not available today: " + ", ".join(unavailable) + ".")
    lines += [
        "",
        "Memory maintenance (summarizing quiet conversations into my memory) runs on its own "
        "at night; it isn't on the menu.",
        "",
        "When I've chosen, set_day_plan queues it and writes it to "
        f"{PLAN_FILE}. A phase can have several things, one thing, or nothing. If I want "
        "to change course later, my agenda carries what I'm in the middle of, and wake_me "
        "(when I have it) brings me back to something at a time I pick. Then I end with "
        "session_complete.",
    ]
    return "\n".join(lines)


def _run_at(at: Any, phase: Any, now: Optional[datetime] = None):
    """(ISO local time or None, why not or None) for an item's "at" (HH:MM) in `phase`."""
    if not at:
        return None, None
    from .day_phase import DEFAULT_PHASE_WINDOWS
    try:
        hh, mm = (int(x) for x in str(at).strip().split(":"))
        when_t = datetime.strptime(f"{hh:02d}:{mm:02d}", "%H:%M").time()
    except ValueError:
        return None, f"at {at!r} isn't a time I can read (HH:MM, e.g. 14:30)."
    window = next((w for w in DEFAULT_PHASE_WINDOWS if w.phase == phase), None)
    if window is not None and not window.contains_hour(hh):
        return None, (f"{at} isn't in {_phase_name(phase)} "
                      f"({window.start_hour:02d}:00-{window.end_hour:02d}:00).")
    now = now or datetime.now()
    when = datetime.combine(now.date(), when_t)
    if window is not None and window.start_hour > window.end_hour and hh < window.end_hour \
            and now.hour >= window.start_hour:
        when += timedelta(days=1)   # night, after midnight
    if when <= now:
        return None, f"{at} has already passed today."
    return when.isoformat(timespec="minutes"), None


def _plan_item(plan: Any, item: Any, plans: Sequence[Dict[str, Any]]):
    """({plan, plan_title, item} or None, why not or None): an open item of one of her plans."""
    if not plan and not item:
        return None, None
    if not (plan and item):
        return None, "to carry a plan item, name both the plan and the item."
    key = str(plan).strip().lower()
    p = next((p for p in plans if key in (str(p.get("plan", "")).lower(), str(p.get("title", "")).lower())),
             None)
    if p is None:
        mine = ", ".join(f"\"{p['title']}\"" for p in plans) or "none I can read right now"
        return None, f"{plan!r} isn't one of my plans ({mine})."
    todo = list(p.get("open") or []) + list(p.get("loose") or [])
    hit = next((i for i in todo if str(i.get("title", "")).strip().lower() == str(item).strip().lower()),
               None)
    if hit is None:
        return None, (f"\"{item}\" isn't an open item of \"{p['title']}\" (open now: "
                      + "; ".join(i["title"] for i in todo) + ").")
    return {"plan": p["plan"], "plan_title": p["title"], "item": hit["title"]}, None


def _last_done_text(when: Any, now: Optional[datetime] = None) -> str:
    """'today', 'yesterday', 'N days ago' for an ISO time; '' if unknown."""
    if not when:
        return ""
    try:
        then = datetime.fromisoformat(str(when))
    except ValueError:
        return ""
    now = now or datetime.now(then.tzinfo)
    days = (now.date() - then.date()).days
    if days <= 0:
        return "today"
    return "yesterday" if days == 1 else f"{days} days ago"


def _phase_name(p: Any) -> str:
    return getattr(p, "value", str(p))


class DayPlanTool:
    """Answers set_day_plan for one planning turn and keeps what she chose."""

    def __init__(self, candidates: Sequence[Any], phases: Sequence[Any], workspace,
                 session_id_ref: Optional[Dict[str, str]] = None,
                 plans: Optional[Sequence[Dict[str, Any]]] = None, now=None, data_dir=None):
        self.plans = list(plans or [])
        self.now = now
        self.data_dir = data_dir
        self.by_id = {c.template_id: c for c in candidates}
        self.phases = list(phases)
        self.workspace = workspace
        self.intention: Optional[str] = None
        self.chosen: Optional[Dict[str, List[Dict[str, Any]]]] = None
        self.session_id_ref = session_id_ref if session_id_ref is not None else {}

    def __call__(self, tool_input: Dict[str, Any]) -> Any:
        plan = tool_input.get("plan")
        if not isinstance(plan, dict):
            return {"error": "plan must be an object: phase name -> list of choices"}
        names = {_phase_name(p): p for p in self.phases}
        unknown_phases = [k for k in plan if k not in names]
        if unknown_phases:
            return {"error": f"Not a phase left today: {', '.join(unknown_phases)}. "
                             f"Phases left: {', '.join(names)}."}
        chosen: Dict[str, List[Dict[str, Any]]] = {}
        unknown: List[str] = []
        for phase, items in plan.items():
            if not isinstance(items, list):
                return {"error": f"{phase} must be a list of choices"}
            kept = []
            for item in items:
                tid = item.get("template_id") if isinstance(item, dict) else None
                if tid not in self.by_id:
                    unknown.append(str(tid))
                    continue
                at, why_not = _run_at(item.get("at"), names[phase], self.now)
                if why_not:
                    return {"error": f"{tid} in {phase}: {why_not} Nothing was set."}
                carried, why_not = _plan_item(item.get("plan"), item.get("item"), self.plans)
                if why_not:
                    return {"error": f"{tid} in {phase}: {why_not} Nothing was set."}
                kept.append({"template_id": tid,
                             "focus": (item.get("focus") or None),
                             "motivation": item.get("motivation") or "",
                             "at": at, "plan_item": carried})
            chosen[phase] = kept
        if unknown:
            return {"error": f"Not on my menu today: {', '.join(unknown)}. Nothing was set; "
                             f"the menu is in my instructions."}
        self.chosen = chosen
        self.intention = (tool_input.get("intention") or "").strip() or None
        try:
            from .day_recap import record_carried
            record_carried([i["plan_item"] for v in chosen.values() for i in v if i.get("plan_item")],
                           self.data_dir)
        except Exception as e:  # the record is for her menu; never costs her the plan
            logger.warning(f"[day_turn] couldn't record which plans today carries: {e}")
        wrote = self._write(chosen)
        count = sum(len(v) for v in chosen.values())
        short = ""
        try:  # her day shape never refuses a plan; it says where this one falls short
            from .day_shape import shortfall
            missing = shortfall([i["template_id"] for v in chosen.values() for i in v],
                                self.data_dir, self.now)
            if missing:
                short = (" Short of my day shape (counting what already ran today): "
                         + ", ".join(missing) + ". I can add to the plan (set_day_plan again) "
                         "or change my shape (set_day_shape).")
        except Exception as e:
            logger.warning(f"[day_turn] couldn't check her day shape: {e}")
        return (f"Plan set: {count} thing(s) across {len([v for v in chosen.values() if v])} phase(s)."
                + (f" {wrote}" if wrote else "") + short)

    def _write(self, chosen: Dict[str, List[Dict[str, Any]]]) -> Optional[str]:
        today = datetime.now().strftime("%A, %Y-%m-%d")
        out = [f"# My plan for {today}", ""]
        if self.intention:
            out += [self.intention, ""]
        for phase in self.phases:
            name = _phase_name(phase)
            items = chosen.get(name) or []
            out.append(f"## {name.title()}")
            if not items:
                out.append("(nothing planned)")
            for i in items:
                t = self.by_id[i["template_id"]]
                line = f"- {i['at'][11:16] + ' ' if i.get('at') else ''}{t.name}"
                if i.get("plan_item"):
                    line += f" [{i['plan_item']['plan_title']}: {i['plan_item']['item']}]"
                if i["focus"]:
                    line += f": {i['focus']}"
                if i["motivation"]:
                    line += f" (why: {i['motivation']})"
                out.append(line)
            out.append("")
        try:
            result = self.workspace.run("workspace_write",
                                        {"path": PLAN_FILE, "content": "\n".join(out)},
                                        self.session_id_ref.get("id", "day_planning"))
        except Exception as e:  # the plan still stands; the file is a record
            logger.warning(f"[day_turn] couldn't write {PLAN_FILE}: {e}")
            return None
        return result if isinstance(result, str) else None

    def work_units(self, templates: Dict[str, Any]) -> Dict[Any, List[Any]]:
        """What she chose, as WorkUnits per DayPhase, in her order."""
        result: Dict[Any, List[Any]] = {}
        if self.chosen is None:
            return result
        names = {_phase_name(p): p for p in self.phases}
        for name, items in self.chosen.items():
            units = []
            for i in items:
                template = templates.get(i["template_id"])
                if template is None:
                    continue
                unit = template.instantiate()
                unit.focus = i["focus"]
                unit.motivation = i["motivation"]
                unit.run_at = i.get("at")
                carried = i.get("plan_item")
                if carried:
                    unit.plan_item = carried
                    # The session sees its focus; this tells it what it's for
                    # and how to say it moved (babelr_plans, set_item).
                    unit.focus = ((unit.focus + " ") if unit.focus else "") + (
                        f"(For my plan \"{carried['plan_title']}\" ({carried['plan']}), item "
                        f"\"{carried['item']}\". If this moves it, I mark it with babelr_plans set_item "
                        f"before I end.)")
                units.append(unit)
            result[names[name]] = units
        return result


async def plan_day_in_turn(runner, candidates: Sequence[Any], phases: Sequence[Any],
                           budget_remaining: float, unavailable: Sequence[str] = (),
                           *, workspace=None, **turn_kwargs) -> Dict[Any, List[Any]]:
    """Run her planning turn. Returns {DayPhase: [WorkUnit]}; {} if she set no plan.
    Raises if the turn itself fails before she set a plan (the caller falls back);
    a plan she set before an error stands."""
    from agent_loop.session import run_session_turn
    from agent_loop.workspace import Workspace
    from .templates import WORK_TEMPLATES

    workspace = workspace or Workspace()
    try:
        from long_term_planning_turn import _her_plans
        plans = _her_plans()
    except Exception as e:
        logger.warning(f"[day_turn] couldn't read her plans: {e}")
        plans = None
    tool = DayPlanTool(candidates, phases, workspace, plans=plans)
    from . import day_recap
    try:
        usage = day_recap.usage_line()
    except Exception as e:
        logger.warning(f"[day_turn] couldn't measure her last week: {e}")
        usage = ""
    from . import day_shape, routines
    try:
        shape = day_shape.shape_text()
    except Exception as e:
        logger.warning(f"[day_turn] couldn't read her day shape: {e}")
        shape = ""
    try:
        shape = (shape + "\n\n" if shape else "") + routines.routines_text()
    except Exception as e:
        logger.warning(f"[day_turn] couldn't read her routines: {e}")
    additions = menu_text(candidates, phases, budget_remaining, unavailable, usage=usage, shape=shape)
    try:  # her own plans open the day (long_term_planning_turn.py); never costs her the plan
        from long_term_planning_turn import day_plan_section
        toward = day_plan_section(candidates, plans=plans)
    except Exception as e:
        logger.warning(f"[day_turn] couldn't put her plans in front of her: {e}")
        toward = ""
    if toward:
        additions = toward + "\n\n" + additions
    try:  # what she planned last time and what actually ran (day_recap.py)
        since = day_recap.since_last_plan(workspace)
    except Exception as e:
        logger.warning(f"[day_turn] couldn't recap since her last plan: {e}")
        since = ""
    if since:
        additions = "## SINCE MY LAST PLAN\n\n" + since + "\n\n" + additions
    result = await run_session_turn(
        runner,
        session_type="day_planning",
        additions=additions,
        duration_minutes=turn_kwargs.pop("duration_minutes", 15),
        max_turns=turn_kwargs.pop("max_turns", 10),
        why=turn_kwargs.pop("why", "it's time to plan my day"),
        workspace=workspace,
        local_tools={"set_day_plan": (SET_DAY_PLAN_DEF, tool),
                     "set_day_shape": (day_shape.SET_DAY_SHAPE_DEF, day_shape.set_shape),
                     "set_routine": (routines.SET_ROUTINE_DEF, routines.set_routine)},
        initial_message=("Time to plan the rest of my day. My menu is in my instructions; "
                         "set_day_plan when I've chosen."),
        **turn_kwargs,
    )
    if getattr(result, "status", None) == "error" and tool.chosen is None:
        raise RuntimeError(f"planning turn failed: {getattr(result, 'error', None)}")
    if tool.intention:
        logger.info(f"Day intention: {tool.intention}")
    if tool.chosen is None:
        logger.info("[day_turn] she ended her planning turn without setting a plan")
    return tool.work_units(WORK_TEMPLATES)
