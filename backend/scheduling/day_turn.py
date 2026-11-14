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
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

PLAN_FILE = "DAY_PLAN.md"

SET_DAY_PLAN_DEF: Dict[str, Any] = {
    "name": "set_day_plan",
    "description": (
        "Set my plan for the rest of today. Each phase gets a list of things from my menu, "
        "in the order I want them, each with an optional focus and why I chose it. Phases "
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
                        },
                        "required": ["template_id"],
                    },
                },
            },
        },
        "required": ["plan"],
    },
}


def menu_text(candidates: Sequence[Any], phases: Sequence[Any], budget_remaining: float,
              unavailable: Sequence[str] = ()) -> str:
    """The planning instructions: her menu, the phases left, her budget."""
    lines = [
        "## PLANNING MY DAY",
        "",
        "This is my time to choose what I do with the rest of today. Nothing is added to "
        "my plan after I make it. I can look things up first (my agenda, my memories, my "
        "open questions, what's been said in Chapter House) if that helps me choose.",
        "",
        f"Phases left today: {', '.join(_phase_name(p) for p in phases)}.",
        f"Budget left today: ${budget_remaining:.2f}.",
        "",
        "My menu (template_id: what it is, about how long, about what it costs):",
    ]
    for c in candidates:
        lines.append(f"- {c.template_id}: {c.description} "
                     f"(~{c.estimated_duration_minutes}min, ${c.estimated_cost_usd:.2f})")
    if unavailable:
        lines.append("")
        lines.append("Not available today: " + ", ".join(unavailable) + ".")
    lines += [
        "",
        "When I've chosen, set_day_plan queues it and writes it to "
        f"{PLAN_FILE}. A phase can have several things, one thing, or nothing. If I want "
        "to change course later, my agenda carries what I'm in the middle of, and wake_me "
        "(when I have it) brings me back to something at a time I pick. Then I end with "
        "session_complete.",
    ]
    return "\n".join(lines)


def _phase_name(p: Any) -> str:
    return getattr(p, "value", str(p))


class DayPlanTool:
    """Answers set_day_plan for one planning turn and keeps what she chose."""

    def __init__(self, candidates: Sequence[Any], phases: Sequence[Any], workspace,
                 session_id_ref: Optional[Dict[str, str]] = None):
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
                kept.append({"template_id": tid,
                             "focus": (item.get("focus") or None),
                             "motivation": item.get("motivation") or ""})
            chosen[phase] = kept
        if unknown:
            return {"error": f"Not on my menu today: {', '.join(unknown)}. Nothing was set; "
                             f"the menu is in my instructions."}
        self.chosen = chosen
        self.intention = (tool_input.get("intention") or "").strip() or None
        wrote = self._write(chosen)
        count = sum(len(v) for v in chosen.values())
        return (f"Plan set: {count} thing(s) across {len([v for v in chosen.values() if v])} phase(s)."
                + (f" {wrote}" if wrote else ""))

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
                line = f"- {t.name}"
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
    tool = DayPlanTool(candidates, phases, workspace)
    result = await run_session_turn(
        runner,
        session_type="day_planning",
        additions=menu_text(candidates, phases, budget_remaining, unavailable),
        duration_minutes=turn_kwargs.pop("duration_minutes", 15),
        max_turns=turn_kwargs.pop("max_turns", 10),
        why=turn_kwargs.pop("why", "it's time to plan my day"),
        workspace=workspace,
        local_tools={"set_day_plan": (SET_DAY_PLAN_DEF, tool)},
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
