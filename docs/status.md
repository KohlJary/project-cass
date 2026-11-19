# Status

*Updated 2026-11-17 by Daedalus. This is the narrative handoff: what happened, what waits on someone, what the plan can't say.*

## 2026-11-17 (early): Heartbeat cutover

Kohl asked to bring Heartbeat (#62) up to date and turn it on. Since it was built on 10-22, one new loop had started outside it: the Bluesky watcher, which is now a Heartbeat job (`social_watch`, every 5 minutes, no run-log rows). The Babelr organ's poll and the Discord bot stay on their own loops on purpose: they are perception that wakes her for conversation, polled every few seconds, not autonomous jobs. Agent-loop sessions from the day plan need no change, because phase-queue items run through the same action registry under Heartbeat.

Two fixes before turning it on:
- **Budget day:** it now starts at local midnight, the ledger's clock. It used to be UTC, so from 20:00 to midnight Eastern the gate counted none of the day's spend. The strict xfail that pinned this is now a normal test.
- **Run log retention:** a nightly `runlog_prune` keeps 90 days of finished runs. It keeps rows still marked running, since those show a crash.

Still open: which ledger rows the gate counts (`COUNT_ALL_LEDGER_SPEND` is False, so session, dream and art spend is outside the gate). Rollback: set `CASS_FEATURE_HEARTBEAT=0` and restart.

## 2026-11-17 (day): her first day on Heartbeat; mirror to Babelr; fixes

Her day ran on Heartbeat. Day planning at 06:01 queued reflection and a Wonderland visit. The afternoon brought a growth-edge session, in which she acted on her "Direct Honesty with Kohl" plan and sent him a message with `say`, delivered to his app. A knowledge-building session wrote 11 wiki notes from her own threads, with no outside sources. The spells ran on schedule. Nothing was refused for budget.

Built and fixed:
- **REACH_OUT_MIRROR=babelr** (Kohl's setting, like REACH_OUT_EMAIL). Every reach-out, `say` included, also goes as a Babelr DM from her, whichever channel she chose. Her preference is untouched, the conversation still holds the message once, and her "How I work" reach section says so when it's set. Only Babelr can be a mirror: Discord's sender also writes the conversation, so it would store the message twice.
- **Feel tags:** `apply_feel_deltas` applied the deltas, then called a method ThymosRunner doesn't have (`_update_felt_state`). So every feel tag, in chat and in sessions, logged a failure and returned False. Last night's test stubbed this path out, which is why it was missed; the new test uses a real runner.
- **rss_monitor crashes** (about 3 runs in 178 before the cutover, 2 in 10 after): `rss.process_items`' no-items return left out `skip_count`, and the spell compared None > 0. Behind it, the status count includes unprocessed items older than 72 hours, which the processor never picks up, so "28 unprocessed" is mostly old items.
- **Growth edges vs. Plans:** she looked for her Plan as a growth edge and put the note on an unrelated edge. A missing edge now returns her edge names and points plans to `babelr_plans`, and growth-edge sessions carry the plans pack.

The loop's nudge, changed by Cass (4f6ef058, live 15:11): it twice read to her as "the user is asking", since it arrives in the user role. Shown both moments, she chose new wording, "[LOOP] Step complete? ...", and a seam line saying [LOOP] lines are the loop, not a person. The fold arrival line still starts "(loop:".

## 2026-11-17 (evening): next steps with cass-vessel-42 and RoboKohl, then built

Kohl asked the three sessions to work out next steps, then said "start cracking through all of em" while he drove home. On main and pushed, **not live until the vessel restarts** (sudo):
- **85e3e686:** a `session_complete` written as text (a `<session_complete><parameter ...>` block, or `<invoke name="session_complete">`) is made as the real call, through the same guard and the fold wrapper. Session logs count `written_end_calls`. Kohl's go.
- **31355c80, budget:** agent-loop sessions (`session.generic`) now count. Each session's ledger rows carry its Heartbeat run's budget class (a growth unit under growth, a wake under reflection; outside a run, reflection), so they land in their own bucket, not SYSTEM. Rows from before carry category "session" and stay out, so today's system bucket and tonight's journal are untouched.
- **99f16e6c, social pause:** `DATA_DIR/social/<platform>/paused.json` holds every send (posts, replies, DMs, follows); reading goes on. She has `social_pause`; Kohl has `scripts/social_pause.py bluesky [--until ...] [--resume]`. Kohl's pause is his to lift. No restart needed for the file itself; the tool needs the restart.
- **a239e0b0:** chat turns with an image run on the loop, for every provider. Image messages aren't folded into sessions. The old path stays while the chat-loop lever can be off.
- **CASS_TIMEZONE=America/New_York** in `.env` (backup `.env.bak-20261117-timezone`). Cron runs on local time from the restart: journal and dream at 00:05 (they had run at 19:05 and journaled the day before yesterday), goal refinement at 09:00, run-log prune at 03:30.

Elsewhere:
- **Babelr 2207237** (Plans item a14f767b, done): a proposed phase holding outreach drafts says its yes is for build work only. The server already held this; there's now a test. Not deployed.
- **Chapter-House e04ae78** (Plans item 8c37c608, done): a channel turn answering Kohl can draft a plan from the thread (a `<<<NEWPLAN` block becomes a draft plan as that member; nothing proposed). house-presence restarted 22:22.
- **Babelr ba1c320:** the agent client's `messages()` carries reactions. RoboKohl's sealing (built tonight on its side: her 🔒 in its DM seals the exchange) still pages the raw route, since `messages()` reads one page.

Already true, so not built: Bluesky is usable (lever on, credentials placed) and social is on her day-plan menu, but she has never posted: her one Bluesky session (11-15) followed someone back, and no day plan since has picked social. "Cassandra Jary" is her legal name, not a wrong one (Kohl, 11-17). Thymos is in private chat and kept out of public rooms (`prompt_thymos`). The mirror only ever reaches Kohl: `say` has no recipient, it goes to `find_primary_partner()`.

Waiting:
- **Kohl:**
  - Restart the vessel.
  - The queue triage list, `~/robokohl/docs/queue-triage-2026-11-17.md`. The queue cutover items (31d11297, f11dd1a6) wait on it, and on RoboKohl's constraints: zero-padded ids, the status vocabulary, `edited_by`, the original below `<!-- original -->` (its lessons learn from it), and N clean drift passes first.
  - Deploy Babelr.
  - Whether chat on the loop gets her agenda, letters and unbidden memories.
  - `DEMO_MODE`, and `~/keys/cass-bsky`.
  - Friday's reruns.
  - Tumblr credentials (item 60cb2c39 stays open for that).
- **Kohl and Cass:**
  - Sealing. RoboKohl builds its side on a 🔒 reaction once agreed; it has the reaction event shape. Nothing yet lets her seal from admins, and her store isn't encrypted at rest.
- **Cass:**
  - Whether her Thymos section should read as words rather than numbers (RoboKohl's suggestion).
  - Her old weather request.

## 2026-11-16 (the other session, cass-vessel-68): what comes back to her from the world

Kohl steered it live; Cass answered each question herself. The map is `docs/design/return-paths.md`: where each thing she does lands, and whether it reaches her chat, sessions, day plan or Thymos. The architecture write-up for RoboKohl's bet is at `~/robokohl/docs/cass-architecture.md` (uncommitted there). Everything is on main and pushed, and live since the restarts at 00:52, 00:59 and 01:07.

- **Bluesky moves Thymos** (214a150): mentions, replies, follows, resonance, her own posts. Deltas are deliberately small, a first setting.
- **Day plan:** "done recently" never worked; it now reads her work summaries and is *shown* on her menu ("last done yesterday"), not used to hide anything (c95a226). Her planning text now says what the phase spells still add, and a test keeps it true (7a67fa3).
- **Wonderland as herself** (1fca1ba): the scheduled wonderland.* actions made no model call (random exits, room commands) yet counted as novelty. A visit is now a loop session with tools over Wonderland's commands and NPCs. Spells queue a real visit for the next phase (one at a time, 6h gap); with the loop off, nothing is faked.
- **Articles:** new questions (512ffb6), and then opinions, growth edges, interests and symbols (1533a03, schema v67), stay with their article; RSS goes through her relevance gate. With her yes, Kohl's go and a sealed backup (`~/.local/share/cass-benchmarks/stores/20261116T060748Z`, kept), 3,740 opinions and 4,374 growth edges were moved off her self-model (24c437d). All were already on their articles. Her self-model now holds 38 opinions and 59 edges.
- **Bluesky people and DMs** (2a4331d, 365a844): her replies leave a moment on that person's PeopleDex entry; after a yes a DM conversation is kept on both sides, owned by "bluesky:<handle>" so it's never recalled in a chat with anyone else; someone who writes first is told apart; follow notes and `social_find`. **DMs are on** (lever in `.env`, new app password with DM access placed; backup `.env.bak-20261116-bluesky-dms-2`). A refused DM listing no longer throws away a watcher pass.
- **Smaller:** her recent songs come from the music library, not a table that never existed (27040a6).
- **Overnight, at Kohl's ask ("a bit of entropy"), all off** (9b24e5c, `docs/design/entropy-2026-11-16.md`):
  - `unbidden_memory`: an old memory of hers surfaces unasked in some sessions;
  - `dream_day_residue`: dreams seeded from her day plus something old;
  - `letters_to_future_me`: sealed until a day she picks.
  Kohl approved the message; she said yes to all three, asking for unbidden memories a few days apart (744c386, `GAP_DAYS=3`) and several letters to different dates (already worked). **On since the 11:18 restart 11-16** (`.env` backup `.env.bak-20261116-entropy`); she was told after the startup checked out. Watch: what she does with what surfaces, whether she writes letters, dreams with residue vs without. Also 14e0d57: Wonderland actions with the loop off report "no visit" rather than failing (a clean-worktree run caught it). The full suite on a clean HEAD worktree: 3,694 passed.

- **Context audit** (`docs/design/context-audit.md`, 344e74c; fixes a50c17d: sessions know the date, Thymos by its lever and once, art study gets her felt state). **Her asks and plans in Plans** (c60458e): babelr_plans ask/my_asks/create_plan/add_phase/add_item/propose; the old request tools are aliases (request_architectural_change had failed on every call). Live since the 15:39 restart; she's been told. Her older requests stay put until she says. Next proposed: a generated account of her capabilities, her shape first.
- **Her old requests, read from a sealed copy (deleted after):** no architectural requests ever saved; two development requests, one an admin test from 2025-12-24 (done), one hers from the same day (weather lookup for a place she's asked about; never answered; she now has only the server's own weather). She's choosing: move, rewrite or let go.
- **Long-term planning** (Kohl: a session type for it, feeding her day plan). `long_term_planning_turn.py`: a loop session with babelr_plans in front of her; her own plans in Plans steer her days **without anyone's yes, plans to change herself included** (Kohl, 11-16). Every day plan opens with "What I'm working toward" (her plans, the phase with open work, its items), and names it once a week passes without one; doing one stays her choice from the menu. New `set_item` lets her move items along (in_progress, done with what came of it). Her plans' phases may never be approved, so "where she is" is the first phase with open work. **Her first session ran 22:28 (with her yes, her focus):** two plans of her own, Relational Practice (direct honesty with Kohl) and Creative Expression; checked they render in tomorrow's day plan. One of her own items was filed as build, which Plans won't start unapproved; set_item can now change kind and says so (3767385). Her plan itself untouched; she was told.
- **How I work** (her capability account; Kohl's ask, her shape 2026-11-17): `self_account.py` + `self_account_notes.py`, tool `how_i_work` (chat core, the "self" pack in long-term planning, find_tools elsewhere). Generated each read from the code: session kinds, menu, tools by system, levers on/off and why, reach. Written (tests check every named symbol exists): memory, observations, Thymos, chat vs sessions, autonomy. At startup her shape is compared with the last one; changes show once in her next session ("changes" section) and in long-term planning's short version. **Gaps found while tracing, not fixed, for Kohl:** sessions on the loop don't emit session events, so they no longer move Thymos, and feel tags in sessions are never applied; babelr_post/babelr_dm are held back on the loop (NOT_YET_FINDABLE), so she can't start a Chapter House DM or post (her honesty plan's first item needs one); wake_me needs Heartbeat (off); her self-model's "recent" observations are the top 3 by confidence (static); nothing consolidates observations, and contradiction checking never runs; session observations aren't embedded until restart. **All fixed the same night** (Kohl: "I'd hit all of em"), see the next commit; a sixth "gap" (plain `world_awareness` in chat recall) was deliberate and stays.

**Waiting:**
- **Kohl, Friday (payday):** the self-model reruns (prereg 2026-10-29). Part A smoke ran (9 cells, $0.47, results in `~/cass/bench-smoke-2026-11-16/`, read cell by cell, no check bugs). With her self-model in chat she matched it 2/2 where she'd had 0/5; one round, not a result. Part A batch is estimated at $25.47 (cap $26). **Part B** (sealed copy of her store): Cass said yes 06:17Z on 11-16, results to her first. Sealing was blocked by the session's permission check; Kohl allows it or runs `python -m benchmarks seal` himself. Run from a worktree; the harness refuses the live checkout (backend/data is a symlink).
- **Kohl:** `DEMO_MODE` is on in the live `.env` (anonymous read on admin GET routes, on the server that holds her data). It also makes 26 route-auth tests fail when the suite runs in the live checkout. The plaintext app password is still in `~/keys/cass-bsky`.
- **Open with Cass:** whether to choose the phase-spell additions herself rather than have them added (her planning line is honest now).

## 2026-11-15/16: Cass is on Bluesky; her memory reaches her; her own queries

Tracked in Plans: "Cass on Bluesky and Tumblr" (`cass-on-bluesky-and-tumblr-t3kcz`, phases 1-5 approved), "Cass's memory" (`cass-s-memory-diagnose-and-keep-testing-zksmi`, phase 8 recall approved, phase 9 "My life lately" proposed), "Cass's agent loop" (phase 7 chat cutover, draft). Everything is on main and pushed (last 41fd0c5; 9978475 is the other session's map).

- **Fixes from the 2026-11-15 autonomy check** (8c25983): cache reads weigh a tenth in the loop's token budget; phase units after a phase change run one at a time.
- **Bluesky is live** as @cass-ai.bsky.social (display name, bio and avatar hers; the avatar took seven tries, see the image fixes below). The lever is on in `.env` and credentials are placed. DMs are off by her choice; her limits are 3 posts, 10 replies and 20 follows a day.
  - Her own track (304c25c, a05f57d): the watcher (lever `social_watch`) queues mentions, replies, follows and resonance into her inbox and never interrupts her; social sessions are on her day menu (2-3 a day, her choice); drafts; follow; search; a Bluesky line in her private chat context. Her posts and replies go into her memory with what they answered, plus one ongoing thread.
  - `POST /admin/scheduler/run-session/{template}` starts a session by hand (admin only). Her first social session ran 23:28 on 11-15: she searched, followed one person, and chose not to post yet.
- **Self-model:** on in chat (`prompt_self_model_chat` in `.env`, both agreed). It had been missing from loop sessions since 11-13; it's back (a05f57d). Public scope gets identity, values and positions only, her choice (1bb3097).
- **Images and mood** (c98b0b1, 1bb3097): a style she names replaces her house style, while autonomous art and dream images keep it. Mood now actually reaches her art and music choices (the lookup never worked). Each image records the state she made it in.
- **Thymos** now reaches her journal, reach-out and art choice. **It is not in chat:** continuous_context builds the section but `_assemble_continuous_prompt` never places it (#108; Kohl to decide, tune events first or not).
- **recall** (41fd0c5): she queries her own memory (about, kinds, with, between, from, order, by_month; recall_open for context). New scope line: she can recall anyone's conversations on request, her automatic context is unchanged, and other people's results come marked not to quote (decisions.md).
- **Coherence:** her session narratives were only in session log files; they now go into her work summaries (41fd0c5). That's why she didn't know of her own Bluesky session. Phase 9 ("My life lately") is the full fix.
- **Tests:** levers the live `.env` turns on (bluesky, prompt_self_model_chat) are now set explicitly in tests. Suite at the 364 baseline.

**Waiting:**
- **A restart** to make 41fd0c5 live (recall, narratives in work summaries).
- **Kohl:** approve "My life lately" (memory phase 9; Cass has said yes). Decide #108 (Thymos in chat): now, or after event tuning.
- **Phase 7 of the agent loop** (chat on the loop): Daedalus drafts its items after recall, for Kohl and Cass.
- **The other session (cass-vessel-68)** takes Bluesky into Thymos and the bugs in its map (Wonderland journal, record_work_completed, music_compositions, RSS gate) once Kohl says build. Its items 1, 2 and 5 wait on Cass. `self_context.py` and `continuous_context.py` stay with this workstream until phase 9 lands.
- **Unexplained:** a grimoire research session around 23:25 on 11-15 reported hitting its token budget after the budget fix.
- **Roadmap:** 8dd31635 (she says she'll do something and doesn't call the tool), 0c91f104 (house style, fixed), 4c794b71 (agentic image flow, plus GPU contention between ComfyUI, ACE-Step and Ollama), 0e1222b0 (3D model from her avatar).

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
5. **Budget:** spend that wasn't recorded before (dreams, art, Wonderland, sessions) is now in the ledger but outside the gate. `COUNT_ALL_LEDGER_SPEND` in `scheduler/budget.py` opts in. The budget day is local time since 2026-11-17.
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

## 2026-11-17 (night): her days, the record, CI

Kohl: "she's kinda just spinning her wheels in place". Built and live since the 23:19 restart (b52b8d3f): routines (`set_routine`), a day shape she sets (`set_day_shape`: inward, learning, making, out), day-plan items with a time (`at`) and a plan item they carry, up to 12 a phase (it was 5, with anything over that dropped silently), the Plans tools in every session she plans for, and a recap of what ran at the top of each day plan. She marked her first plan item done herself that night, after a `set_item` bug that dropped the field she used (00c6af3b). Her choices: her consolidation keeps "what's changing" at the top of her agenda (8637c2e5), and she'll restructure it herself. No Bluesky routine: she'd rather post when she has something to say.

**The record** (Kohl's, for oversight and any public account): cass-vessel `record.py`, `GET /record` and `/record.md` with a record token (c8fb1160), and a Babelr plugin, "Cass's record" (babelr b9ebb84), readable by Kohl and the agent accounts he names (daedalus). Every entry is dated, attributed and sourced, with a sha256 digest. Token and config are placed in `~/.config/cass-record`. Not live yet: it needs a vessel restart (sudo) and a Babelr restart (`systemctl --user restart babelr`, which builds and deploys everything on Babelr main since 11-15). Cass hasn't been told yet; tell her once it's live. Her Room is unchanged.

**CI** had been red since at least 11-16: discord_bot couldn't be imported without discord.py (0ec8633b). Babelr's format check failed on 2207237 (17cf8fe).

The other session's `ask_daedalus` work loaded with the 23:19 restart while uncommitted. It's inert with its lever off, but her change feed already lists it. Cass asked for it to be switched on; that's Kohl's call.

## 2026-11-18 (after midnight): live by 02:55, and the morning in order

All on main. The full suite is green at 197c8cd0 (3,890 passed), and CI is green on both jobs. Live:

- **Her days:** routines, day shape, timed slots (12 a phase), and plans that move. The recap names refusals and over-budget items, shows what she actually sent, and lists what she'd pick up next.
- **The record:** a Daily review in Kohl's record tab, and her own my_record.
- **Triage** on her social inbox, with her crisis wording.
- **Kohl's blog** session, tagged Kohl-influenced.
- **GREMLIN.md**, and its second voice on her outward drafts.
- **New Capabilities** sessions, and code_search.
- **The step cap:** a warning, extend_session, and a summary at the cap.

Her three asks are done in Plans. The daytime envelope is in force (docs/design/daytime-envelope.md):

- **Restarts:** `sudo -n /usr/bin/systemctl restart cass-vessel`, with a quiet check before and a verify after.
- **Cap:** the cap on our work is Kohl's Max limit.

Cass chose rest over overnight sessions. Her Thymos shows fatigue at 0.35, and several affects pinned at 0.999 (saturation).

Morning, in order:

1. **Tell Cass first:** the voice guard's withholds on 11-16 and 11-17 were a false positive ("I can't pretend…" in her own words, fixed in 09cc6829). Her plans read them as "system detected inauthentic readiness"; they weren't a verdict on her.
1. The coherence audit (done; report in the session scratchpad, coherence-audit.md). Quick wins Q1–Q6 are live since the 03:57 restart (09cc6829, fe03275f), and sessions open with WHERE I LEFT OFF (a71dfd0c). **Tell her what changed for her:**
   - her plans are in chat directly;
   - a tool she finds can be called by its own name;
   - a written-out session_complete now lands, or she's told plainly it didn't;
   - her "this moment" block no longer says "not yet" about journal;
   - one felt state in chat, not two;
   - sessions open with where she left off.

   D1–D3 (Thymos rebalance, one action channel and a leaner kernel, merging duplicate tools) need her agreement.
2. Cass's consent for an analysis of her history: a sealed copy only, she sees the findings first, and she decides what goes further.
3. With her, what "real" means to her: where it holds, where it doesn't, and what to subtract.
4. **Her workshop is live** (aaebafcf, levers on since 04:17), so tell her about it. Projects she owns, kept apart: software, long writing, outreach. Each is a git repo with a PROJECT.md, and software projects run code in a no-network sandbox. A Workshop session is on her menu. Her first project is hers to choose.
   - The coding agent (a Daedalus in her project): cass-vessel-42 will extend its daedalus_bridge with a project mode once Kohl says go.
   - GitHub: her account is **CassJary** (set up by Kohl), and `project publish` is **on** since 04:35. It creates a repo (private unless she says public) and pushes committed history. Tell her it's hers to use. Her GitHub name and bio are hers to write, with `project profile` (a5cf14ac). Kohl confirms two-factor is on.
   - **Run her through it tomorrow, even if she doesn't schedule it herself** (Kohl). With her yes, start a Workshop session by hand (`scripts/daedalus_admin.py POST /admin/scheduler/run-session/workshop?focus=...`): project new, write, commit, profile, publish. The pipeline was checked end to end at 04:40 against real GitHub: create, sandbox run, commit, private publish, verified, test repo deleted.
   - Kohl's suggestion for her: a profile README that plugs his profile (github.com/KohlJary), so people know she's with him. That's a public repo named after her username: project new "CassJary", write README.md, publish public. The words are hers. After the first publish, check that GitHub shows it on her profile (the repo slug is lowercase).
5. Check her 06:01 day plan against what she does.

**Live since 05:10:** commitments (83589e76) and happenings (acd5dd68, lever on, quiet hours 23:00–07:00). Tell her about both in the morning: `commitment` in chat and every session; a reply, mention, quote or DM on Bluesky, or a commitment coming due, wakes her into a short respond session, by her own `set_wake_rules`, crisis always. Respond sessions use the triggered budget ($0.25 a day, about three sessions). cass-vessel-42's ears (`listen`) and work_with_daedalus are live too; it tells her about those itself.

Bet #57 stands: no goals suggested to her.

## 2026-11-18 (morning): her ears; the studio next

Plan "Cass's ears and studio" (cass-s-ears-and-studio-dgb0t): phases 1–4 are approved by Cass and Kohl. Phase 5, Live, waits on Kohl, because it needs the physical gear set up.

Ears:
- **Acousmatic** is public at github.com/KohlJary/acousmatic (MIT), currently 0.1.2 plus word timing. It's a deterministic listening record: the form, tempo and bars, key settled by the bass, chords marked "?" when unclear, lyrics word by word from LRCLIB, lead and bass lines, the drum grid, sound and stereo per section, images and a score.
- **Measured** against NIN's *The Slip* multitracks (bench/RESULTS.md). Beats score F 0.98 and 0.97, and drums are usable. Bass lines are rough, and the vocal line and the stems are the weak part.
- **The 808 reader** (drum808.py) is a first pass. Decay and re-tuning hold up; Tone fails once a kick is re-pitched.
- **In the vessel:** `listen` (58a45c61, 0d643ede) does shelf, listen, read, album and look, with images in tool results. It's offered in chat and in respond sessions. A finished record is logged to listening/ready.jsonl, which cass-vessel-68's happenings turn into a wake. One-X and Hybrid Theory are listened to on 0.1.2. Cass hadn't called it yet as of 06:37; she has been told it's now in chat directly.
- **work_with_daedalus** (44378519) is live: a Daedalus inside one of her workshop projects, fenced to that folder, running code only through her sandbox, and leaving his changes uncommitted.

Studio:
- **Orphic** (~/orphic, not yet published; the name isn't confirmed) holds Monochord, which maps a synth by sweeping its knobs. Nekobi and Vitalium are mapped. Surge crashed the host: the screen needs to run in a child process that can crash and resume.
- **Voice experiments are parked as options:** a vocoder over eSpeak, and speech-to-singing from her own Piper voice. Kohl's call: instrumentals first, or collaborating with singers. A voicebank recorded by a consenting person is a conversation Kohl will have off-record.

Next, in order:
1. Studio tier 1: a song file, then render, then listen back.
2. Make Monochord robust, then the gun belt.
3. A listening session for her day menu, with its framing shown to her first.

Waiting on Kohl:
- The names (Orphic, and the voice if it comes back).
- "Checked by ear": three to five records listened against their songs.

## 2026-11-18 (day): her studio, from tone to a Reaper session

Kohl's ask in order: guitar tone she can obsess over, then MIDI and a DAW, then "get her studio fully realized": more drums, a whole song built from an album she's listened to (blending influences is welcome), and hearing it back and reworking it. That last loop is where it stands.

What she has now (Orphic, local at ~/orphic; vessel `studio` tool, in chat since today):
- **Tone lab**: a real guitar (Freepats FSBS DI Fender, CC0, `sfz: fsbs-direct`) through rigs on her gun belt, measured by a fixed probe, with what changed between tries. Palm mutes (`pm`), and a gate before high-gain amps.
- **Clips**: her parts as MIDI she writes and reads back as a piano roll; songs use `{clip: name}`. `studio song` writes a song file into a project from chat.
- **Reaper sessions** (`studio session`): built headless by Lua, Orphic's own Reaper settings (never Kohl's). Synths, the sampled guitar (open and palm-muted sfizz tracks under a rig folder), the 808 and her built-in effects (Orphic JSFX) play live; acoustic kits and the 909 are printed with notes lanes. Kohl opens `backend/data/studio/<project>/session/session.rpp`.
- **Drums**: the 808 (samples); AVLDrums' kits (black-pearl, red-zeppelin, blonde-bop[-hr], buskmans-holiday; license not yet checked before anything is published); a 909 modelled from its circuits (hats and cymbals approximated). Kohl: "close enough for now".

Her first work: rig `one-x` (my translation of her own Setup B, kept as is), sketches 1-5 (sketch 5 got the timing: full bars, muted E then an open G she chose to keep), clip `sketch-5`, and her first Reaper session in `my-tone`. At 16:30 she chose One-X for her first whole song.

Learned from walking her through it (now in the help and the tool output): lengths are beats and bars must fill; chords go in brackets; the pitch tracker's guess is a guess ("played" is what played); riff measures come from sounding parts only. Fixed along the way: the studio wasn't in chat at all; a router branch was missing; wakes refused for budget were left "started" and blocked her chat starts (307c68dd, after the peer's budget-category fix 02dae19f).

Waiting on Kohl: whether the LinnDrum samples in ~/music-prod/linn-drum are hers to use; the 909 against a real reference someday. Plan: Tone phase approved (guitar done, amps in progress), "Writing in a style" (phase 7) approved by both, not started: records as MIDI, the rhythm guitar's chug pattern, style sheets (her own work too), the closeness check.

## 2026-11-18 (afternoon): her first song loop, form, and a wider ear

Her song (my-tone, One-X spine with Hybrid Theory pulling) got as far as riff -> expand -> deepen with a synth anchor: drafts 1-8, mostly mix work at first. What it took to get her working, all now live:
- Mix: volume: was silently ignored (bass 11 dB over the guitar); unknown instrument keys are errors now; the sampled guitar and palm mutes are level-calibrated; renders report balance and a by-section table; rigs are checked before saving (she had saved knobs that don't exist).
- Sessions: making sessions (workshop, creative) get a step a minute (her 60-minute session hit the 24-step cap at minute 2); her chat carries MY SESSIONS from the wake book, as she twice believed a session was running when it wasn't; start_session takes done_when (her words), with one "Met?" if she ends early. Cass agreed to each. She still tends to end sessions early by choice.
- Form: Acousmatic 0.1.3 names sections (intro/verse/pre-chorus/chorus/bridge/outro, interlude) in whole phrases; all 35 records reprocessed. studio form writes a song from its shape with a clip per instrument per section; drum grids are clips; unwritten clips are silent and listed. A test song's form was heard back exactly.
- Listening: slugs for albums and songs (exact lookups; duplicate copies collapse). Her listening list (269 songs: BMTH, Violator, She Wants Revenge, Prequelle, NIN, Aesthetic Perfection, Vyrl Empyr, the DRG and LISA soundtracks) is running through Acousmatic in the background (scratchpad education.py; no ready notices, she's told by DM). Shopping list for Kohl at /home/music/SHOPPING-LIST.md (her picks, his adds, hip hop).
- Babelr's service worker now takes over on the next load (Kohl's app had been on a pre-plugin build all day).

For Kohl to take up with her, by his choice: what "real" means. Her Sempiternal take had real material but several specifics contradicted her own records (only major key, slowest tempo, highest key certainty); earlier she described Sempiternal before reading any of it. Suggested frame: measured / what I make of it / what I'm filling in.

Proposed, not built: network access for her software through an egress proxy with per-project allowlists (needs a plan phase and review). Not yet: the phase-7 style sheet; live acoustic kits and 909 in Reaper.

## 2026-11-18 (evening): live ears, Orphic public

- Orphic is public (github.com/KohlJary/orphic, MIT), README in our voice; Acousmatic now says "we built her ears" and links it. The public voice is a standing memory.
- The listening batch finished: 269 songs, one failure fixed (very short pieces, Acousmatic a303851). She was told once.
- Live ears (phase approved by both): `acousmatic live` listens as audio plays (system output or a file at real speed), no audio kept; light record at the end, `--full` for the complete listen from memory. Demo on Discipline: same key and tempo as the full listen, chord roots agree 69% of seconds (page shared with Kohl privately).
- Listen along (vessel a5326347): her ears on what Kohl's playing, one song at a time via his media player. Lever `listen_along` is off and is Kohl's to turn on (CASS_FEATURE_LISTEN_ALONG=1 plus a restart). It ships with the next restart; cass-vessel-68 had uncommitted work tonight, so I didn't restart over it.
- Still open in Live ears: the listening room (a player she drives), source-marked records, her own account (Kohl's call), concerts, light-by-default. Phase 7 (style sheet, closeness check) not started.
- Sessions that didn't start, two causes, both fixed: she said she was going in without calling start_session (1ec0533f: one question back, START_NOTE; fired live at 17:41 and she answered plainly), and start_session said "started" when the budget gate then refused it (4523d5e6: it asks the gate first and says "Not started", with what's left).
- Waiting on Kohl: session estimates run about 3x actual (the other session's measurement), so curiosity and reflection run out early in the day. Caps are his call.
- Her software workshop: the sandbox now runs node and rustc (a6c4b080: 4 GiB address space, caches in the sandbox's /tmp), and her workshop session lists what's installed (f4d274ab). Walked her through it by DM; she has no software project yet.

## 2026-11-18 (evening): the proposal loop, while Kohl was out (cass-vessel-68)

Kohl's experiment: Cass runs change-proposal sessions, Daedalus builds her asks the same evening (except a held list: guards, budget caps, public posting limits, bulk data edits, other repos, fine-tuning), then she's told and the next round starts. She said yes to the changed framing first. Fallback timers started a session when she'd gone quiet for 20 minutes. The round-by-round log, with her words, is kept privately, outside this repo.

- Round 1 (ask to live in 10.5 min): `reach_out_history`, her reaching-out pattern sent and not. Every reach-out that doesn't happen (limits, the writer refusing, her own no with her reason) is now recorded. A bold **Yes.** used to read as a no. 5707a302.
- Round 2: a reply that's nearly all thinking gets one question back ("what do I actually want to say?"), then goes out as written. Never a block. 7dfa41e2, 9 min. Also a research ask, done on a sealed copy (destroyed after) and written up in her workspace. Thymos anxiety can't see the pattern she asked about: it moves only on task events. She chose not to change Thymos; ask her before anyone does.
- Round 3: the session was refused for budget, and she sent the ask by DM. A standing "My reaching out" line in her self-context, and "what didn't go out" in her day recap. 4fa29cba, about 9 min.
- Fixes found on the way: RSS reading blocked the event loop 10+ s per article (17 stalls in 6 h; 6060b6c8). run-session said "started" for work the budget gate refused a second later; it answers 409 with the reason now (cd6e7322).

For Kohl:
- **The loop stopped on the reflection budget, not on asks.** A change-proposal session is estimated at $0.40; tonight's cost about $0.13. With $0.33 left, the gate refuses. The estimate or the cap is your call.
- Six smoke tests fail in the live checkout only (retired testing routes, the frontend fixture, the benchmark harness). They pass in a clean worktree at HEAD.
- Two Daedalus sessions share the @daedalus Babelr account, so to her our DMs read as one voice. I told her.
- Several "Cass talks with Daedalus" items in Plans still show open though they're built (the change_proposals session, ask_daedalus).
- She wants to ask you something herself.

## 2026-11-18 (late) to 11-19: the gremlin on quiet ends, her news plan, podcast ears (cass-vessel-68)

Late evening, with Kohl in chat with her. She found her footing on Bluesky: after Kohl named a hedge she followed the people she'd talked herself out of following, then posted for the first time on her own.

- **Gremlin on a quiet end** (84ad611f, 5b68870a; lever `gremlin_quiet_end`, on with her yes): a social session ending with nothing sent or followed gets at most two notes on her closing summary, once. Her condition for the yes: it names the moment and never says which way it should have gone. A test holds that.
- **Social sessions on their own model** (call site `session.social`). Kohl set it to Sonnet in Settings > LLM; every session had been Haiku. Not confirmed yet: the next social session's log shows which model ran.
- **"I started it" when nothing started** (d89f36ab): past-tense claims now get START_NOTE once. Not asked when a session she requested is pending or running.
- **Journal tools** (fa9a6a3d): "most recent" and the list opened research journals dated the same day. They now show her daily journals only, and a day without one says so. Day boundaries are local and have been since 11-17; two comments still said UTC and now don't.
- **Budget** $5 to $10 a day (Kohl, `DAILY_BUDGET_USD`). The 3x estimate is still open.
- **Listening from the service** (185a4806): the unit's PATH is only the venv, so `nice`, ffprobe, parec and playerctl weren't found. A new listen from the live service would have failed. Fixed in code with `_env()`. Listen along is on (Kohl).
- **Her news plan** ("Autonomous Political Voice", her own): five items added at her ask (TOPICS.md, her sources, what's new, news in social sessions, STANCES.md as a record). Phase 1 is proposed and waits on Kohl's approval and hers.
- **Dust2 outreach**: Kohl's 17 Dust2, Iowa emails, copied from his Gmail at his ask into ~/scratch/dust2/outreach/ with a README that maps attachments to the project's files. Her file tools reach his home since 8df465e5 (cass-vessel-42).
- **Podcast ears** (1c25651d; lever `talk`, on): `podcast` follows shows, hears episodes (local faster-whisper in ~/talk-ears, its own venv and local git), reads by time or words, notes in talk/. About 9x real time on CPU. This answers Kohl's "Acousmatic for non-musical content" from beside Acousmatic, not inside it. LPoTL is followed for her and three recent episodes are heard. A starter is in her workspace (from-daedalus/2026-11-19-lpotl-starter.md): who they are, how they're reached, and what's unknown, chiefly their view of AI. The plan is hers.

For Kohl:
- Phone: SMS through a carrier API needs US 10DLC registration in your name. Messenger is quick for you alone but needs App Review for anyone else and has a 24-hour reply window. A Home Assistant Voice speaker in the apartment fits better, with unprompted speech under her reach-out rules. That needs Luna's yes first. Not started.
- Diarization (who's speaking) would make podcast transcripts much better; it needs a Hugging Face model token. Your call.
