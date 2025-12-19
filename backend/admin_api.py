"""
Cass Vessel - Admin API Router

This module is now a thin wrapper that re-exports from the modular
routes/admin/ package. All endpoints have been organized into domain-specific
files for better maintainability:

  - routes/admin/auth.py       - Authentication, login, register, user approval
  - routes/admin/daemons.py    - Daemon CRUD, export/import
  - routes/admin/genesis.py    - Genesis dream sessions
  - routes/admin/memory.py     - Memory, journals, conversations
  - routes/admin/self_model.py - Self-model, identity snippets
  - routes/admin/stats.py      - System stats, GitHub metrics, token usage
  - routes/admin/sessions.py   - All session types (research, synthesis, etc.)
  - routes/admin/homepage.py   - Homepage and GeoCass sync

For backward compatibility, this module re-exports all public interfaces.
"""
from fastapi import APIRouter

# Import the combined router and all exports from the admin package
from routes.admin import (
    # The combined router
    router as _admin_router,

    # Auth functions
    create_token,
    verify_token,
    require_admin,
    require_auth,
    JWT_SECRET,
    JWT_ALGORITHM,

    # Manager references (for backward compatibility)
    memory,
    conversations,
    users,
    self_manager,
    token_usage_tracker,

    # Init functions
    init_managers,
    init_github_metrics,
    init_token_tracker,
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
)

# Create the router with prefix
router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(_admin_router)

# Re-export everything for backward compatibility
__all__ = [
    "router",
    "create_token",
    "verify_token",
    "require_admin",
    "require_auth",
    "JWT_SECRET",
    "JWT_ALGORITHM",
    "memory",
    "conversations",
    "users",
    "self_manager",
    "token_usage_tracker",
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
]
