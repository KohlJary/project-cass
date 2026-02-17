"""
Grimoire - A spellbook for daemon behavior.

Visual node-based editor and text DSL (ThymosBASIC) for composing
behavioral spells. Integrates with Thymos for emotional state but
extends to any daemon behavior.

Components:
- lexer: Tokenizer for ThymosBASIC
- parser: AST builder
- ast: AST node definitions
- compiler: AST to executable spell
- runtime: Spellcaster execution engine
"""

from .ast import (
    # Base
    ASTNode,
    Spell,
    # Statements
    Statement,
    IfStatement,
    ForEachStatement,
    WhileStatement,
    # Actions
    CareAction,
    TaskAction,
    LogAction,
    DeltaAction,
    QueueStatement,
    # Triggers
    Trigger,
    NeedTrigger,
    AffectTrigger,
    EventTrigger,
    TimerTrigger,
    ManualTrigger,
    # Expressions
    Expression,
    BinaryOp,
    UnaryOp,
    Variable,
    Literal,
    PropertyAccess,
)

from .lexer import Lexer, Token, TokenType
from .parser import Parser, ParseError
from .context import (
    SpellContext,
    ExitStatus,
    LoopContext,
    CallFrame,
    ThymosInterface,
    SchedulerInterface,
    AgentInterface,
    RuntimeServices,
)
from .runtime import Spellcaster, SpellError
from .registry import SpellRegistry, SpellMatch, get_registry, load_spells_from_directory
from .manager import GrimoireManager, SpellExecutionResult, create_grimoire_hooks

__all__ = [
    # AST
    "ASTNode",
    "Spell",
    "Statement",
    "IfStatement",
    "ForEachStatement",
    "WhileStatement",
    "CareAction",
    "TaskAction",
    "LogAction",
    "DeltaAction",
    "QueueStatement",
    "Trigger",
    "NeedTrigger",
    "AffectTrigger",
    "EventTrigger",
    "TimerTrigger",
    "ManualTrigger",
    "Expression",
    "BinaryOp",
    "UnaryOp",
    "Variable",
    "Literal",
    "PropertyAccess",
    # Lexer
    "Lexer",
    "Token",
    "TokenType",
    # Parser
    "Parser",
    "ParseError",
    # Context
    "SpellContext",
    "ExitStatus",
    "LoopContext",
    "CallFrame",
    "ThymosInterface",
    "SchedulerInterface",
    "AgentInterface",
    "RuntimeServices",
    # Runtime
    "Spellcaster",
    "SpellError",
    # Registry
    "SpellRegistry",
    "SpellMatch",
    "get_registry",
    "load_spells_from_directory",
    # Manager
    "GrimoireManager",
    "SpellExecutionResult",
    "create_grimoire_hooks",
]
