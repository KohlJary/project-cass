"""
Tier 1 map: which smoke tests cover which lever (benchmark epic #65).

`scripts/tier1_status.py` reads this to build docs/tier1-status.md, and
`tests/test_tier1_map.py` (fast suite) fails when the map falls out of step:

- every lever in features.LEVERS must have an entry here, even if it has no
  smoke test yet (then `tests` is empty and the page flags it UNCOVERED);
- no entry may name a lever that doesn't exist;
- every test path here must exist;
- every smoke test (each top-level `test_*` function or `Test*` class in
  tests/smoke/test_*.py) must be listed under a lever or under SPINE.

So a new lever, or a new smoke test, fails CI until it is classified here.

Entries are pytest node-id prefixes relative to backend/: a file
("tests/smoke/test_x.py") or a test in it ("tests/smoke/test_x.py::test_y",
"tests/smoke/test_x.py::TestClass"). Parametrized cases match their base name.

`depth` says how much of the subsystem the listed tests exercise:

- "runs":    the subsystem's own work runs against the fake LLM (with the lever
             on, or invoked by hand the way its trigger would) and the test
             checks the result.
- "partial": some of the subsystem runs, but the part the lever starts (a loop,
             a connection, a boot path) does not. The note says which.
- "gate":    the tests only check that the lever gates the entry point; the
             subsystem's work is faked.
- "none":    no smoke test. `tests` must be empty.

Tests that only assert a subsystem stays OFF under CASS_PROFILE=test don't
count as coverage. Fast-suite unit tests don't either (Tier 1 is the smoke
batteries); notes mention them where they exist.
"""

CYCLES = "tests/smoke/test_autonomous_cycles.py"
HEARTBEAT_BOOT = "tests/smoke/test_heartbeat_boot.py"
LEVER_WIRING = "tests/smoke/test_lever_wiring.py::TestLeverWiring"

LEVER_COVERAGE = {
    # --- Synkratos scheduler and its system jobs ---
    "scheduler": {
        "depth": "partial",
        "tests": [f"{CYCLES}::test_scheduler_loop_not_started",
                  f"{HEARTBEAT_BOOT}::test_migrated_jobs_run_on_heartbeat_not_synkratos"],
        "note": "Jobs register on Synkratos at boot and run by hand; the scheduler loop itself is never started.",
    },
    "job_github_metrics": {
        "depth": "runs",
        "tests": [f"{CYCLES}::test_job_github_metrics",
                  "tests/smoke/test_heartbeat_fallback.py"],
        "note": "",
    },
    "job_idle_summarization": {
        "depth": "runs",
        "tests": [f"{CYCLES}::test_job_idle_summarization"],
        "note": "",
    },
    "job_daily_journal": {
        "depth": "runs",
        "tests": [f"{CYCLES}::test_job_daily_journal_writes_dream",
                  f"{CYCLES}::test_job_daily_journal_writes_journal",
                  "tests/smoke/test_journal_pipeline.py"],
        "note": "",
    },
    "job_goal_refinement": {
        "depth": "runs",
        "tests": [f"{CYCLES}::test_job_goal_refinement",
                  f"{HEARTBEAT_BOOT}::test_a_heartbeat_run_is_logged"],
        "note": "",
    },
    "job_autonomous_research": {
        "depth": "runs",
        "tests": [f"{CYCLES}::test_job_autonomous_research"],
        "note": "",
    },
    "research_session_requests": {
        "depth": "none",
        "tests": [],
        "note": "The autonomous_research job runs in smoke with this lever off; the request queue path is not run.",
    },

    # --- Thymos / Grimoire / goals ---
    "thymos": {
        "depth": "none",
        "tests": [],
        "note": "Smoke checks Grimoire is attached to Thymos without starting it; the tick loop never runs.",
    },
    "grimoire_timer_spells": {
        "depth": "runs",
        "tests": [f"{CYCLES}::test_timer_spells_loaded",
                  f"{CYCLES}::test_timer_spell_rss_monitor",
                  f"{CYCLES}::test_timer_spell_research_synthesis",
                  f"{CYCLES}::test_timer_spell_art_study",
                  f"{CYCLES}::test_timer_spell_goal_executor"],
        "note": "Each spell is cast once by hand (what its timer would do); the on_tick trigger is not run.",
    },
    "grimoire_need_spells": {
        "depth": "partial",
        "tests": [f"{CYCLES}::test_need_spell_social_care_outreach",
                  f"{CYCLES}::test_need_spell_novelty_care_wonderland"],
        "note": "Two of the need spells (social_care, novelty_care) are cast by hand; the threshold trigger and the other need spells are not run.",
    },
    "goal_orchestrator": {
        "depth": "partial",
        "tests": [f"{CYCLES}::test_timer_spell_goal_executor"],
        "note": "goal_executor runs against a bare orchestrator with the lever off; needs-to-goals and LLM goal planning are not run. Fast-suite: tests/test_goal_orchestrator.py.",
    },

    # --- Day phases / autonomous scheduling ---
    "autonomous_scheduling": {
        "depth": "runs",
        "tests": [CYCLES, "tests/smoke/test_agent_loop_session.py"],
        "note": "Booted on so the action registry is built; the spells and sessions dispatch through it.",
    },
    "day_phases": {
        "depth": "none",
        "tests": [],
        "note": "DayPhaseTracker / AutonomousScheduler are never started in smoke.",
    },
    "phase_email": {
        "depth": "gate",
        "tests": [f"{LEVER_WIRING}::test_phase_change_email_check_respects_lever"],
        "note": "Checks a phase change calls the email check only with the lever on; the email check is faked.",
    },

    # --- Other background loops ---
    "conversation_observation": {"depth": "none", "tests": [], "note": ""},
    "legacy_background_loops": {
        "depth": "partial",
        "tests": ["tests/smoke/test_heartbeat_fallback.py"],
        "note": "Checks the fallback starts the legacy loops (their coroutines are replaced by recorders); the loops' work is not run.",
    },
    "identity_bootstrap": {"depth": "none", "tests": [], "note": "Fast-suite: tests/test_identity_snippet_refresh.py."},
    "coherence_monitor": {"depth": "none", "tests": [], "note": ""},
    "source_refresh": {"depth": "none", "tests": [], "note": "Talks to outside services (weather/geo/GitHub); smoke blocks the network."},
    "capability_indexing": {
        "depth": "gate",
        "tests": [f"{LEVER_WIRING}::test_late_source_registration_respects_capability_indexing"],
        "note": "Checks late source registration starts indexing only with the lever on; indexing (Ollama) is faked.",
    },

    # --- Autonomous action domains ---
    "rss": {
        "depth": "runs",
        "tests": [f"{CYCLES}::test_timer_spell_rss_monitor"],
        "note": "",
    },
    "research": {
        "depth": "runs",
        "tests": [f"{CYCLES}::test_timer_spell_research_synthesis",
                  f"{CYCLES}::test_timer_spell_goal_executor"],
        "note": "",
    },
    "art_study": {
        "depth": "runs",
        "tests": [f"{CYCLES}::test_timer_spell_art_study"],
        "note": "Met Museum and Wikipedia fetches are stubbed.",
    },
    "outreach": {
        "depth": "runs",
        "tests": [f"{CYCLES}::test_need_spell_social_care_outreach"],
        "note": "Reaches outreach.draft; nothing is sent.",
    },
    "wonderland_actions": {
        "depth": "runs",
        "tests": [f"{CYCLES}::test_need_spell_novelty_care_wonderland"],
        "note": "",
    },

    # --- Integrations ---
    "discord": {
        "depth": "partial",
        "tests": ["tests/smoke/test_discord_wake_tools.py"],
        "note": "The wake callback runs against a fake bot; the Discord connection is not started.",
    },
    "home_assistant": {
        "depth": "none",
        "tests": [],
        "note": "Smoke routes and executes the HA chat tools with availability patched, but the lever's refresh loop and subscription are not run.",
    },
    "relay": {
        "depth": "partial",
        "tests": ["tests/smoke/test_chat_turn_hazards.py::test_relay_turn_persists_same_artifacts_as_websocket",
                  "tests/smoke/test_chat_turn_hazards.py::test_overlapping_turns_do_not_cross_users",
                  "tests/smoke/test_chat_event_loop.py::test_slow_retrieval_in_relay_chat_does_not_block_other_requests"],
        "note": "The relay chat handler runs; the relay client connection is not started.",
    },
    "geocass": {"depth": "none", "tests": [], "note": ""},
    "push": {
        "depth": "none",
        "tests": [],
        "note": "Smoke covers the /push/register endpoint, but send_push (what the lever gates) is not called.",
    },

    # --- Local media ---
    "tts": {"depth": "none", "tests": [], "note": "Fast-suite (marked `tts`): tests/test_tts.py, tests/test_tts_optional.py."},
    "face_id": {"depth": "none", "tests": [], "note": "CI's full job doesn't install face recognition."},
    "voice_id": {"depth": "none", "tests": [], "note": ""},

    # --- What reaches her prompt ---
    "self_context": {
        "depth": "none",
        "tests": [],
        "note": "Chat turns in smoke build the prompt with this lever off. Fast-suite: tests/test_self_context.py.",
    },

    # --- Her reaching out ---
    "reach_out": {"depth": "none", "tests": [], "note": "Fast-suite: tests/test_reach_out.py."},

    # --- One agent loop ---
    "agent_loop": {
        "depth": "runs",
        "tests": ["tests/smoke/test_agent_loop_session.py"],
        "note": "",
    },

    # --- Heartbeat ---
    "heartbeat": {
        "depth": "runs",
        "tests": [HEARTBEAT_BOOT, "tests/smoke/test_heartbeat_fallback.py"],
        "note": "",
    },

    "art_choice": {
        "depth": "none",
        "tests": [],
        "note": "generate_image_action is not run in smoke. Fast-suite: tests/test_art_choice.py.",
    },
}

# Smoke tests for the spine: what runs with every lever off (boot, chat,
# auth, routes, tools). Listed so that every smoke test is classified.
SPINE = {
    "boot": ["tests/smoke/test_app_boot.py",
             f"{LEVER_WIRING}::test_endpoint_lists_levers_and_requires_admin",
             f"{CYCLES}::test_grimoire_attached_to_thymos_without_starting_it"],
    "chat turn": ["tests/smoke/test_ws_chat_turn.py",
                  "tests/smoke/test_http_chat_paths.py",
                  "tests/smoke/test_chat_turn_hazards.py",
                  "tests/smoke/test_chat_event_loop.py"],
    "tools": ["tests/smoke/test_tool_routability.py",
              "tests/smoke/test_tool_execution.py"],
    "auth": ["tests/smoke/test_auth_unified.py",
             "tests/smoke/test_auth_ownership.py"],
    "admin and routes": ["tests/smoke/test_admin_area.py",
                         "tests/smoke/test_frontend_endpoints.py",
                         "tests/smoke/test_drift_routes.py",
                         "tests/smoke/test_authenticity_patterns_route.py",
                         "tests/smoke/test_llm_routing_admin.py",
                         "tests/smoke/test_push_quiet_hours_endpoints.py"],
    "journals": ["tests/smoke/test_journal_lock_enforced.py"],
    "memory and people": ["tests/smoke/test_narrative_thread_update.py",
                          "tests/smoke/test_peopledex_observe.py"],
    "spells": ["tests/smoke/test_spells_parse.py"],
}

DEPTHS = ("runs", "partial", "gate", "none")
