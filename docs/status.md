# Status

*Updated 2026-10-22 night by Daedalus. This is the narrative handoff: what happened, what waits on someone, what the plan can't say.*

## Night of 2026-10-22: more of the plan, built (not deployed)

Kohl said to keep going through the plan in night mode. Every merged PR had green CI and passed Momus. Every Momus note was fixed before merge. Nothing below is live until the next restart.

On restart, schema **v64 → v65** runs automatically. It adds one nullable column, `token_usage_records.heartbeat_run_id`, plus a partial index. It's additive and idempotent, and a dry run on a copy of the 19:07 backup changed nothing else.

| PR | What landed | Change on restart |
| --- | --- | --- |
| #97 | Research queue stats report `queued`; continuous mode had never run a task | Continuous mode works once someone switches it on (she boots `supervised`) |
| #98 | This page: the 19:15 deploy | None |
| #99 | API keys out of the journal. NewsAPI moved to a header; httpx request URLs no longer logged at INFO | No key-bearing URLs in `journalctl` |
| #100 | `RESEARCH_MAX_TASKS_PER_DAY` (default 15) caps automatic wiki research | At most 15 automatic tasks a day; the admin "run single" button says when the cap stops it |
| #101 | Cut prompt_composer/assembler and admin prompt-configs, session_init, and nine legacy session runners nothing called (−11.9k lines) | None for her. The admin prompt-configs routes are gone. The **chain system is live and was kept** (see below) |
| #103 | Benchmark Tiers 2–3 harness (#65): scenarios, judge, budget cap, dry run, results pages, draft criteria | None. Nothing runs it automatically |
| #104 | Heartbeat cutover (#62), behind `heartbeat` (still off) | With the lever off, behavior is unchanged apart from: the v65 column; `memory_maintenance` no longer fails a step that was never defined (its template description is shorter); dead paths removed; a shutdown hook that does nothing with the lever off |
| #106 | Remaining data paths come from `DATA_DIR` (fixes #105) | None. Every path resolves where it did before |

**Waiting on Kohl from tonight:**
1. **#102: one chat turn for all five entry points.** It's open, not merged, because it changes what she is told on three surfaces, and there's no lever.
   - **Prompt source:** POST /chat, Home Assistant and Discord stop using the active prompt chain and use the continuous-context prompt that WebSocket chat uses.
   - **Discord:** a public scope (no memories, home state or self-context in the prompt) and per-channel conversations.
   - **POST /chat:** gains an ownership check.
   - **Home Assistant:** gets a 50 s limit with a spoken fallback.
   - The PR body's "What merging means" section is the full list. Rollback means reverting it.
2. **Rotate the NewsAPI key.** It was in the journal before #99.
3. **Benchmarks:** the draft criteria (`docs/benchmarks/criteria-DRAFT.md`) and Momus's attack on them (`criteria-DRAFT-momus.md`) are yours to cut. Biggest point: as built, Tier 3 compares stateful Cass with a stateless plain model, so it can't isolate "the interior". Adding a plain-model-plus-history arm would fix that. No run has happened, and none will without `--budget-usd`.
4. **Before turning on `heartbeat`,** read #104's body. Once the lever is on:
   - spells and goal work pass the budget gate;
   - phase-queued journals and summaries obey their job levers;
   - research from spells needs the job levers;
   - the run log grows by about 400 rows a day, with no retention yet.
5. **New issues:**
   - #107: memory retrieval isn't scoped per user, and POST /chat attributes every turn to the global user. Discord tools are part of this too.
   - #108: the Thymos section is built but never placed in her continuous prompt, so her drives reach no chat prompt today.

**Corrections to the plan found tonight:**
- **The chain system is live.** #58 said the chain editor affects no live prompt. In fact POST /chat, HA, Discord and the onboarding intro build her prompt from the active chain. The roadmap now says so. It can be cut once those paths move off it, which is what #102 does.
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

Research still boots in `supervised` mode (the mode isn't persisted), so nothing runs or spends Tavily credits until the mode is changed on the admin page. #97 (merged 2026-10-22, live after the next restart) fixes the `queued`/`queued_count` bug that kept continuous mode from ever running a task. Before switching to continuous, note that nothing caps tasks per day: the budget gate counts a flat $0.10 per task, and Tavily calls aren't metered anywhere. A daily cap is in progress. The first run re-harvests red links from the wiki as it is now.

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
6. **Levers:** turning on `agent_loop` gives every session the core and memory tools, and `session_complete` ends a session. Turning on `heartbeat` moves two jobs (github_metrics, goal_refinement) onto it. Per #87's review, its budget gate is advisory until the ledger question in 5 is settled: the token-tracker sync overwrites in-process spend every 60 s.
7. **Research:** Tavily for the wiki queue is decided: it's on as of 2026-10-22 and the queue was cleared. Which session engine survives (legacy or generic)? Turn on `research_session_requests`, or cut them? There's an existing bug where `queued` should be `queued_count`, so the research job never runs a task. It's pinned as an xfail, and fixing it starts research that hasn't been running.
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
- **Not done:** the chat cutover onto the agent loop, the Heartbeat cutover, Tiers 2–3 (#65), self-context (#63, a design conversation), TUI/Godot/HA credentials (#33). Small follow-ups from review:
  - wiki research rows orphaned as `in_progress` after a restart (session rows are now failed at startup by #94; wiki rows: re-queue or fail is your call);
  - `web.search` now reports a failed Brave/Serper call as an error instead of "0 results" (dormant: neither key is set).
- **A rule slip to own:** the reviewer fact-checking this report read Cass's *live* `cass.db` read-only (schema version, research queue counts). Nothing was written, but tonight's rule was snapshots only. Future briefs will name it explicitly.
