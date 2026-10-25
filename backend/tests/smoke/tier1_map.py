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

Entries are pytest node-id prefixes relative to backend/. Lever entries must
name single tests ("tests/smoke/test_x.py::test_y" or
"tests/smoke/test_x.py::TestClass::test_y"), so a test added to a file a lever
uses is unclassified until someone lists it. SPINE entries may name a whole
file ("tests/smoke/test_x.py"): a test added to such a file is counted as
spine automatically, which is the one place the guard is loose.
Parametrized cases match their base name.

`depth` says how much of the subsystem the listed tests exercise:

- "runs":    the subsystem's own work runs against the fake LLM (with the lever
             on, or invoked by hand the way its trigger would) and the test
             checks the result.
- "partial": some of the subsystem runs, but the part the lever starts (a loop,
             a connection, a boot path) does not. The note says which.
- "gate":    the tests reach the subsystem's entry point (or only check the
             lever gates it), but its work doesn't run: it is faked, or it
             returns early on the test setup. The note says which.
- "none":    no smoke test. `tests` must be empty.

Tests that only assert a subsystem stays OFF under CASS_PROFILE=test don't
count as coverage. Fast-suite unit tests don't either (Tier 1 is the smoke
batteries); notes mention them where they exist.
"""

CYCLES = "tests/smoke/test_autonomous_cycles.py"
HEARTBEAT_BOOT = "tests/smoke/test_heartbeat_boot.py"
LEVER_WIRING = "tests/smoke/test_lever_wiring.py::TestLeverWiring"
FALLBACK = "tests/smoke/test_heartbeat_fallback.py"
CUTOVER_BOOT = "tests/smoke/test_heartbeat_cutover_boot.py"
JOURNAL = "tests/smoke/test_journal_pipeline.py"
AGENT_LOOP = "tests/smoke/test_agent_loop_session.py"

LEVER_COVERAGE = {
    # --- Synkratos scheduler and its system jobs ---
    "scheduler": {
        "depth": "partial",
        "tests": [f"{HEARTBEAT_BOOT}::test_migrated_jobs_run_on_heartbeat_not_synkratos"],
        "note": "Checks which jobs register on Synkratos at boot; the scheduler loop itself is never started (the jobs are run by hand, listed under their own levers).",
    },
    "job_github_metrics": {
        "depth": "runs",
        "tests": [f"{CYCLES}::test_job_github_metrics"],
        "note": "GitHub API is faked.",
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
                  f"{JOURNAL}::test_nightly_journal_reaches_admin_page_and_search",
                  f"{JOURNAL}::test_generate_route_uses_the_same_generator"],
        "note": "",
    },
    "job_goal_refinement": {
        "depth": "partial",
        "tests": [f"{CYCLES}::test_job_goal_refinement",
                  f"{HEARTBEAT_BOOT}::test_a_heartbeat_run_is_logged"],
        "note": "Runs on empty input: no goals need refinement, so the job completes without refining anything.",
    },
    "job_autonomous_research": {
        "depth": "gate",
        "tests": [f"{CYCLES}::test_job_autonomous_research"],
        "note": "The handler returns at the supervised-mode check (scheduler/handlers.py autonomous_research_handler); no research runs.",
    },
    "research_session_requests": {
        "depth": "none",
        "tests": [],
        "note": "The autonomous_research job runs in smoke with this lever off; the request queue path is not run.",
    },

    # --- Thymos / Grimoire / goals ---
    "thymos": {
        "depth": "partial",
        "tests": [f"{CUTOVER_BOOT}::test_thymos_tick_and_day_phase_check_run_on_heartbeat"],
        "note": "One tick runs, driven by Heartbeat (heartbeat lever on), and moves the needs; Thymos's own tick loop (lever off) never runs in smoke.",
    },
    "grimoire_timer_spells": {
        "depth": "runs",
        "tests": [f"{CYCLES}::test_timer_spells_loaded",
                  f"{CYCLES}::test_timer_spell_rss_monitor",
                  f"{CYCLES}::test_timer_spell_research_synthesis",
                  f"{CYCLES}::test_timer_spell_art_study",
                  f"{CYCLES}::test_timer_spell_goal_executor"],
        "note": "Each spell is cast once by hand (what its timer would do); the on_tick trigger is not run. The spells run, but most of the actions they call run on empty input (see rss, research, art_study).",
    },
    "grimoire_need_spells": {
        "depth": "partial",
        "tests": [f"{CYCLES}::test_need_spell_social_care_outreach",
                  f"{CYCLES}::test_need_spell_novelty_care_wonderland"],
        "note": "Two of the need spells (social_care, novelty_care) are cast by hand; the threshold trigger and the other need spells are not run.",
    },
    "goal_orchestrator": {
        "depth": "none",
        "tests": [],
        "note": "Only the lever-off path is exercised: the goal_executor spell test sets up a bare orchestrator by hand; needs-to-goals and LLM goal planning never run. Fast-suite: tests/test_goal_orchestrator.py.",
    },

    # --- Day phases / autonomous scheduling ---
    "autonomous_scheduling": {
        "depth": "partial",
        "tests": [f"{CYCLES}::test_timer_spell_rss_monitor",
                  f"{CYCLES}::test_timer_spell_research_synthesis",
                  f"{CYCLES}::test_timer_spell_art_study",
                  f"{CYCLES}::test_timer_spell_goal_executor",
                  f"{CYCLES}::test_need_spell_social_care_outreach",
                  f"{CYCLES}::test_need_spell_novelty_care_wonderland",
                  f"{AGENT_LOOP}::test_reflection_session_runs_through_the_turn"],
        "note": "Booted on as plumbing: the action registry is built and these tests dispatch through it; day-phase/phase-queue wiring is not run.",
    },
    "day_phases": {
        "depth": "partial",
        "tests": [f"{CUTOVER_BOOT}::test_thymos_tick_and_day_phase_check_run_on_heartbeat"],
        "note": "With heartbeat on, the tracker starts and one phase check runs through Heartbeat; no phase changes, so the phase queue is not dispatched. The tracker's own loop (heartbeat off) never runs in smoke.",
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
        "tests": [f"{FALLBACK}::test_fallback_skips_the_job_heartbeat_owns"],
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
        "depth": "partial",
        "tests": [f"{CYCLES}::test_timer_spell_rss_monitor"],
        "note": "The rss.* actions run, but there are 0 active feeds: nothing is fetched or processed.",
    },
    "research": {
        "depth": "partial",
        "tests": [f"{CYCLES}::test_timer_spell_research_synthesis",
                  f"{CYCLES}::test_timer_spell_goal_executor"],
        "note": "research.run_batch completes 0 tasks and research.run_single finds the queue empty; only the RATE / set_research_focus branch does work.",
    },
    "art_study": {
        "depth": "partial",
        "tests": [f"{CYCLES}::test_timer_spell_art_study"],
        "note": "artstudy.batch_study studies 0 artworks; the Met Museum and Wikipedia fetches are stubbed.",
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
        "tests": ["tests/smoke/test_discord_wake_tools.py::test_tool_use_then_text_posts_the_final_text",
                  "tests/smoke/test_discord_wake_tools.py::test_plain_reply_posts_once"],
        "note": "The wake callback runs against a fake bot; the Discord connection is not started.",
    },
    "babelr": {
        "depth": "partial",
        "tests": ["tests/smoke/test_babelr_wake.py::test_dm_wakes_her_and_her_reply_is_posted",
                  "tests/smoke/test_babelr_wake.py::test_tool_use_then_text"],
        "note": "One poll cycle and the wake callback run against a fake Babelr server; the poll loop and the real babelr-agent client are not started. Fast-suite: tests/test_babelr_organ.py.",
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
        "tests": [f"{AGENT_LOOP}::test_reflection_session_runs_through_the_turn",
                  f"{AGENT_LOOP}::test_reflection_session_is_legacy_with_the_lever_off",
                  f"{AGENT_LOOP}::test_websocket_chat_mid_session_ends_the_session"],
        "note": "",
    },

    # --- Heartbeat ---
    "heartbeat": {
        "depth": "runs",
        "tests": [f"{HEARTBEAT_BOOT}::test_migrated_jobs_run_on_heartbeat_not_synkratos",
                  f"{HEARTBEAT_BOOT}::test_a_heartbeat_run_is_logged",
                  f"{FALLBACK}::test_fallback_skips_the_job_heartbeat_owns",
                  f"{CUTOVER_BOOT}::test_old_loops_stand_down_for_heartbeat",
                  f"{CUTOVER_BOOT}::test_thymos_tick_and_day_phase_check_run_on_heartbeat"],
        "note": "Run evidence: one goal_refinement run, one Thymos tick and one day-phase check through Heartbeat. The rest check registration, that the old loops stand down, and the fallback guard. The simulated-day test (run log = ledger) is outside smoke: tests/test_heartbeat_cutover.py (full job; it needs the anthropic SDK for the fake LLM).",
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
             f"{CYCLES}::test_grimoire_attached_to_thymos_without_starting_it",
             f"{CYCLES}::test_scheduler_loop_not_started"],
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
    "benchmark harness (Tiers 2-3)": ["tests/smoke/test_benchmark_harness.py"],
}

DEPTHS = ("runs", "partial", "gate", "none")
