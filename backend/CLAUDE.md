# Backend Notes

Claude Code loads the repository root `CLAUDE.md` along with this file, so project context, goals and workflow live there. This file used to be a full copy of that context; it drifted out of sync and kept old claims alive, so it now holds only backend-specific pointers.

- Entry point: `main_sdk.py`
- Module structure and patterns: `ARCHITECTURE.md`
- In-progress work and known issues: `TODO.md`
- Schema changes: update CREATE TABLE in `database/schema.py`, add a migration in `_apply_schema_updates()` in `database/migrations.py`, bump `SCHEMA_VERSION`
- Data lives under `DATA_DIR` (default `backend/data`); vector store at `DATA_DIR/chroma`
- Tests: `tests/`

## Feature Levers (`features.py`)

Every subsystem that starts on its own (Synkratos and each system job, Thymos,
Grimoire timer/need spells, goal orchestrator, day phases, phase email,
observation loop, RSS/research/art study/outreach/Wonderland actions, Discord,
Home Assistant, relay, GeoCass, push, TTS, face/voice ID, ...) has one on/off
lever in `features.py`, checked at the point where it starts.

- Defaults are current behavior. `CASS_FEATURE_<NAME>=0/1` overrides one lever.
- `CASS_PROFILE=test`: everything off (core chat still works).
  `CASS_PROFILE=quiet`: no autonomous LLM spend, no external integrations.
- Explicit `CASS_FEATURE_*` beats the profile. Old env vars
  (`AUTONOMOUS_SCHEDULING_ENABLED`, `DISCORD_ENABLED`, `RELAY_ENABLED`,
  `COHERENCE_MONITOR_ENABLED`) still work and feed their lever.
- The effective table is logged at startup and served (admin only) at
  `GET /admin/features`.

**Rule: new subsystem = new lever + smoke test.** If you add anything that
starts a loop, timer, subscription, scheduled job, autonomous LLM call or
outside connection, add a lever for it in `features.py`, check it at the start
point, and add a smoke test in `tests/smoke/` that runs one cycle against the
fake LLM. See `tests/README.md`.

`strict.report_swallowed(exc, context)` is the helper for except-blocks that
log and carry on: same behavior in production, re-raises under `CASS_STRICT=1`
(tests and CI), so silent failures fail a test.

## LLM calls (`llm_caller.py`, `llm_config.py`)

Every LLM call goes through `llm_caller` (`call_llm` / `call_llm_sync` for
text, `create_message` / `create_message_sync` for Messages-API requests,
`ollama_raw` for native Ollama tool loops). Each call names a call site
registered in `llm_config.CALL_SITES`, whose default policy is the model that
call site ran before routing. An admin override (Settings > LLM, or
`PUT /admin/llm-config/{call_site}`) wins over the default; dreams, chat and
model interviews are pinned. Usage lands in `token_usage_records` with the
call site name. `tests/test_llm_routing.py` fails on a direct client call or
an unregistered call site. Chat turns are the exception for now (each user's
model setting; see the test's exception list).
