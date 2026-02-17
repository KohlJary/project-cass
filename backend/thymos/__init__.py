"""
Thymos - Homeostatic Emotional/Motivational System

θυμός (thymos) - the spirited part of the soul, seat of emotions
and the source of action.

This module provides:
- Affect Vector: Continuous emotional dimensions (0.0-1.0)
- Needs Register: Functional needs with thresholds, decay, and preferred ranges
- Felt State Summarizer: Natural language integration of current state
- Goal Generator: Self-directed goals arising from need imbalances
- Shadow Runner: Event processing loop (observation mode - logs but doesn't drive)

IMPORTANT: Thymos runs in SHADOW MODE. It computes what it *would* suggest
without driving behavior, until validated as humane.

Usage:
    from thymos import ThymosShadowRunner

    runner = ThymosShadowRunner(daemon_id="cass")
    await runner.start()

    # Process events from State Bus
    await runner.process_event("message.received", {"user_id": "..."})

    # Get current state for admin visibility
    state = runner.get_current_state()

    await runner.stop()
"""

from .models import (
    # Affect
    AffectDimension,
    AffectState,
    AffectDelta,
    AFFECT_DEFAULTS,
    # Needs
    NeedType,
    Need,
    NeedsState,
    NeedDelta,
    NEED_DEFAULTS,
    create_default_need,
    # Goals
    SuggestedGoal,
    # Felt State
    FeltState,
)

from .affect_vector import AffectVector
from .needs_register import NeedsRegister
from .dynamics import AffectNeedDynamics, get_event_mappings
from .felt_state import FeltStateSummarizer
from .goal_generator import GoalGenerator, get_need_action_map
from .shadow_runner import (
    ThymosShadowRunner,
    # Safety controls
    THYMOS_ENABLED,
    thymos_kill_switch,
    is_thymos_enabled,
)

# Persistence functions
from . import persistence

# Configuration
from .config import get_config, reload_config, ThymosConfig

__all__ = [
    # Models
    "AffectDimension",
    "AffectState",
    "AffectDelta",
    "AFFECT_DEFAULTS",
    "NeedType",
    "Need",
    "NeedsState",
    "NeedDelta",
    "NEED_DEFAULTS",
    "create_default_need",
    "SuggestedGoal",
    "FeltState",
    # Components
    "AffectVector",
    "NeedsRegister",
    "AffectNeedDynamics",
    "get_event_mappings",
    "FeltStateSummarizer",
    "GoalGenerator",
    "get_need_action_map",
    # Main runner
    "ThymosShadowRunner",
    # Safety controls
    "THYMOS_ENABLED",
    "thymos_kill_switch",
    "is_thymos_enabled",
    # Persistence
    "persistence",
    # Configuration
    "get_config",
    "reload_config",
    "ThymosConfig",
]
