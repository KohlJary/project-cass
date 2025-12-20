"""
Admin API - Router Composition
Combines all admin sub-routers and provides initialization functions.
"""
from fastapi import APIRouter

# Import all sub-routers
from .auth import (
    router as auth_router,
    init_users as _init_auth_users,
    create_token,
    verify_token,
    require_admin,
    require_auth,
    JWT_SECRET,
    JWT_ALGORITHM,
)
from .daemons import router as daemons_router
from .genesis import router as genesis_router
from .memory import (
    router as memory_router,
    init_managers as _init_memory_managers,
)
from .self_model import router as self_model_router
from .stats import (
    router as stats_router,
    init_managers as _init_stats_managers,
    init_github_metrics as _init_stats_github_metrics,
    init_token_tracker as _init_stats_token_tracker,
)
from .sessions import (
    router as sessions_router,
    init_research_session_manager,
    init_research_scheduler,
    init_daily_rhythm_manager,
    init_research_manager,
    init_goal_manager,
    init_session_runners,
    init_synthesis_runner,
    init_meta_reflection_runner,
    init_consolidation_runner,
    init_growth_edge_runner,
    init_writing_runner,
    init_knowledge_building_runner,
    init_curiosity_runner,
    init_world_state_runner,
    init_creative_runner,
    init_user_model_synthesis_runner,
    init_reflection_runner,
)
from .homepage import router as homepage_router
from .narrative import (
    router as narrative_router,
    init_managers as _init_narrative_managers,
)
from .state import router as state_router
from .goals import (
    router as goals_router,
    init_goal_manager as _init_goal_manager,
)
from .scheduler import (
    router as scheduler_router,
    set_scheduler as _set_scheduler,
    get_scheduler,
)

# Create combined router
router = APIRouter()

# Include all sub-routers
router.include_router(auth_router)
router.include_router(daemons_router)
router.include_router(genesis_router)
router.include_router(memory_router)
router.include_router(self_model_router)
router.include_router(stats_router)
router.include_router(sessions_router)
router.include_router(homepage_router)
router.include_router(narrative_router)
router.include_router(state_router)
router.include_router(goals_router)
router.include_router(scheduler_router)


# Module-level references for backward compatibility
memory = None
conversations = None
users = None
self_manager = None


def init_managers(mem, conv, usr, self_mgr):
    """Initialize managers from main app - propagates to all sub-routers."""
    global memory, conversations, users, self_manager
    memory = mem
    conversations = conv
    users = usr
    self_manager = self_mgr

    # Initialize auth module
    _init_auth_users(usr)

    # Initialize memory routes
    _init_memory_managers(mem, conv, usr)

    # Initialize stats routes
    _init_stats_managers(mem, usr)


def init_github_metrics(manager):
    """Initialize GitHub metrics manager."""
    _init_stats_github_metrics(manager)


def init_token_tracker(tracker):
    """Initialize token usage tracker."""
    global token_usage_tracker
    token_usage_tracker = tracker
    _init_stats_token_tracker(tracker)


def init_narrative_managers(thread_manager, question_manager, memory=None, conversations=None, token_tracker=None):
    """Initialize narrative coherence managers (threads/questions)."""
    _init_narrative_managers(thread_manager, question_manager, memory, conversations, token_tracker)


def init_unified_goal_manager(manager=None):
    """Initialize unified goal manager."""
    _init_goal_manager(manager)


def init_scheduler(scheduler):
    """Initialize Synkratos for admin API access."""
    _set_scheduler(scheduler)


# Module-level reference for token tracker (used by other modules)
token_usage_tracker = None


# Re-export all public interfaces
__all__ = [
    # Router
    "router",

    # Auth functions
    "create_token",
    "verify_token",
    "require_admin",
    "require_auth",
    "JWT_SECRET",
    "JWT_ALGORITHM",

    # Manager references (for backward compatibility)
    "memory",
    "conversations",
    "users",
    "self_manager",
    "token_usage_tracker",

    # Init functions
    "init_managers",
    "init_github_metrics",
    "init_token_tracker",
    "init_research_session_manager",
    "init_research_scheduler",
    "init_daily_rhythm_manager",
    "init_research_manager",
    "init_goal_manager",
    "init_session_runners",
    "init_synthesis_runner",
    "init_meta_reflection_runner",
    "init_consolidation_runner",
    "init_growth_edge_runner",
    "init_writing_runner",
    "init_knowledge_building_runner",
    "init_curiosity_runner",
    "init_world_state_runner",
    "init_creative_runner",
    "init_user_model_synthesis_runner",
    "init_reflection_runner",
    "init_narrative_managers",
    "init_unified_goal_manager",
    "init_scheduler",
    "get_scheduler",
]
