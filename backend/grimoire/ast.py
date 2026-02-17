"""
Grimoire AST (Abstract Syntax Tree) Definitions

These dataclasses represent the parsed structure of a ThymosBASIC spell.
"""

from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum, auto


# =============================================================================
# BASE CLASSES
# =============================================================================

@dataclass
class ASTNode:
    """Base class for all AST nodes."""
    # Note: line/column set via set_location() after construction
    # to avoid dataclass inheritance issues

    def set_location(self, line: int, column: int) -> "ASTNode":
        """Set source location. Returns self for chaining."""
        object.__setattr__(self, "_line", line)
        object.__setattr__(self, "_column", column)
        return self

    @property
    def line(self) -> int:
        return getattr(self, "_line", 0)

    @property
    def column(self) -> int:
        return getattr(self, "_column", 0)


@dataclass
class Expression(ASTNode):
    """Base class for expressions (things that produce values)."""
    pass


@dataclass
class Statement(ASTNode):
    """Base class for statements (things that do stuff)."""
    pass


# =============================================================================
# SPELL (TOP-LEVEL)
# =============================================================================

class SpellScope(Enum):
    """What systems a spell can interact with."""
    THYMOS = auto()
    SCHEDULER = auto()
    MEMORY = auto()
    EXTERNAL = auto()
    CREATIVE = auto()


@dataclass
class SpellMetadata:
    """Spell header metadata."""
    name: str
    author: str = "unknown"
    priority: int = 50
    cooldown_minutes: int = 0
    tags: list[str] = field(default_factory=list)
    scope: set[SpellScope] = field(default_factory=lambda: {
        SpellScope.THYMOS,
        SpellScope.SCHEDULER,
    })


@dataclass
class Spell(ASTNode):
    """A complete spell (the top-level AST node)."""
    metadata: SpellMetadata
    triggers: list["Trigger"]
    body: list[Statement]
    labels: dict[str, int] = field(default_factory=dict)  # label -> statement index
    imports: list["ImportStatement"] = field(default_factory=list)


# =============================================================================
# IMPORTS
# =============================================================================

@dataclass
class ImportStatement(ASTNode):
    """Import a spell or action from a package."""
    path: str              # e.g., "community-spells/creative/art_from_emotion"
    alias: Optional[str]   # AS <alias>
    import_type: str = "spell"  # "spell" or "action"


# =============================================================================
# TRIGGERS
# =============================================================================

@dataclass
class Trigger(ASTNode):
    """Base class for spell triggers (entry points)."""
    pass


class Comparison(Enum):
    """Comparison operators for triggers."""
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
    EQ = "=="
    NE = "!="


@dataclass
class NeedTrigger(Trigger):
    """ON need.<name> <op> <threshold>"""
    need_name: str
    comparison: Comparison
    threshold: float
    debounce_seconds: float = 0


@dataclass
class AffectTrigger(Trigger):
    """ON affect.<name> <op> <threshold>"""
    affect_name: str
    comparison: Comparison
    threshold: float
    debounce_seconds: float = 0


@dataclass
class EventTrigger(Trigger):
    """ON event.<type> [WHERE <condition>]"""
    event_type: str
    condition: Optional[Expression] = None


@dataclass
class TimerTrigger(Trigger):
    """ON TIMER EVERY <n> or ON TIMER CRON '<expr>'"""
    interval_minutes: Optional[float] = None
    cron_expr: Optional[str] = None


@dataclass
class ManualTrigger(Trigger):
    """ON MANUAL '<label>'"""
    label: str


# =============================================================================
# EXPRESSIONS
# =============================================================================

@dataclass
class Literal(Expression):
    """Literal values: numbers, strings, booleans."""
    value: Any
    literal_type: str  # "number", "string", "boolean"


@dataclass
class Variable(Expression):
    """Variable reference: $name"""
    name: str


@dataclass
class PropertyAccess(Expression):
    """Property access: need.value_coherence, affect.anxiety, $obj.field"""
    base: Expression  # Can be Variable or another PropertyAccess
    property_name: str


@dataclass
class BinaryOp(Expression):
    """Binary operation: a + b, a AND b, etc."""
    left: Expression
    operator: str  # "+", "-", "*", "/", "AND", "OR", "<", ">", "==", etc.
    right: Expression


@dataclass
class UnaryOp(Expression):
    """Unary operation: NOT x, -x"""
    operator: str  # "NOT", "-"
    operand: Expression


@dataclass
class FunctionCall(Expression):
    """Function call: COOLDOWN_READY("key", 30)"""
    function_name: str
    arguments: list[Expression]


@dataclass
class Interpolation(Expression):
    """String interpolation: "Value is {$x}"."""
    parts: list[Expression]  # Mix of Literal (string) and other expressions


# =============================================================================
# STATEMENTS - CONTROL FLOW
# =============================================================================

@dataclass
class IfStatement(Statement):
    """IF <condition> THEN ... [ELSE IF ... THEN ...] [ELSE ...] END IF"""
    condition: Expression
    then_body: list[Statement]
    else_if_clauses: list[tuple[Expression, list[Statement]]] = field(default_factory=list)
    else_body: list[Statement] = field(default_factory=list)


@dataclass
class ForEachStatement(Statement):
    """FOR EACH $item IN <collection> [WHERE <condition>] ... NEXT"""
    item_var: str
    collection: Expression  # NEEDS, AFFECTS, or array variable
    filter_condition: Optional[Expression] = None
    body: list[Statement] = field(default_factory=list)


@dataclass
class WhileStatement(Statement):
    """WHILE <condition> ... END WHILE"""
    condition: Expression
    body: list[Statement] = field(default_factory=list)


@dataclass
class ForStatement(Statement):
    """FOR $i = <start> TO <end> [STEP <step>] ... NEXT"""
    var_name: str
    start: Expression
    end: Expression
    step: Optional[Expression] = None
    body: list[Statement] = field(default_factory=list)


@dataclass
class LabelStatement(Statement):
    """:label_name"""
    label_name: str


@dataclass
class GotoStatement(Statement):
    """GOTO label_name"""
    target_label: str


@dataclass
class GosubStatement(Statement):
    """GOSUB label_name"""
    target_label: str


@dataclass
class ReturnStatement(Statement):
    """RETURN"""
    pass


@dataclass
class ExitStatement(Statement):
    """EXIT SUCCESS|FAILURE|SKIPPED ['reason']"""
    status: str  # "SUCCESS", "FAILURE", "SKIPPED"
    reason: Optional[str] = None


@dataclass
class WaitStatement(Statement):
    """WAIT <seconds>"""
    seconds: Expression


@dataclass
class ContinueStatement(Statement):
    """CONTINUE (in loops)"""
    pass


@dataclass
class BreakStatement(Statement):
    """BREAK (in loops)"""
    pass


# =============================================================================
# STATEMENTS - ACTIONS
# =============================================================================

@dataclass
class LetStatement(Statement):
    """LET $name = <expression>"""
    var_name: str
    value: Expression


@dataclass
class CareAction(Statement):
    """CARE <action_key> or CARE FOR $need"""
    action_key: Optional[str] = None
    for_need: Optional[Expression] = None


@dataclass
class TaskAction(Statement):
    """TASK <action> [param=value, ...] [AWAIT]"""
    action: str
    parameters: dict[str, Expression] = field(default_factory=dict)
    await_completion: bool = False


@dataclass
class EmitAction(Statement):
    """EMIT <event_type> [WITH <data>]"""
    event_type: str
    data: Optional[Expression] = None


@dataclass
class LogAction(Statement):
    """LOG DEBUG|INFO|OBSERVATION '<message>'"""
    level: str  # "DEBUG", "INFO", "OBSERVATION"
    message: Expression  # Usually Interpolation


@dataclass
class DeltaAction(Statement):
    """DELTA affect.curiosity +0.1, need.novelty_intake +0.2"""
    affect_deltas: dict[str, float] = field(default_factory=dict)
    need_deltas: dict[str, float] = field(default_factory=dict)


@dataclass
class ResetAction(Statement):
    """RESET ALL|AFFECTS|NEEDS|<specific_names>"""
    target: str  # "ALL", "AFFECTS", "NEEDS", or specific name


# =============================================================================
# STATEMENTS - AGENTIC
# =============================================================================

@dataclass
class AskStatement(Statement):
    """ASK '<question>' [WITH <context>] INTO $answer, $reasoning"""
    question: Expression
    context: Optional[Expression] = None
    answer_var: str = ""
    reasoning_var: Optional[str] = None


@dataclass
class ChooseStatement(Statement):
    """CHOOSE '<prompt>' FROM opt1='Label 1', opt2='Label 2' [WITH <context>] INTO $choice, $reasoning"""
    prompt: Expression
    options: dict[str, str]  # id -> label
    context: Optional[Expression] = None
    choice_var: str = ""
    reasoning_var: Optional[str] = None


@dataclass
class RateStatement(Statement):
    """RATE '<prompt>' [WITH <context>] INTO $rating, $reasoning"""
    prompt: Expression
    context: Optional[Expression] = None
    rating_var: str = ""
    reasoning_var: Optional[str] = None


@dataclass
class GenerateStatement(Statement):
    """GENERATE '<prompt>' [WITH <context>] INTO $content"""
    prompt: Expression
    context: Optional[Expression] = None
    output_var: str = ""


@dataclass
class ReflectStatement(Statement):
    """REFLECT '<prompt>' [WITH <context>] [SAVE AS JOURNAL|OBSERVATION]"""
    prompt: Expression
    context: Optional[Expression] = None
    save_as: Optional[str] = None  # "JOURNAL" or "OBSERVATION"


@dataclass
class CastStatement(Statement):
    """CAST <spell_reference> [WITH <context>]"""
    spell_ref: str  # Spell name or imported alias
    context: Optional[Expression] = None


# =============================================================================
# PHASE QUEUE
# =============================================================================

@dataclass
class QueueStatement(Statement):
    """QUEUE <action_or_template> FOR PHASE <phase> [PRIORITY <n>]"""
    action: str  # Action ID or template name
    phase: str  # "morning", "afternoon", "evening", "night"
    priority: int = 1
    parameters: dict[str, Expression] = field(default_factory=dict)


# =============================================================================
# PARALLEL EXECUTION
# =============================================================================

@dataclass
class ParallelBlock(Statement):
    """PARALLEL ... END PARALLEL [WAIT ALL|FIRST]"""
    branches: list[list[Statement]]
    wait_mode: str = "ALL"  # "ALL" or "FIRST"
