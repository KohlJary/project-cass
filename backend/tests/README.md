# Backend tests

Run everything from `backend/`.

## Two suites

| Suite | What it covers | Needs | Command |
|---|---|---|---|
| **fast** | Managers, CRUD, levers, strict mode | `requirements-test.txt` | `pytest -m "not slow and not tts"` |
| **smoke** (`tests/smoke/`) | Boots the real app and exercises the spine | `requirements.txt` (face recognition optional) | `pytest -m smoke` |

`pytest` with no arguments runs both. When the runtime deps aren't installed,
tests that import the real app (the smoke directory, `test_route_auth.py`,
`test_security_lockdown.py`) are skipped instead of erroring, so the fast CI
job still works. CI's `full` job installs the runtime deps and runs all of
them (`.github/workflows/tests.yml`).

Every test has a hard 60s timeout (`pytest-timeout`, set in `pytest.ini`). A
hang fails that one test with a stack dump instead of stalling CI. Use
`@pytest.mark.timeout(N)` for a test that legitimately needs longer.

### Authentication

The app is default-deny (`route_guard.py`): every route needs a token unless
it's on the public list, and `/ws` rejects chat from an anonymous socket. The
smoke conftest has helpers for this. Never loosen the guard to make a test pass.

- `smoke_user`: `(user_id, token)` for a real user row with a `/auth/login`-style
  access token. Use it as `client.websocket_connect(f"/ws?token={token}")` or
  `headers={"Authorization": f"Bearer {token}"}`.
- `smoke_admin`: `(user_id, token)` for an admin with an admin-dashboard token,
  which is the only kind routes that declare `require_admin` accept.
- `create_user(...)`, `access_token(user_id)` and `admin_token(user_id)` are
  plain functions for module-scoped setups.

No test may call a real LLM, the network or real hardware. In `tests/smoke/`
a network guard enforces this: any outbound connection or DNS lookup raises.

### What the smoke batteries check

- `test_app_boot.py`: `main_sdk` boots, `/health` is 200, and no background
  loop is running under `CASS_PROFILE=test`.
- `test_ws_chat_turn.py`: one full `/ws` chat turn (message in, response frame
  out, turn saved to SQLite), then a turn where the model calls a tool.
- `test_tool_routability.py`: every tool any chat client can offer the model
  reaches an executor through `route_tool`, with the right arguments.
- `test_spells_parse.py`: every `.spell` file parses.
- `test_frontend_endpoints.py`: every endpoint the four frontends call exists.
  The list comes from `scripts/extract_frontend_endpoints.py`. Re-run it and
  commit the fixture when a frontend's API calls change.
- `test_autonomous_cycles.py`: each Synkratos system job and Grimoire timer
  spell runs one cycle against the fake LLM and does its work.
- `test_agent_loop_session.py`: one `session.reflection` through the agent loop
  (lever `agent_loop`) against the fake LLM, and the legacy path with it off.
- `test_lever_wiring.py`: the `/admin/features` endpoint and lever checks
  that need the runtime deps.

## Defaults set by `tests/conftest.py`

- `CASS_PROFILE=test`: every feature lever is off (see `features.py`).
- `CASS_STRICT=1`: `strict.report_swallowed()` re-raises instead of only logging.
- `DATA_DIR` is a temp dir. Every test gets its own copy of a seeded SQLite DB
  (`test_db`, autouse).
- `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are fake values. A test that forgot
  the fake LLM fails instead of spending money.

## Fixtures

### `levers`: turn subsystems on for a test

```python
def test_rss_cycle(levers):
    with levers(rss=True, grimoire_timer_spells=True):
        ...  # inside the block these levers are on; everything else stays off
```

Overrides beat env vars and profiles, and an unknown lever name is an error.
Levers are read when a subsystem starts, so to boot the app with something on,
wrap the boot in `levers(...)` (see `module_app` in `tests/smoke/conftest.py`).

### `fake_llm`: script the model

`fake_llm` patches every LLM client production uses: the Anthropic SDK
(sync and async, `create` and `stream`), `llm_caller` (Grimoire
ASK/RATE/REFLECT) and OpenAI chat completions.

```python
def test_turn(booted_app, fake_llm):
    fake_llm.queue_text("Hello Kohl")                          # one text reply
    fake_llm.queue_tool_use("lookup_person", {"name": "Kohl"})  # a tool call
    fake_llm.queue_json({"rating": 0.9, "reasoning": "x"})      # JSON-shaped text
    ...
    call = fake_llm.calls[0]          # every request is recorded, in order
    call.system_text, call.messages, call.tool_names, call.model, call.source
    fake_llm.total_input_tokens       # token usage you scripted
```

- With an empty queue the fake answers `"OK"`. Set `fake_llm.strict = True`
  to fail on unexpected calls instead.
- `fake_llm.responder = fn(source, kwargs) -> ScriptedResponse | None` lets
  you answer by prompt content (used for Grimoire's JSON prompts).

### Other fixtures

- `fake_embeddings`: offline, deterministic stand-in for Chroma's default
  embedding model (the real one downloads about 80MB).
- `booted_app` (smoke): a `TestClient` around the fully started `main_sdk` app.
- `module_app(...)` (smoke): boots the app once per module with some levers on.

## The xfail-strict convention

Known bugs from the capability audit are written as real tests marked
`@pytest.mark.xfail(strict=True, reason="<card>: <what's broken>")`.

- While the bug exists, the test fails, so it shows as `xfailed` and the
  suite is green.
- **When you fix the bug, the test passes. `strict=True` turns that into a
  failure (XPASS(strict)), so the suite goes red until you delete the xfail.**
  This is deliberate: the known-bug lists can only shrink, and every fix
  leaves a passing regression test behind.

In table-driven batteries the marks come from a dict at the top of the file
(`KNOWN_UNROUTABLE`, `KNOWN_MISSING`, `KNOWN_BROKEN`). Delete the entry when
you fix it.

To see why each known failure fails: `pytest -m smoke --runxfail`.

## Adding a subsystem

New subsystem = new lever + smoke test. Add the lever to `features.py`,
check it where the subsystem starts, and add a test under `tests/smoke/` that
turns it on with `levers` and runs one cycle against `fake_llm`.
