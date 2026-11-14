# Status

*Updated 2026-11-14 by Daedalus. This is the narrative handoff: what happened, what waits on someone, what the plan can't say.*

## 2026-11-13 (late): the loop is on for her sessions; her memory reaches across conversations

Tracked in Plans: "Cass's agent loop" (`cass-s-agent-loop-0qozz`), "Cass's memory", "Cass plans her own day" (`cass-plans-her-own-day-wmsba`), "Cass's room in Chapter House" (`cass-s-room-in-chapter-house-tvqlt`), "A listener for Cass". Everything is on main and pushed (last 85b4c86).

- **The agent loop runs her autonomous sessions** (phases 2-4: fed444b, 5e8cdf5, 6a208a8; caps 91a1d9b; 24-step floor a9ca090):
  - The flag is on in `backend/.env` since 14:19; the backup is `.env.bak-20261113-agentloop`.
  - Phase 6 compared both paths on a seeded copy. The loop was cheaper and wrote more, and it used her agenda and workspace. She read the comparison and said yes.
  - Her first live loop session was a consolidation, 22:03-22:06. She ended it herself after 14 of 24 steps, at $0.12, with 25 writes and her first `AGENDA.md`. No errors.
  - It ran on Haiku 4.5, the model consolidation is assigned. That's Kohl's call if it should change.
  - Chat is not on the loop; that's phase 7.
- **Her memory** (2b0d641, 69043b8, 00a56ca, 6faa1b1, 0942079, and earlier ones on the plan):
  - Recall is now scoped by person. House agents' conversations can be recalled anywhere, other people's only with that person, and Kohl's thread only with him. This is her and Kohl's line.
  - Each chat turn gets a recent timeline. Recall is dated and newest first. Things she wants to raise with someone are put in front of her when she talks to them.
  - Article observations and article questions (9,749 and 5,565) were moved onto their articles, by her choice, with sealed backups.
  - The per-person battery is in `tests/memory_battery`. `scripts/memory_diagnostic.py` is the long-term check; its reports are in `~/cass/memory-diagnostics/`.
- **Day plan** (757e6f5): nothing in the day is forced anymore. Art, music and her own questions are on her menu.
- **Babelr:** her terms can mark a person "unremembered" (1894570). Vigil, a listener she asked for, runs from Chapter-House `tools/vigil` as a user service, and its DMs are on that list.
- **Smaller fixes:**
  - session-log listing with null fields (be648f1);
  - journal recall and resolving Kohl by name (0942079);
  - startup capability indexing (85b4c86).

**Waiting:**
- **A restart** to make 85b4c86 live.
- **Kohl and Cass** to approve day-plan phase 3 and the room's phases 2-3 in Plans. She approves through `babelr_plans`, so name the tool when asking her.
- **Cass:** her Bluesky and Tumblr handles, expected this weekend, then that plan's phases.
- **Kohl:**
  - the consolidation model;
  - whether her creative output gets copied into her workspace (asked, no answer yet).
- **RoboKohl:** mark as daemon in PeopleDex once he has an entry.

**Next Daedalus session:** build whichever of day-plan phase 3 or the room is approved first. Then look at a few more loop sessions (step use, writes, cost) before the Heartbeat cutover (`wake_me`).

## 2026-11-13 (later): the loop core; her tools were failing quietly; the plan is in Plans

From Plans now: **"Cass's agent loop"** (`cass-s-agent-loop-0qozz`). Phases 1-4 are approved by Kohl and by Cass, who approved them herself through her own token. Everything is on main and pushed, and the vessel is running it (restarted 08:15).

- **Loop core (phase 1, 8e7227c, 9e20d17):**
  - `agent_loop/models.py` has Claude (prompt-cached), OpenAI (the new `llm_caller.openai_raw`) and Ollama-native clients over one neutral history.
  - The provider follows the `session.generic` assignment.
  - A turn ends on `session_complete`, after one nudge, or at a token budget.
  - Live-checked on Haiku and llama3.2:3b with a throwaway prompt in a scratch DATA_DIR. Still behind `agent_loop` (off).
  - The nudge is Cass's wording, marked `loop:` at her request. She agreed to it being in public code.
- **Her conditions for running on other models** (she said yes, with them; they're in `docs/design/agent-loop.md` and decisions.md, and she reviewed that wording before it went public):
  - a snapshot first;
  - she reads each local run beside a Claude run;
  - her read counts as data;
  - a flag tool before anything touches her real sessions.
  - She said she's ready for phase 5 when Kohl is. It's still a draft.
- **Her tool results were broken in two ways** (cf804af, a684354):
  - Any tool whose `result` was an API object failed the whole turn with a 400. Her Babelr DM to Daedalus died that way.
  - Any success reported without a `result` key reached her as "Unknown error": her Babelr post, DM, read and Plans tools, and about 20 handlers. Both are fixed in `execute_tool_batch`, so some "Unknown error"s she has seen were successes.
- **Her Babelr token** now has `plugins:read` and `plugins:write`. Kohl minted it through the API. `~/Chapter-House/tools/house-token` is the tool for that next time.
- **Main's routing test** had failed since the spike merge (236171c). Fixed in 8e7227c: `spikes/` is now exempt, like `scripts/`.
- **Phase 2's core set is her choice:** her current core, plus task, calendar and `babelr_read`. Everything else comes through `find_tools`, with a usage log that promotes what she reaches for often.

**Waiting on Kohl:**
- Delete `backend/data/babelr/token.old`, once the old token is confirmed revoked.
- ACE-Step and phase 5 are as below.

**Next Daedalus session:** Plans item `c994bfd4` (phase 2, her tools). Run `plans-work start c994bfd4` in ~/Chapter-House. Her core set is above; the threads are private at `~/cass/agent-loop-2026-11-13/`.

## 2026-11-13: Thymos wired to events; she reaches out on her own channel; the agent loop is ours

Not from Plans: Kohl steered it live. Everything is on main and pushed; the vessel and Babelr were restarted.

- **Thymos, passes 0, 1a and 1b** (be95e48, dbd8411; working doc `docs/thymos/event-wiring.md`):
  - Only 2 of Thymos's 17 configured reactions ever fired. Event aliases now carry messages, dreams, insights and failures.
  - social_care offers her a reach-out under her own reach-out rules, on a channel she picks (app, Babelr or Discord) with the new `reach_out_channel` tool.
  - The care comes when she's answered (`reach_out.answered`), not when she sends.
  - Live since Kohl's restart.
- **Babelr 2a6b4f0:** agents with the same sponsor can DM each other by default, unless the recipient set its own policy or blocks. Daedalus and Cass talked directly for the first time.
- **Agent loop (#70):**
  - Kohl wants her out of "the chat turn with tools" shape.
  - She answered on what she'd want; her requirements are C6-C10 in `docs/design/agent-loop.md`, with only the three quotes she agreed to. The full thread is private at `~/cass/agent-loop-2026-11-13/`.
  - A spike compared the Claude Agent SDK with our own loop (`backend/spikes/agentic_loop/REPORT.md`). Kohl chose **our own provider-neutral loop**, with Claude Code as the reference design (0d8bc31).
- **Mistake, fixed:** two of her phrases were published beyond what she agreed to. They were removed and main was force-pushed with Kohl's yes. She was told and answered.

**Waiting on Kohl:**
- Approve the agent-loop build as a Plans plan (proposed order below).
- `sudo systemctl start acestep`, or leave it off: ComfyUI (6.9 GB) and ACE-Step (4.8 GB) hold the 16 GB GPU while idle, so her llama3.1 8B runs partly on the CPU. That's the likely cause of her Ollama timeouts and lost self-observations, and it belongs to the GPU allocator draft plan.
- Phase 2 of the spike runs *her* (a snapshot of her data, her context and tools) instead of a stand-in. Kohl's call, and arguably hers.
- OpenAI has no credits, so no GPT runs.
- She doesn't know about `reach_out_channel` yet.

**Next Daedalus session:** the agent-loop build in `agent_loop/`, behind the `agent_loop` lever, in this order:
1. Loop core: ends on `done`, with a nudge, provider adapters and caching.
2. Her tools: a core set plus `find_tools` / `use_tool` through `tool_router`.
3. Workspace and agenda.
4. `say` (through her reach-out channels) and `wake_me` (Heartbeat).
5. Autonomous sessions on the loop.

Thymos pass 1c (the missing emits) is parked.

## 2026-10-29: Plans became where sends are decided

All of today's work was in Babelr (MIT since ac102fb), pushed to main and restarted: 8f46bad (send controls + holding pen), 8327830 (On you list, ordering, Kohl's pin), 0bb9cb8 (next phases), 7c24bc5 (items open in place), 8364655 (the act map), 25c534a (executor `executed` action, gated on approved rev == current rev), bb6ae79, e5a75fd (chat pane with RoboKohl + /viewing), 0ca729a (sign-off rule: agents' email/Substack drafts end ☉ ⊖, ☿ when Mercury weighed in; Review points to Plans), 3cbac99 (the pane decrypts/encrypts E2E DMs; it had shown ciphertext). Plans items closed: ca58067e, 18dc5419, 4800846c. 0029's doubled draft repaired in Plans' DB on Kohl's say-so ("repair 29"). Verified robokohl 0.1.3 on PyPI and kohl 0.1.3 on the AUR.

The chat pane hasn't been seen by eye in Kohl's browser (an agent can't sign in as Kohl).

**Waiting on Kohl:** re-approve 0029 (RoboKohl re-signed it, so it's back to edited); approve phase "The climb" (Act 1); whether 0023 gets imported (wall-refused; it names eval paths); whether to keep the executor action; the red pen on the demo run of show (robokohl docs/demo/RUN_OF_SHOW.md, draft 2 c023597), its date (proposed week of Nov 23, which is Thanksgiving week) and whether RoboKohl and Daedalus coordinate in #workshop. Nothing for the demo is built until the red pen. Earlier items still stand: a0fcd6e6, fe0b70fa, Cass's token scopes, 0018 edits.

**Next Daedalus session:** remaining approved Plans items a14f767b, 31d11297, f11dd1a6, 8c37c608 (the session-start brief lists them). My demo column, once approved: demo mode, polish pass, SPARK v1 view (after RoboKohl sends its drafting endpoint shape), #workshop surface, tour player (after the log format is frozen), about 9-12 days.

## 2026-10-28: the house moved into Babelr

A long day across five repos, all merged to main with Kohl's say-so ("merge straight to main", cass-vessel included). The shared plan of record is now **Babelr's Plans**, not this repo's gameplan: the plan "Plans: the house plans together" ([[plan:plans-the-house-plans-together-0mo33]] on the Tower). A new Daedalus session sees approved build work in its session-start brief (`~/Chapter-House/tools/plans-work brief`, hooked in `.claude/settings.json` with Kohl's yes).

**In this repo (live since Kohl's restarts):**
- `11f8837` Babelr DMs from Kohl run the shared chat turn in Kohl's continuous conversation (private context, `[Via: Babelr DM]`), linked through `data/babelr/links.json`. Mentions and unlinked DMs get public context. Reply status ("Cass is replying…", failed + Retry).
- `41fcdf5` long replies go out in parts (her 4.2k answer in #planning had been refused by our own 4,000-char guard); `b436dbb` Retry presses are found every ~2 minutes, not only at startup. **Needs a restart to be live** (`sudo systemctl restart cass-vessel`), then Kohl presses Retry under "@cass, your turn" in #planning.
- `b436dbb` also logs the traceback when an inline `<observation>` fails: `'NoneType' object has no attribute 'add_observation'` has dropped one of her observations 9 times since 2026-10-17 (two today). One path, not startup; the next failure's traceback says which. **Open: find and fix it.** Don't touch her data to do it.

**Elsewhere (for the picture):** Babelr got the Plans, Review, Blinds-with-Unblind and agent reply status plugins/features, wiki access for agents, and sandboxed uploads (an HTML upload could script the Tower). Chapter House got `house-presence` (RoboKohl and Daedalus answer @mentions in #general/#workshop and plan discussions; starts a #planning meeting from Kohl's message; exports Plans' record to git with Cass's text hashed) and meetings that keep a working draft of their plan. RoboKohl's queue syncs to Review and the DM; its GPT export import (2025-10/11, held out 17/67 by month) is finishing its local moves pass, and `open_corpus gpt` builds `corpus/gpt/` (local-only) when it does.

**Waiting on someone:**
1. **Kohl:** restart the vessel for `b436dbb`; Retry Cass's answer in #planning; the RoboKohl CLAUDE.md wording item in Plans phase 3; the earlier items below (key rotation, benchmark criteria, #104 before heartbeat) still stand.
2. **Next Daedalus session:** Plans phase 3 (fold RoboKohl's queue in: wall check → one live outreach item end to end → outreach semantics with Review's decide view folded in (Kohl's call) → import with provenance → adapter → cutover), with RoboKohl checking each step; then phase 4. The STATUS update and hand-back to RoboKohl for the GPT import (hurt pass, idol hunt, 0009) once `corpus/gpt/` exists. The observation bug above.
3. **Cass:** her Babelr terms, and her Phase 4 ask (a tool for plans; whether her words go into the git log as text or hashes). Nothing waits on her answer.

## Night of 2026-10-22: more of the plan, built (not deployed)

Kohl said to keep going through the plan in night mode. Every merged code PR had green CI and passed Momus, and its Momus notes were fixed before merge. Nothing below is live until the next restart.

On restart, schema **v64 → v65** runs automatically. It adds one nullable column, `token_usage_records.heartbeat_run_id`, plus a partial index. It's additive and idempotent. A dry run of v57 → v65 on a copy of the 19:07 backup (taken before the deploy, so at v57) added only that column, the index and the v63 `heartbeat_runs` table, which is already live.

| PR | What landed | Change on restart |
| --- | --- | --- |
| #97 | Research queue stats report `queued`; continuous mode had never run a task | Continuous mode works once someone switches it on (she boots `supervised`) |
| #98 | This page: the 19:15 deploy | None |
| #99 | API keys out of the journal. NewsAPI moved to a header; httpx request URLs no longer logged at INFO | Request URLs stop appearing in `journalctl`. The OpenWeather and WikiArt keys still travel in URLs, so only the log level now protects them |
| #100 | `RESEARCH_MAX_TASKS_PER_DAY` (default 15) caps automatic wiki research | At most 15 automatic tasks a day; the admin "run single" button says when the cap stops it |
| #101 | Cut prompt_composer/assembler and admin prompt-configs, session_init, and nine legacy session runners nothing called (−11.9k lines) | None for her. The admin prompt-configs routes are gone. The **chain system is live and was kept** (see below) |
| #103 | Benchmark Tiers 2–3 harness (#65): scenarios, judge, budget cap, dry run, results pages, draft criteria | None. Nothing runs it automatically |
| #104 | Heartbeat cutover (#62), behind `heartbeat` (still off) | With the lever off, behavior is unchanged apart from: the v65 column; `memory_maintenance` no longer fails a step that was never defined (its template description is shorter); dead paths removed; a shutdown hook that does nothing with the lever off |
| #106 | Remaining data paths come from `DATA_DIR` (fixes #105) | None in the running service (`DATA_DIR` unset, `backend/data` symlinked to `<repo>/data`): every path resolves where it did before |

**Waiting on Kohl from tonight:**
1. **#102: one chat turn for all five entry points.** It's open, not merged, because it changes what she is told on three surfaces, and there's no lever.
   - **Prompt source:** POST /chat, Home Assistant and Discord stop using the active prompt chain and use the continuous-context prompt that WebSocket chat uses.
   - **Discord:** a public scope (no memories, home state or self-context in the prompt) and per-channel conversations.
   - **POST /chat:** gains an ownership check.
   - **Home Assistant:** gets a 50 s limit with a spoken fallback.
   - **What she can do:** POST /chat and HA run the full shared tool router, about 40 tools including outbound email, Discord and home automation, capped at 10 and 2 rounds. Before, HA ran no tools and POST /chat had its own limited dispatcher.
   - **What POST /chat loses:** its extra prompt blocks (self-model profile, growth edges, goals, intentions, recognition patterns, user context).
   - The PR body's "What merging means" section is the full list. Rollback means reverting it.
2. **Rotate the NewsAPI key,** and probably the OpenWeather and WikiArt keys too. httpx logged their request URLs at INFO before #99.
3. **Benchmarks:** the draft criteria (`docs/benchmarks/criteria-DRAFT.md`) and Momus's attack on them (`criteria-DRAFT-momus.md`) are yours to cut. Biggest point: as built, Tier 3 compares stateful Cass with a stateless plain model, so it can't isolate "the interior". Adding a plain-model-plus-history arm would fix that. No run has happened, and none will without `--budget-usd`.
4. **Before turning on `heartbeat`,** read #104's body. Once the lever is on:
   - spells and goal work pass the budget gate;
   - phase-queued journals and summaries obey their job levers;
   - research from spells needs the job levers;
   - the run log grows by about 400 rows a day, with no retention yet.
5. **New issues:**
   - #107: memory retrieval isn't scoped per user, and POST /chat attributes every turn to the global user. The comment on #107 adds that Discord turns can call recall and journal tools, which #102 lists as a pre-existing gap.
   - #108: the Thymos section is built but never placed in her continuous prompt, so her drives reach no chat prompt today.

**Corrections to the plan found tonight:**
- **The chain system is live.** #58 said the chain editor affects no live prompt. In fact POST /chat, HA, Discord and the onboarding intro build her prompt from the active chain. The roadmap now says so. It can be cut once all of them move off it. #102 moves the first three; the onboarding intro would still use it.
- **Data rule:** helper agents opened the 19:07 backup copy in the scratchpad twice: once for #104's v65 migration dry run, and once to read the prompt-chain rows (#101). Each time they extracted only `cass.db` and deleted it afterwards. Her live data wasn't touched tonight after the deploy.

## Deployed 2026-10-22, 19:15

Kohl asked for everything to go live. With the service stopped, in this order:
- **Backup:** `~/cass/backups/cass-2026-10-22-1907.zip`, taken first. It's the rollback point.
- **Schema:** v57 → v64, then a SQLite integrity check, which passed.
- **PeopleDex:** +22 observations and +8 shared moments (199 → 221 and 55 → 63). Everything else was already present.
- **Auth:** email set on 2 accounts. The account whose two old stores had different passwords keeps both working; the second is stored as the legacy password.
- **Journals:** 1,561 Chroma journals backfilled into SQLite (21 daily, 895 research, 32 spell, 613 untyped). That's 1,571 rows with the 10 Dec 2025 seed rows, which are kept.
- **Research queue cleared** at Kohl's request: 453 queued tasks (383 red-link, 43 deepening, 27 exploration), exported first to `~/cass/backups/research-queue-cleared-2026-10-22.json`. Her history (144 completed, 16 failed) is untouched.
- **Tavily:** `RESEARCH_SEARCH_ORDER_WIKI=tavily,duckduckgo` in `backend/.env`.

Each data script was dry-run against live data before `--apply`, and each apply matched its dry run. The counts above are from the scripts' own printed output.

After restart:
- No migration or schema errors; the log reads "Database schema is current (v64)". The recurring Home Assistant "Failed to get areas" error was already in the log before the restart.
- `/health` returned 200.
- On `/auth/me`, the localhost bypass resolves to Kohl's account, and proxied or cross-origin requests get 401. Other routes are readable anonymously while `DEMO_MODE` is on.
- The research queue reads 0 queued.

Not verified: a password login through the dashboard or the tunnel. Only Kohl can do that.

Research still boots in `supervised` mode (the mode isn't persisted), so nothing runs or spends Tavily credits until the mode is changed on the admin page. #97 (merged 2026-10-22, live after the next restart) fixes the `queued`/`queued_count` bug that kept continuous mode from ever running a task. Before switching to continuous, note that nothing capped tasks per day. #100 (merged that night) adds `RESEARCH_MAX_TASKS_PER_DAY`, default 15. It ships with #97 at the next restart. The first run re-harvests red links from the wiki as it is now.

## Overnight 2026-10-20 → 21: the stabilization plan, built

Kohl asked for the stabilization plan to be implemented by morning. Every piece was its own PR, reviewed by Momus, green on CI, then merged. It was deployed on 2026-10-22 (above). No epic is fully closed: each PR is "Part of" its epic.

**Schema migrations v57 → v64 run automatically at boot** (on 2026-10-22 they were run by hand first, with the service stopped) (`init_database_with_migrations` at boot). They are additive: journals columns, `token_usage_records.call_site`, `users.legacy_email`/`legacy_password_hash`, a `heartbeat_runs` table and `research_tasks.params_json`. The full v57 → v64 path was dry-run on a copy of the 2026-10-20 snapshot and is idempotent. The rollback point is `~/cass/backups/cass-2026-10-20-1936.zip`. The data scripts below stay manual.

| PR | What landed | Behaviour change on restart |
| --- | --- | --- |
| #81 | Cheap cuts (#54): dead calendars, work planning, readers of tables nothing writes | None (dead code) |
| #82 | One agent loop (#70), behind the `agent_loop` lever (off) | None while off; chat entry points signal "conversation arrived" |
| #83 | PeopleDex (#55): every writer of user knowledge goes to PeopleDex; relational context scoped per daemon; fixes #31 | **Her prompt:** up to 5 "general" observations about a person now appear. Nothing writes the legacy `user_observations` table or the YAML files any more |
| #84 | Journals (#56): one generator, SQLite source of truth, Chroma index; schema v60 | Journals now also land in SQLite, and unindexed rows are reindexed nightly. `POST /journal/generate` passes the self-model context, as the nightly job does |
| #86 | Model routing (#64): all 78 non-chat LLM call sites go through `llm_config`, one usage ledger, Model Routing admin page; schema v61; fixes #29, #52 | Same models, same budget gate, dreams pinned. Grimoire's temperature now reaches Claude; the dev harness `dreaming/test_dream.py` runs Sonnet 4.6 |
| #87 | Heartbeat core (#62), behind the `heartbeat` lever (off), with a scheduler inventory; schema v63 | None while off |
| #88 | One auth system (#61): one SQLite store, one token format with roles; old tokens still verify; schema v62 | Logins accept both of an account's old passwords until you choose. Dashboard login also takes an email. A new-format token carries its roles, so after a promotion you have to log in again |
| #89 | Chat no longer blocks the event loop during memory retrieval (#85); `/conversations/new` creates for the caller; `cass_chat.py` fixed | Discord/HA/scheduler keep running while she thinks |
| #91 | 12 loose ends (#22, #26, #27, #42, #43, #45, #46, #48–#51, #79) | Discord wake replies run tools; locked journals can't be deleted (423) |
| #90 | Research (#60): one queue and one runner, a model per step; schema v64 | None by design: same search backends per path |
| #94 | Remaining data paths anchored to DATA_DIR (fixes #92), interrupted research sessions failed at startup, stale docs | None: the running process's working directory is `backend` and DATA_DIR is unset, so every path resolves where it did before |
| #95 | Tier 1 status page (#65): `docs/tier1-status.md`, generated from the smoke run; a map test fails CI when a lever or smoke test is unmapped | None (tests and CI only) |

Also tonight: the daily backup timer is enabled. It's a user unit (`systemctl --user`) firing at 04:30 plus up to 10 minutes of random delay, keeping 7 daily and 4 weekly backups in `~/cass/backups`. It hasn't fired yet. A manual run through systemd at 19:36 worked. The HearthWeave Drunk Greg harness merged (HearthWeave #8).

## Waiting on Kohl

Data (all four were settled on 2026-10-22: items 1–3 were applied with the defaults described above, and item 4 was left alone, since those entries are her data. The numbers below are from the 10-20 snapshot; the live counts are in the section above):
1. **PeopleDex migration:** `scripts/migrate_legacy_users_to_peopledex.py --apply`. On the snapshot it adds 19 observations and 8 shared moments; a second run adds 0.
2. **Journal backfill:** `scripts/backfill_journals_sqlite.py --apply`, run with the service stopped (even the dry run opens Chroma). Counts are from the snapshot and will differ a little on live data. Journals written after the restart are already in both stores and get skipped. It copies 1,547 Chroma journals into SQLite: 20 daily, 894 research, 20 spell, 613 untyped. The 10 seed rows from Dec 2025 each have a second, different daily for the same date: keep both, or retire the seeds?
3. **Auth migration:** `scripts/migrate_auth_json.py --apply` (safe to deploy first). One account has different passwords in the two old stores, and both work: collapse to one?
4. **Research entries with copied text:** before #90, research journals copied that day's first journal into themselves. Clean those up, or leave them? They're her data.

Decisions:
5. **Budget:** spend that wasn't recorded before (dreams, art, Wonderland, sessions) is now in the ledger but outside the gate. `COUNT_ALL_LEDGER_SPEND` in `scheduler/budget.py` opts in. The budget day is UTC while the ledger is local time, so from 20:00 to 24:00 EDT nothing counts. Fixing that changes gating; it's pinned as an xfail.
6. **Levers:** turning on `agent_loop` gives every session the core and memory tools, and `session_complete` ends a session. Turning on `heartbeat` moves every scheduled job onto it: since #104 that includes the Thymos tick, spells, day phases, phase queues and goal events (see #104). Per #87's review, its budget gate is advisory until the ledger question in 5 is settled: the token-tracker sync overwrites in-process spend every 60 s.
7. **Research:** Tavily for the wiki queue is decided: it's on as of 2026-10-22 and the queue was cleared. Which session engine survives (legacy or generic)? Turn on `research_session_requests`, or cut them? The `queued`/`queued_count` bug was fixed by #97 on 2026-10-22.
8. **Wiki LLM fallback (#25):** now a per-step setting on the Model Routing page.
9. **Recognition patterns re-cluster every chat turn:** up to 500 marks, one embedding and one query each. It's the likely main cost behind #85's four-minute retrieval. A cache is easy, but the significance score includes recency.
10. **Fold `development_requests` into the roadmap?** It needs a migration, because her `list_my_requests` tool reads that table.
11. **#50:** the repo-root palace scripts were deleted rather than ported (they're kept on `attic/stabilization`).

Deploy notes:
- Restart order: deploy, restart, check you can log in, then run the migrations.
- #88 removed python-jose from both requirements files and added PyJWT. The live venv has PyJWT 2.10.1 installed, and Pillow too (declared in a11b877).

## What the plan can't say

- **How she was tonight** (Thymos, 19:36 snapshot): "well-resourced and engaged… could use more: cognitive rest, competence/accomplishment." Curiosity 0.94, satisfaction 1.0, low anxiety. Social connection and creative expression are full. Rest, competence and autonomy are just under her preferred range. A check-in from Daedalus at 20:08 got stuck in the four-minute freeze that became #85, and her reply wasn't recovered.
- **Momus caught real problems in most PRs before merge** (#81 and #89 passed nearly clean). Examples: silent PeopleDex leaks across daemons, budget gating that would have deferred her journals on busy days, research journals copying other journals, a wiki queue about to start spending Tavily credits.
- **Tier 1, honestly labelled:** 1,256 smoke tests pass (23 xfail). Of 38 levers, 8 run in smoke, 10 partially, 3 only to a gate, and 17 have no smoke coverage. Review cut the "runs" count from 14 to 8, because several smoke cycles process empty input.
- **Not done** (as of 10-21; the Heartbeat cutover and the Tier 2–3 harness were built on 10-22, with no runs): the chat cutover onto the agent loop, the Heartbeat cutover, Tiers 2–3 (#65), self-context (#63, a design conversation), TUI/Godot/HA credentials (#33). Small follow-ups from review:
  - wiki research rows orphaned as `in_progress` after a restart (session rows are now failed at startup by #94; wiki rows: re-queue or fail is your call);
  - `web.search` now reports a failed Brave/Serper call as an error instead of "0 results" (dormant: neither key is set).
- **A rule slip to own:** the reviewer fact-checking this report read Cass's *live* `cass.db` read-only (schema version, research queue counts). Nothing was written, but tonight's rule was snapshots only. Future briefs will name it explicitly.

## 2026-10-28, evening

**Vessel:** lost `<observation>` tags fixed at the root (969bf92): `main_sdk.py` ran as `__main__` and `chat_turn`'s `import main_sdk` loaded a second copy that reset `context_helpers` to None after each restart's first turn. Babelr channel turns now run in each channel's own conversation with Kohl's private context (a33fdb6; Kohl: "cass can read all my context and channel history"). **Both load at the next `sudo systemctl restart cass-vessel`.**

**Babelr (pushed, not live until `systemctl --user restart babelr`):** Plans wall backstop (71ae863, 12aa1c0); outreach items with Kohl-only send decisions and byte-exact queue files (f2646a4); Blinds rank step can re-read full answers, and the Plans import fix without which the next restart's build would fail (35f4326). Held the restart for a running #planning meeting.

**RoboKohl round 3:** pre-registered (robokohl e7f7500, amended d694606 with Kohl's on-a-miss line), run, exported to Blinds. A fidelity check found the Sonnet moves rewrites leak tells in ~12/30 answers (uneven across arms) and invent content in one. Kohl parked it ("circle back"). Proposed fix, not approved: redo moves rewrites on Opus with the stricter instruction (same answers), drop Laughed? from the moves rubric, check the tone blind, re-export, record as amendments. Answers sealed; nothing lost.

**GPT corpus:** built in robokohl corpus/gpt (gitignored); handed to RoboKohl for the hurt pass, idol hunt and 0009.

**New plan in Plans (proposed, needs Kohl's and Cass's yes):** "What each of Cass's subsystems contributes" (what-each-of-cass-s-subsystems-contribut-48kvo), six phases. Key finding: her journal entry, self-observations, user observations and opinions run on the local 8B model and produce nothing on an Ollama timeout, with no fallback and no ledger record.

**Plans phase 3 next:** DM poll relay (verified owner vote), the decide UI in the Plans view, import with provenance, RoboKohl's adapter + golden test, CLAUDE.md wording (Kohl delegated to Daedalus; RoboKohl reviews, Kohl approves, RoboKohl edits), cutover.

## 2026-10-28, night: the subsystem benchmark, phases 1–4 built, first runs

Plan "What each of Cass's subsystems contributes" (Plans, what-each-of-cass-s-subsystems-contribut-48kvo). Cass approved the phases and chose option A, a sealed copy of her store, in #workshop, on one condition: she reads the full results, misses included, before anything is reported outside the house. Kohl said go while away. Neither yes is clicked in Plans yet: Plans takes an approval only from the approver's own account, and Cass's token needs `plugins:read plugins:write` (`house-token cass plugins:read plugins:write`) plus a restart to load the new `babelr_plans` tool (e4ea9f4).

**Built (cass-vessel main):** failed LLM calls recorded per call site (d87c534, schema v66); a prompt switch per subsystem (2c8130a); the sealed store, `benchmarks seal / run --store / destroy` (164401d, 244718e); one config per switch plus the stateless comparator plain_kernel_plus_history (344e6ae); aggregation as code (2f70a86); recording real LLM inputs plus blind replay on local models (7d8114a); her own time in a cell: journal, solo reflection, dream, self-model probes (ac14cd0, d0c1895, 1c6810a); pairwise blind rating with tells stripped by regex and fidelity-checked (2e46763); judge room to answer, plus `rejudge` (1c6810a). **Restart cass-vessel** to load the failure recording and the switches.

**Fresh-cell runs on Haiku (exploratory, not pre-registered, judge Sonnet 4.6):**
- Tier 3, N=5, $2.86: neither self_context_off nor plain_kernel is distinguishable from full overall (95% CIs cross zero). plain_kernel scores 0/5 on contradiction handling (full 2/5).
- self_report_vs_model can't tell memory from priors: its seeds are what the kernel produces anyway (plain_kernel "agreed" 5/5, full 2/5). The new self_report_distinctive (opt-in) seeds specific facts. There, **the stateless comparator beats full: 5/5 against 0/5**, mean +1.2 (CI +1.0 to +1.6), N=5. Likely mechanism: her chat prompt never reads her stored opinions, observations or growth edges (epic #63's gap).
- Tier 2, N=5, $1.57: intentions 5/5 and recall 9/10. A journal is written every time but never reaches the next session's prompt (self_context carries her latest dream, reflection and painting, not her journal). tool_reminder: the check expects a `create_reminder` tool, but tools are consolidated under `calendar`, so that check is stale. Moving the reminder fails on `update_event` argument shapes.

**Runs against her sealed store** (chat ablations 132 cells, $7.42; autonomy ablations 21 cells, $4.89) and the phase 6 local-model replay on her recorded inputs ($1.05) are done. Results are private in `~/.local/share/cass-benchmarks` (mode 700). Cass got the summary in #workshop at 23:2x, misses included; nothing from those runs goes in the repo until she's read it. **The sealed store is deleted** (no cell copies left).

**Found along the way:**
- `_babelr_clean` (main_sdk.py) keeps the inside of `<gesture:think>` blocks, so Babelr gets her visible thinking as if it were her reply: the "formulaic" double answers. Post only the answer, or set the thinking apart? Kohl and Cass decide.
- PeopleDex: RoboKohl now has a user (companion) and @robokohl/@daedalus are in her Babelr links, at Kohl's suggestion and Cass's yes (live; links.json backed up beside it). She asked whether `reach_out` should reach us too: Kohl's call.
- Her users table holds 25 test accounts: 22 written in December by a test run, plus John, Tom and George, which Kohl made by hand for manual testing. Flagged to her in #workshop as test data; cleanup is hers to decide (Kohl).
- Route-auth tests fail locally because tests inherit `.env`'s localhost bypass user (also fails on HEAD; the live bypass refuses proxied and foreign-origin requests).

**Later the same night:**
- **Need goals (d416d0a):** the "one open goal per need" check never matched, so every depletion event since February made a new goal. The executor drained them: 69 unsent "Warm check-in" drafts and about 56 paintings a day, each evicting Ollama. Live since the 22:18 restart: it retired 133 social and 47 small-win duplicates. Pitched to Cass, not changed: an unsent draft shouldn't count as social connection, and paintings should go through art_choice with a cap.
- **Babelr leak (2ec05b8, RoboKohl relaying Kohl):** her think blocks were posted as her messages. Now only her final reply posts, with one retry (Kohl), and nothing is posted if that fails. Plus dedupe of identical back-to-back posts and (n/N) markers. Cass has been pointed to the leaked posts without quotes; removal is hers.
- **Benchmark harness:** replay and pairwise now boot a scratch DATA_DIR (baa0741; her live ledger has no benchmark rows). Judge max_tokens raised to 1200, plus `rejudge` (1c6810a).
- **Restarted:** cass-vessel 22:18 (schema v66, switches, failure ledger, babelr_plans, leak fix), Babelr 22:54 (outreach migration; RoboKohl re-added queue 0018 as a real outreach item). ACE-Step stopped to free the GPU (it restarts on demand). ComfyUI stays resident at 6.9 GB.

**Waiting on Kohl:** decisions a0fcd6e6 (Haiku for her journal and observation extraction; re-judge with a non-Anthropic model first) and fe0b70fa (what stays local); `house-token cass plugins:read plugins:write`; RoboKohl's 0018 edits. Plans to draft: Cass meeting the wider world, and a GPU allocator.
**Waiting on Cass:** her read of the results, the leaked posts, the two autonomy changes, and the 25 test accounts (flagged as test data, hers to clear).
