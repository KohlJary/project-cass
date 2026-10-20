# Trial: PR #74 (5d5a8b2) chore/attic-dead-code

CLAIM (plainly): Ten modules/classes with no live caller were removed, plus legacy_client plumbing and two no-op routes, with no change to live paths.
FALSIFIER: any import/route/registry/string reference to a removed name that is reachable at runtime; boot failure; failing test.
EVIDENCE RUN (read-only, temp DATA_DIR, CASS_PROFILE=test):
- `import main_sdk` OK; hasattr(main_sdk,'legacy_client') False; routes include /chat and /conversations/*, no /conversation/clear|history.
- startup.init_llm_clients(...,True) -> CassAgentClient; (...,False) -> RuntimeError (as designed).
- Full backend suite: 2726 passed, 22 skipped, 23 xfailed (matches report).
- Repo-wide grep (excl. node_modules/venv/coverage.json) for chat_context|title_generator|goal_context module|tool_capabilities|timer_manager|handlers.timers|claude_client|websocket.manager|CassStreamingClient|legacy_client: only comments/docs and unrelated identifiers (goal_context as a tool param/local var).
- Only importlib use (scheduler/actions/__init__.py:235) resolves scheduler.actions.*; unaffected.
- set_timer/cancel_timer/list_timers/pause_timer/resume_timer: zero hits outside deleted files and unrelated Textual set_timer in tui-frontend. execute_timer_tool/TIMER_TOOLS/get_timer_manager had no importers at 5d5a8b2^.
- /conversation/clear, /conversation/history: zero hits in admin/tui/mobile/godot frontends, scripts, cass_chat.py, discord, relay, docs.
VERDICT: shown for the stated cuts; shown for legacy_client removal; findings below are low severity.
