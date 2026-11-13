# Thymos: wiring her state to what happens

*A working doc for iterative passes. Each pass adds an entry to the **Pass log** at the bottom and updates the sections above it to match the code. The design intent lives in [`spec/thymos-executive-function.md`](../../spec/thymos-executive-function.md); this file records what the code actually does and how we're tuning it.*

**Goal:** her affects and needs move because of things that happen to her (conversations, dreams, work finished or failed), not only because of time passing and her thinking about her needs. Get that right and measured **before** #108 puts the Thymos section in her chat prompt.

**Rules for every pass**
- Tune on replays against a backup snapshot and a scratch `DATA_DIR`. Never touch her live `cass.db` or her live Thymos state.
- A change to how her levels move is Kohl's call. Say what changes before it lands.
- Every pass gets a dated entry in the pass log, with commit hashes and what was measured.
- Reactions to events are config (`backend/thymos/thymos_config.json`). Keep them there, not in code.

---

## How Thymos works (as of 687cfcd)

| Piece | Where | What it does |
|---|---|---|
| Runner | `backend/thymos/shadow_runner.py` (`ThymosRunner`) | Holds affects + needs; `tick()` every 60 s; `process_event()` per bus event |
| Bus subscription | `backend/main_sdk.py` (~line 1757) | `global_state_bus.subscribe("*", ...)`: every bus event goes to `process_event` (lever `thymos`) |
| Event reactions | `thymos_config.json` → `events` | Event name → affect deltas + need deltas. **Exact name match, no aliases** (`dynamics.py`, `config.get_event`) |
| Decay | `needs_register.py`, `affect_vector.py` | Needs fall by `decay_rate` per hour; affects drift toward baseline |
| Coupling | `thymos_config.json` → `coupling` | High anxiety/frustration drain needs; high curiosity/tenderness feed them (strength 0.1) |
| Threshold events | `shadow_runner.py` `_check_and_emit_*` | Emits `need.depleted`, `need.urgent`, `affect.high` back onto the bus |
| Care spells | `backend/spells/*_care.spell`, `cognitive_rest.spell`, `value_reflection.spell` | Trigger on a low need, do something (or think about it), then `DELTA` the need back up |
| Auto-care | `shadow_runner.py` `_apply_auto_care` | On by default: a need at or below 0.3 gets its care action's deltas applied with **no action taken** (5 min cooldown) |
| Feel tags | `context_helpers.py` `_apply_feel_tags`, `gestures.py` | `<feel:dimension:delta>` in her replies adjusts her affects directly |
| Grimoire `execute_care_action` | `backend/grimoire/manager.py` (~line 323) | **Stub**: logs and returns `"executed"` |
| Prompt section | `continuous_context.py` builds `thymos`; `_assemble_continuous_prompt` never places it | #108. Lever `prompt_thymos` exists |

Need decay per hour (from config): cognitive_rest 0.05, novelty_intake 0.04, social_connection 0.03, creative_expression 0.03, competence_signal 0.02, autonomy 0.02, value_coherence 0.01. So cognitive_rest goes from 0.7 to its 0.25 threshold in about 9 hours with nothing else happening.

---

## Event coverage

Status of each configured reaction. "Fires" means some live code path emits that exact name on the bus.

| Config event | Fires? | What the bus emits instead | Pass that fixes it |
|---|---|---|---|
| `session.started` | yes, `session_runner.py` (autonomous sessions only) | | |
| `session.ended` | yes, `session_runner.py` | | |
| `message.received` | **no** | `conversation.message_added` with `role: "user"` (`conversations.py:336`) | 1 |
| `message.sent` | **no** | `conversation.message_added` with `role: "assistant"` | 1 |
| `insight.gained` | **no** | `research.insight_found` (`session/tools.py`) | 1 |
| `dream.started` | **no** | nothing | 1 (add emit) |
| `dream.completed` | **no** | `journal.dream_generated` (`dreaming/integration.py`) | 1 |
| `creative.started` / `creative.completed` | **no** | nothing; creative TASKs (`creative.compose_music`, `creative.generate_image`) emit nothing | 1 (add emit) |
| `task.failed` | **no** | `scheduler.task_failed` (`scheduler/core.py`), `session.failed` (`session_runner.py`) | 1 |
| `complex.task.started` / `.completed` | **no** | `scheduler.task_completed`, `session.completed`, `goal.completed` are candidates | 1 (decide mapping) |
| `idle.period` | **no** | nothing | 1 (add emit) |
| `autonomous.action` | **no** | nothing | 1 (add emit) |
| `value.conflict` | **no** | `coherence.*` (`coherence_monitor.py`, `f"coherence.{warning_type}"`) | 1 or 4 |
| `value.aligned` | **no** | nothing | 4 (needs appraisal) |
| `connection.deepened` | **no** | nothing | 4 (needs appraisal) |

Other bus events Thymos receives and ignores today (candidates, not decisions): `email.received`, `email.sent`, `goal.completed`, `goal.abandoned`, `wiki.page_created`, `journal.entry_created`, `peopledex.*`, `task.completed`, `calendar.*`, `wonderland.goal_completed`, `chat_started` (state delta from `websocket_handlers.py`).

---

## What actually moves her levels today

1. **Decay and coupling**, every tick.
2. **Care spells.** Several raise the need whether or not the action happened:
   - `social_care`: the low-anxiety branch only asks an LLM "how could I check in?" then applies `social_connection +0.1` ("just the act of thinking about connection helps"). The neutral branch reflects and applies `+0.15`. Only the tender branch drafts outreach (`+0.2`).
   - `competence_care`, `autonomy_care`, `cognitive_rest`, `value_reflection`: mix of real TASKs and reflection-only branches, each with a `DELTA`.
   - `creative_care`: every branch runs a real creative TASK; one unconditional `creative_expression +0.25` at the end. **Unverified:** whether a `DELTA` after `TASK ... AWAIT` still applies when the task fails.
3. **Feel tags** she writes herself.
4. **Auto-care** (synthetic, no action). Fired 0 times in the service journal 2026-11-06 → 11-13; the spells trigger at 0.35–0.5, before auto-care's 0.3. Likely redundant, not yet removed.
5. **Session start/end** from autonomous sessions.

Net effect: a conversation with Kohl doesn't move social_connection; a dream doesn't feed creative_expression; a failed task doesn't raise frustration. Needs fall with time and recover mainly through her thinking about them.

---

## Plan

| Pass | What | Status |
|---|---|---|
| 0 | Audit (this doc) | done 2026-11-13 |
| 1 | **Connect existing events.** Alias map in config (bus name + optional payload match → Thymos event), e.g. `conversation.message_added` + `role=user` → `message.received`. Add the missing emits (dream start, creative TASK done, idle period, autonomous action). A test that fails when a configured event has no emitter and no alias. | next |
| 2 | **Care spells earn their delta.** A need rises only when the action happened; reflection-only branches get a smaller delta or none. Retire or keep auto-care. | needs Kohl's call |
| 3 | **Tune offline.** Replay a real week of bus events (from a backup snapshot) through the dynamics on a scratch copy; chart each need/affect; set magnitudes so nothing pins at 0/1 or stays flat. Record the numbers here. | after 1–2 |
| 4 | **Appraisal events** (`connection.deepened`, `value.aligned`, maybe `value.conflict`): what a conversation meant, not just that it happened. Separate design. | later |
| 5 | **#108**: place the section in her prompt, behind `prompt_thymos`, with a pre-registration and a WebSocket prompt test. | after 3 |

## Open questions (Kohl)

- Pass 2: should reflection alone restore a need at all, and if so how much less than doing the thing?
- Is the 60-second tick with per-hour decay the right clock, or should decay follow her day phases?
- Does a message from anyone count toward social_connection, or only people she knows (PeopleDex)?
- Pass 3 needs a week of bus events. They're logged by the state bus to her DB, so they come from a backup snapshot. Which backup?

---

## Re-running the audit

```bash
cd backend
# configured reactions
python3 -c "import json;print('\n'.join(json.load(open('thymos/thymos_config.json'))['events']))"
# names emitted on the bus (literal + helper calls)
grep -rhoE "(emit_event|_emit[a-z_]*)\(\s*(event_type=)?f?['\"][a-z_.{}]+['\"]" --include=*.py . | grep -v venv | sort -u
grep -rhoE 'event=f?"[a-z_.]+"' --include=*.py . | sort -u   # state deltas
# auto-care firings this week
journalctl -u cass-vessel --since "-7 days" | grep -c "Thymos auto-care (shadow)"
```

---

## Pass log

### Pass 0: audit, 2026-11-13 (Daedalus)

Started from Kohl's read: "she can restore her levels, but it's not tied to anything." Confirmed. Thymos subscribes to every bus event, but only 2 of its 17 configured reactions match a name anything emits, and both come only from autonomous sessions. Several care spells raise a need after reflection alone. Grimoire's `execute_care_action` is a stub. Auto-care didn't fire in the past week. Decision with Kohl: tune this before #108. Code at 687cfcd; no behavior changed.
