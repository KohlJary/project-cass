"""
Grimoire Admin API

Endpoints for managing and monitoring the Grimoire spell system.
Designed for modularity - can be extracted for standalone Grimoire app.

Endpoints:
- GET  /grimoire/status          - Manager status
- GET  /grimoire/spells          - List all spells
- GET  /grimoire/spells/:name    - Get spell details
- GET  /grimoire/spells/:name/source - Get spell source code
- POST /grimoire/spells/:name/cast   - Execute spell manually
- POST /grimoire/spells/compile  - Validate/compile spell source
- POST /grimoire/spells/reload   - Reload spells from disk
- GET  /grimoire/execution-log   - Recent executions
- GET  /grimoire/cooldowns       - Spell cooldown status
- GET  /grimoire/triggers        - List all indexed triggers
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, List, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/grimoire", tags=["grimoire"])

# Module-level reference to the Grimoire manager
_grimoire_manager = None
_spells_directory: Optional[Path] = None


def init_grimoire_manager(manager, spells_dir: Path = None) -> None:
    """Initialize the Grimoire manager reference."""
    global _grimoire_manager, _spells_directory
    _grimoire_manager = manager
    _spells_directory = spells_dir


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class GrimoireStatusResponse(BaseModel):
    """Grimoire manager status."""
    shadow_mode: bool
    trace_enabled: bool
    spells_loaded: int
    services_configured: bool
    recent_executions: int
    spells_directory: Optional[str]
    timer_spells_count: int = 0
    cron_support: bool = False


class SpellSummary(BaseModel):
    """Brief spell info for list view."""
    name: str
    author: Optional[str]
    priority: int
    cooldown_minutes: int
    tags: List[str]
    trigger_count: int
    statement_count: int
    enabled: bool = True


class TriggerInfo(BaseModel):
    """Trigger information."""
    type: str  # need, affect, event, timer, manual
    target: Optional[str]  # need/affect name, event type, timer spec, manual label
    condition: Optional[str]  # human-readable condition


class StatementInfo(BaseModel):
    """Statement/action information."""
    type: str  # log, task, care, delta, ask, reflect, if, foreach, etc.
    summary: str  # Human-readable summary of what this statement does
    details: Optional[dict] = None  # Additional structured details


class SpellDetail(BaseModel):
    """Full spell details."""
    name: str
    author: Optional[str]
    version: Optional[str]
    description: Optional[str]
    priority: int
    cooldown_minutes: int
    tags: List[str]
    triggers: List[TriggerInfo]
    statements: List[StatementInfo]
    statement_count: int
    cooldown_remaining_seconds: Optional[float]
    last_executed: Optional[str]


class SpellSourceResponse(BaseModel):
    """Spell source code."""
    name: str
    source: str
    file_path: Optional[str]


class CompileRequest(BaseModel):
    """Request to compile spell source."""
    source: str
    validate_only: bool = True  # If False, load into registry


class CompileResponse(BaseModel):
    """Result of compilation."""
    success: bool
    spell_name: Optional[str]
    error: Optional[str]
    warnings: List[str] = []
    trigger_count: int = 0
    statement_count: int = 0


class CastRequest(BaseModel):
    """Request to cast a spell manually."""
    context: dict = {}  # Optional context data for the spell


class CastResponse(BaseModel):
    """Result of manual spell cast."""
    success: bool
    spell_name: str
    status: str
    reason: Optional[str]
    execution_time_ms: float
    trace: Optional[List[str]]


class ExecutionLogEntry(BaseModel):
    """A spell execution record."""
    spell_name: str
    trigger_type: str
    status: str
    reason: Optional[str]
    execution_time_ms: float
    timestamp: Optional[str]


class CooldownEntry(BaseModel):
    """Spell cooldown status."""
    spell_name: str
    cooldown_minutes: int
    last_executed: Optional[str]
    remaining_seconds: float
    can_execute: bool


class TimerStatusEntry(BaseModel):
    """Timer trigger status."""
    spell_name: str
    interval_minutes: Optional[float]
    cron_expr: Optional[str]
    last_run: Optional[str]
    last_run_ago_minutes: Optional[float]
    next_run_in_minutes: Optional[float]


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/status", response_model=GrimoireStatusResponse)
async def get_grimoire_status():
    """Get Grimoire manager status."""
    if not _grimoire_manager:
        raise HTTPException(status_code=503, detail="Grimoire not initialized")

    status = _grimoire_manager.get_status()
    return GrimoireStatusResponse(
        shadow_mode=status["shadow_mode"],
        trace_enabled=status["trace_enabled"],
        spells_loaded=status["spells_loaded"],
        services_configured=status["services_configured"],
        recent_executions=status["recent_executions"],
        spells_directory=str(_spells_directory) if _spells_directory else None,
        timer_spells_count=status.get("timer_spells_count", 0),
        cron_support=status.get("cron_support", False),
    )


@router.get("/spells", response_model=List[SpellSummary])
async def list_spells():
    """List all loaded spells."""
    if not _grimoire_manager:
        raise HTTPException(status_code=503, detail="Grimoire not initialized")

    spells = _grimoire_manager.get_loaded_spells()
    return [
        SpellSummary(
            name=s["name"],
            author=s.get("author"),
            priority=s["priority"],
            cooldown_minutes=s["cooldown_minutes"],
            tags=s.get("tags", []),
            trigger_count=s["trigger_count"],
            statement_count=s["statement_count"],
        )
        for s in spells
    ]


@router.get("/spells/{name}", response_model=SpellDetail)
async def get_spell(name: str):
    """Get detailed information about a spell."""
    if not _grimoire_manager:
        raise HTTPException(status_code=503, detail="Grimoire not initialized")

    spell = _grimoire_manager.registry.get_spell(name)
    if not spell:
        raise HTTPException(status_code=404, detail=f"Spell not found: {name}")

    # Build trigger info
    triggers = []
    for t in spell.triggers:
        trigger_info = _trigger_to_info(t)
        triggers.append(trigger_info)

    # Check cooldown status
    import time
    last_exec_time = _grimoire_manager._spell_cooldowns.get(name)
    cooldown_remaining = None
    last_executed = None

    if last_exec_time:
        last_executed = datetime.fromtimestamp(last_exec_time).isoformat()
        elapsed = time.time() - last_exec_time
        cooldown_seconds = spell.metadata.cooldown_minutes * 60
        remaining = cooldown_seconds - elapsed
        cooldown_remaining = max(0, remaining)

    # Build statement info
    statements = [_statement_to_info(stmt) for stmt in spell.body]

    return SpellDetail(
        name=spell.metadata.name,
        author=spell.metadata.author,
        version=getattr(spell.metadata, 'version', None),
        description=getattr(spell.metadata, 'description', None),
        priority=spell.metadata.priority,
        cooldown_minutes=spell.metadata.cooldown_minutes,
        tags=spell.metadata.tags,
        triggers=triggers,
        statements=statements,
        statement_count=len(spell.body),
        cooldown_remaining_seconds=cooldown_remaining,
        last_executed=last_executed,
    )


@router.get("/spells/{name}/source", response_model=SpellSourceResponse)
async def get_spell_source(name: str):
    """Get the source code for a spell."""
    if not _grimoire_manager:
        raise HTTPException(status_code=503, detail="Grimoire not initialized")

    spell = _grimoire_manager.registry.get_spell(name)
    if not spell:
        raise HTTPException(status_code=404, detail=f"Spell not found: {name}")

    # Try to find the source file
    source = None
    file_path = None

    if _spells_directory:
        # Look for the spell file
        for path in _spells_directory.glob("**/*.spell"):
            try:
                content = path.read_text()
                # Quick check if this is the right spell
                if f'NAME "{name}"' in content or f"NAME '{name}'" in content:
                    source = content
                    file_path = str(path)
                    break
            except Exception:
                continue

    if not source:
        # Reconstruct from AST (basic reconstruction)
        source = _spell_to_source(spell)

    return SpellSourceResponse(
        name=name,
        source=source,
        file_path=file_path,
    )


@router.post("/spells/{name}/cast", response_model=CastResponse)
async def cast_spell(name: str, request: CastRequest):
    """Manually execute a spell."""
    if not _grimoire_manager:
        raise HTTPException(status_code=503, detail="Grimoire not initialized")

    spell = _grimoire_manager.registry.get_spell(name)
    if not spell:
        raise HTTPException(status_code=404, detail=f"Spell not found: {name}")

    # Check if spell has a manual trigger or allow force cast
    has_manual = any(
        hasattr(t, '__class__') and t.__class__.__name__ == 'ManualTrigger'
        for t in spell.triggers
    )

    # Execute the spell
    result = await _grimoire_manager._execute_spell(
        spell,
        request.context,
        "manual_api"
    )

    return CastResponse(
        success=result.status in ("completed", "ok"),
        spell_name=result.spell_name,
        status=result.status,
        reason=result.reason,
        execution_time_ms=result.execution_time_ms,
        trace=result.trace,
    )


@router.post("/spells/compile", response_model=CompileResponse)
async def compile_spell(request: CompileRequest):
    """Validate and optionally load a spell from source."""
    from grimoire import Parser, ParseError

    try:
        parser = Parser(request.source)
        spell = parser.parse()

        response = CompileResponse(
            success=True,
            spell_name=spell.metadata.name,
            trigger_count=len(spell.triggers),
            statement_count=len(spell.body),
        )

        # Load into registry if requested
        if not request.validate_only and _grimoire_manager:
            _grimoire_manager.registry._register_spell(spell, spell.metadata.name)

        return response

    except ParseError as e:
        return CompileResponse(
            success=False,
            error=str(e),
        )
    except Exception as e:
        return CompileResponse(
            success=False,
            error=f"Unexpected error: {e}",
        )


@router.post("/spells/reload")
async def reload_spells():
    """Reload all spells from the spells directory."""
    if not _grimoire_manager:
        raise HTTPException(status_code=503, detail="Grimoire not initialized")

    if not _spells_directory:
        raise HTTPException(status_code=400, detail="No spells directory configured")

    # Clear existing spells
    _grimoire_manager.registry.spells.clear()
    _grimoire_manager.registry._need_triggers.clear()
    _grimoire_manager.registry._affect_triggers.clear()
    _grimoire_manager.registry._event_triggers.clear()
    _grimoire_manager.registry._timer_triggers.clear()
    _grimoire_manager.registry._manual_triggers.clear()

    # Reload
    count = _grimoire_manager.load_spells(_spells_directory)

    return {"reloaded": count, "directory": str(_spells_directory)}


@router.get("/execution-log", response_model=List[ExecutionLogEntry])
async def get_execution_log(
    limit: int = Query(default=20, le=100),
    use_db: bool = Query(default=False, description="Use persisted history instead of in-memory log"),
):
    """Get recent spell executions."""
    if not _grimoire_manager:
        raise HTTPException(status_code=503, detail="Grimoire not initialized")

    if use_db and _grimoire_manager.daemon_id:
        try:
            from grimoire.persistence import get_execution_log as get_db_log
            db_log = get_db_log(_grimoire_manager.daemon_id, limit=limit)
            return [
                ExecutionLogEntry(
                    spell_name=entry["spell_name"],
                    trigger_type=entry["trigger_type"],
                    status=entry["status"],
                    reason=entry.get("reason"),
                    execution_time_ms=entry.get("execution_time_ms"),
                    timestamp=entry.get("executed_at"),
                )
                for entry in db_log
            ]
        except Exception:
            pass  # Fall back to in-memory

    log = _grimoire_manager.get_execution_log(limit)
    return [
        ExecutionLogEntry(
            spell_name=entry["spell_name"],
            trigger_type=entry["trigger_type"],
            status=entry["status"],
            reason=entry.get("reason"),
            execution_time_ms=entry["execution_time_ms"],
            timestamp=None,
        )
        for entry in log
    ]


@router.get("/execution-stats")
async def get_execution_stats(days: int = Query(default=7, le=30)):
    """Get execution statistics from persisted history."""
    if not _grimoire_manager:
        raise HTTPException(status_code=503, detail="Grimoire not initialized")

    if not _grimoire_manager.daemon_id:
        return {"error": "Persistence not enabled"}

    try:
        from grimoire.persistence import get_execution_stats as get_stats
        return get_stats(_grimoire_manager.daemon_id, days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cooldowns", response_model=List[CooldownEntry])
async def get_cooldowns():
    """Get cooldown status for all spells."""
    if not _grimoire_manager:
        raise HTTPException(status_code=503, detail="Grimoire not initialized")

    import time
    now = time.time()
    entries = []

    for name, spell in _grimoire_manager.registry.spells.items():
        cooldown_minutes = spell.metadata.cooldown_minutes
        last_exec = _grimoire_manager._spell_cooldowns.get(name)

        if last_exec:
            elapsed = now - last_exec
            cooldown_seconds = cooldown_minutes * 60
            remaining = max(0, cooldown_seconds - elapsed)
            can_execute = remaining <= 0
            last_executed = datetime.fromtimestamp(last_exec).isoformat()
        else:
            remaining = 0
            can_execute = True
            last_executed = None

        entries.append(CooldownEntry(
            spell_name=name,
            cooldown_minutes=cooldown_minutes,
            last_executed=last_executed,
            remaining_seconds=remaining,
            can_execute=can_execute,
        ))

    return entries


@router.get("/timers", response_model=List[TimerStatusEntry])
async def get_timer_status():
    """Get timer trigger scheduling status."""
    if not _grimoire_manager:
        raise HTTPException(status_code=503, detail="Grimoire not initialized")

    from datetime import datetime
    status_list = _grimoire_manager.get_timer_status()

    return [
        TimerStatusEntry(
            spell_name=entry["spell_name"],
            interval_minutes=entry.get("interval_minutes"),
            cron_expr=entry.get("cron_expr"),
            last_run=datetime.fromtimestamp(entry["last_run"]).isoformat() if entry.get("last_run") else None,
            last_run_ago_minutes=entry.get("last_run_ago_minutes"),
            next_run_in_minutes=entry.get("next_run_in_minutes"),
        )
        for entry in status_list
    ]


@router.get("/triggers")
async def get_triggers():
    """Get all indexed triggers by type."""
    if not _grimoire_manager:
        raise HTTPException(status_code=503, detail="Grimoire not initialized")

    registry = _grimoire_manager.registry

    return {
        "need_triggers": [
            {"spell": spell.metadata.name, "trigger": _trigger_to_info(t).dict()}
            for spell, t in registry._need_triggers
        ],
        "affect_triggers": [
            {"spell": spell.metadata.name, "trigger": _trigger_to_info(t).dict()}
            for spell, t in registry._affect_triggers
        ],
        "event_triggers": [
            {"spell": spell.metadata.name, "trigger": _trigger_to_info(t).dict()}
            for spell, t in registry._event_triggers
        ],
        "timer_triggers": [
            {"spell": spell.metadata.name, "trigger": _trigger_to_info(t).dict()}
            for spell, t in registry._timer_triggers
        ],
        "manual_triggers": [
            {"spell": spell.metadata.name, "trigger": _trigger_to_info(t).dict()}
            for spell, t in registry._manual_triggers
        ],
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _trigger_to_info(trigger) -> TriggerInfo:
    """Convert a trigger AST node to TriggerInfo."""
    from grimoire import (
        NeedTrigger, AffectTrigger, EventTrigger, TimerTrigger, ManualTrigger
    )

    if isinstance(trigger, NeedTrigger):
        condition = _comparison_to_string(trigger.comparison, trigger.threshold)
        return TriggerInfo(
            type="need",
            target=trigger.need_name,
            condition=condition,
        )
    elif isinstance(trigger, AffectTrigger):
        condition = _comparison_to_string(trigger.comparison, trigger.threshold)
        return TriggerInfo(
            type="affect",
            target=trigger.affect_name,
            condition=condition,
        )
    elif isinstance(trigger, EventTrigger):
        return TriggerInfo(
            type="event",
            target=trigger.event_type,
            condition=None,
        )
    elif isinstance(trigger, TimerTrigger):
        if trigger.cron_expr:
            target = f"CRON {trigger.cron_expr}"
        else:
            target = f"EVERY {trigger.interval_minutes}m"
        return TriggerInfo(
            type="timer",
            target=target,
            condition=None,
        )
    elif isinstance(trigger, ManualTrigger):
        return TriggerInfo(
            type="manual",
            target=trigger.label,
            condition=None,
        )
    else:
        return TriggerInfo(
            type="unknown",
            target=None,
            condition=None,
        )


def _comparison_to_string(comparison, threshold) -> str:
    """Convert comparison enum to human-readable string."""
    from grimoire.ast import Comparison

    op_map = {
        Comparison.LT: "<",
        Comparison.LE: "<=",
        Comparison.GT: ">",
        Comparison.GE: ">=",
        Comparison.EQ: "==",
        Comparison.NE: "!=",
    }
    op = op_map.get(comparison, "?")
    return f"{op} {threshold}"


def _expr_to_string(expr) -> str:
    """Convert an expression to a readable string."""
    from grimoire.ast import Literal, Variable, PropertyAccess, BinaryOp, UnaryOp

    if isinstance(expr, Literal):
        if isinstance(expr.value, str):
            return f'"{expr.value}"'
        return str(expr.value)
    elif isinstance(expr, Variable):
        return f"${expr.name}"
    elif isinstance(expr, PropertyAccess):
        return f"{_expr_to_string(expr.base)}.{expr.property_name}"
    elif isinstance(expr, BinaryOp):
        return f"{_expr_to_string(expr.left)} {expr.operator} {_expr_to_string(expr.right)}"
    elif isinstance(expr, UnaryOp):
        return f"{expr.operator}{_expr_to_string(expr.operand)}"
    else:
        return str(expr)


def _statement_to_info(stmt, depth: int = 0) -> StatementInfo:
    """Convert a statement AST node to StatementInfo."""
    from grimoire.ast import (
        LogAction, TaskAction, CareAction, DeltaAction, EmitAction,
        AskStatement, RateStatement, GenerateStatement, ReflectStatement, ChooseStatement,
        IfStatement, ForEachStatement, WhileStatement, ForStatement,
        LetStatement, ExitStatement, WaitStatement, CastStatement,
        LabelStatement, GotoStatement, GosubStatement, ReturnStatement,
        ContinueStatement, BreakStatement, ResetAction, ParallelBlock,
    )

    # Actions
    if isinstance(stmt, LogAction):
        msg = _expr_to_string(stmt.message) if hasattr(stmt.message, '__class__') else str(stmt.message)
        return StatementInfo(
            type="log",
            summary=f"LOG {stmt.level} {msg}",
            details={"level": stmt.level, "message": msg},
        )

    elif isinstance(stmt, TaskAction):
        params = ", ".join(f"{k}={v}" for k, v in stmt.params.items()) if stmt.params else ""
        await_str = " AWAIT" if stmt.await_result else ""
        return StatementInfo(
            type="task",
            summary=f"TASK {stmt.action}({params}){await_str}",
            details={"action": stmt.action, "params": stmt.params, "await": stmt.await_result},
        )

    elif isinstance(stmt, CareAction):
        if stmt.action_key:
            return StatementInfo(type="care", summary=f"CARE {stmt.action_key}")
        elif stmt.need_name:
            return StatementInfo(type="care", summary=f"CARE FOR {stmt.need_name}")
        return StatementInfo(type="care", summary="CARE")

    elif isinstance(stmt, DeltaAction):
        deltas = []
        for k, v in stmt.affect_deltas.items():
            sign = "+" if v >= 0 else ""
            deltas.append(f"affect.{k} {sign}{v}")
        for k, v in stmt.need_deltas.items():
            sign = "+" if v >= 0 else ""
            deltas.append(f"need.{k} {sign}{v}")
        return StatementInfo(
            type="delta",
            summary=f"DELTA {', '.join(deltas)}",
            details={"affects": stmt.affect_deltas, "needs": stmt.need_deltas},
        )

    elif isinstance(stmt, EmitAction):
        return StatementInfo(
            type="emit",
            summary=f"EMIT {stmt.event_type}",
            details={"event_type": stmt.event_type},
        )

    # Agentic statements
    elif isinstance(stmt, AskStatement):
        q = _expr_to_string(stmt.question)
        return StatementInfo(
            type="ask",
            summary=f"ASK {q} INTO ${stmt.answer_var}",
            details={"question": q, "answer_var": stmt.answer_var},
        )

    elif isinstance(stmt, RateStatement):
        p = _expr_to_string(stmt.prompt)
        return StatementInfo(
            type="rate",
            summary=f"RATE {p} INTO ${stmt.rating_var}",
            details={"prompt": p, "rating_var": stmt.rating_var},
        )

    elif isinstance(stmt, GenerateStatement):
        p = _expr_to_string(stmt.prompt)
        return StatementInfo(
            type="generate",
            summary=f"GENERATE {p} INTO ${stmt.output_var}",
            details={"prompt": p, "output_var": stmt.output_var},
        )

    elif isinstance(stmt, ReflectStatement):
        p = _expr_to_string(stmt.prompt)
        save = f" SAVE AS {stmt.save_as}" if stmt.save_as else ""
        return StatementInfo(
            type="reflect",
            summary=f"REFLECT {p}{save}",
            details={"prompt": p, "save_as": stmt.save_as},
        )

    elif isinstance(stmt, ChooseStatement):
        p = _expr_to_string(stmt.prompt)
        return StatementInfo(
            type="choose",
            summary=f"CHOOSE {p} INTO ${stmt.choice_var}",
            details={"prompt": p, "choice_var": stmt.choice_var, "options": stmt.options},
        )

    # Control flow
    elif isinstance(stmt, IfStatement):
        cond = _expr_to_string(stmt.condition)
        return StatementInfo(
            type="if",
            summary=f"IF {cond} THEN ... END IF",
            details={"condition": cond, "then_count": len(stmt.then_body), "else_count": len(stmt.else_body) if stmt.else_body else 0},
        )

    elif isinstance(stmt, ForEachStatement):
        coll = _expr_to_string(stmt.collection)
        return StatementInfo(
            type="foreach",
            summary=f"FOR EACH ${stmt.item_var} IN {coll}",
            details={"item_var": stmt.item_var, "body_count": len(stmt.body)},
        )

    elif isinstance(stmt, WhileStatement):
        cond = _expr_to_string(stmt.condition)
        return StatementInfo(
            type="while",
            summary=f"WHILE {cond}",
            details={"condition": cond, "body_count": len(stmt.body)},
        )

    elif isinstance(stmt, ForStatement):
        return StatementInfo(
            type="for",
            summary=f"FOR ${stmt.var_name} = {_expr_to_string(stmt.start)} TO {_expr_to_string(stmt.end)}",
            details={"var": stmt.var_name, "body_count": len(stmt.body)},
        )

    elif isinstance(stmt, LetStatement):
        val = _expr_to_string(stmt.value)
        return StatementInfo(
            type="let",
            summary=f"LET ${stmt.var_name} = {val}",
            details={"var": stmt.var_name},
        )

    elif isinstance(stmt, ExitStatement):
        reason = f" '{stmt.reason}'" if stmt.reason else ""
        return StatementInfo(
            type="exit",
            summary=f"EXIT {stmt.status}{reason}",
            details={"status": stmt.status, "reason": stmt.reason},
        )

    elif isinstance(stmt, WaitStatement):
        secs = _expr_to_string(stmt.seconds)
        return StatementInfo(type="wait", summary=f"WAIT {secs}")

    elif isinstance(stmt, CastStatement):
        return StatementInfo(
            type="cast",
            summary=f"CAST {stmt.spell_ref}",
            details={"spell": stmt.spell_ref},
        )

    elif isinstance(stmt, LabelStatement):
        return StatementInfo(type="label", summary=f":{stmt.label_name}")

    elif isinstance(stmt, GotoStatement):
        return StatementInfo(type="goto", summary=f"GOTO {stmt.target_label}")

    elif isinstance(stmt, GosubStatement):
        return StatementInfo(type="gosub", summary=f"GOSUB {stmt.target_label}")

    elif isinstance(stmt, ReturnStatement):
        return StatementInfo(type="return", summary="RETURN")

    elif isinstance(stmt, ContinueStatement):
        return StatementInfo(type="continue", summary="CONTINUE")

    elif isinstance(stmt, BreakStatement):
        return StatementInfo(type="break", summary="BREAK")

    elif isinstance(stmt, ResetAction):
        return StatementInfo(type="reset", summary=f"RESET {stmt.target}")

    elif isinstance(stmt, ParallelBlock):
        return StatementInfo(
            type="parallel",
            summary=f"PARALLEL ({len(stmt.branches)} branches)",
            details={"branch_count": len(stmt.branches)},
        )

    else:
        return StatementInfo(
            type="unknown",
            summary=str(type(stmt).__name__),
        )


def _spell_to_source(spell) -> str:
    """Reconstruct basic source from spell AST (for display only)."""
    lines = []

    # Metadata
    lines.append("' === SPELL METADATA ===")
    lines.append(f'NAME "{spell.metadata.name}"')
    if spell.metadata.author:
        lines.append(f'AUTHOR "{spell.metadata.author}"')
    if getattr(spell.metadata, 'version', None):
        lines.append(f'VERSION "{spell.metadata.version}"')
    if getattr(spell.metadata, 'description', None):
        lines.append(f'DESCRIPTION "{spell.metadata.description}"')
    lines.append(f"PRIORITY {spell.metadata.priority}")
    if spell.metadata.cooldown_minutes:
        lines.append(f"COOLDOWN {spell.metadata.cooldown_minutes}")
    for tag in spell.metadata.tags:
        lines.append(f'TAG "{tag}"')
    lines.append("")

    # Triggers
    lines.append("' === TRIGGERS ===")
    for trigger in spell.triggers:
        info = _trigger_to_info(trigger)
        if info.type == "need":
            lines.append(f"ON need.{info.target} {info.condition}")
        elif info.type == "affect":
            lines.append(f"ON affect.{info.target} {info.condition}")
        elif info.type == "event":
            lines.append(f'ON EVENT "{info.target}"')
        elif info.type == "timer":
            lines.append(f"ON TIMER {info.target}")
        elif info.type == "manual":
            lines.append(f'ON MANUAL "{info.target}"')
    lines.append("")

    # Body placeholder
    lines.append("' === BODY ===")
    lines.append(f"' ({len(spell.body)} statements - source reconstruction not fully implemented)")
    lines.append("' Use the original .spell file for full source")

    return "\n".join(lines)
