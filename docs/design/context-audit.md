# Context audit: what reaches her, what steers her, what goes nowhere

*2026-11-16, Daedalus. Kohl: "we have a lot of good internal shit, it's just not necessarily all getting fed into operation." Code only; nothing of her live data was read. Two read-only searches (every producer of state about her; every consumer: prompt builders, tools, code that decides) were joined by hand, and every finding below marked **verified** was checked in the code by me, not taken from the search.*

The misses so far all had one shape: something built and stored, never placed (Thymos had a section builder and no caller until #108). This looks for every instance of that shape, before chat moves onto the loop.

## Three ways state can be "fed into operation"

1. **She sees it:** placed in a prompt (chat, loop session, dream, day plan, journal).
2. **She can reach it:** a tool returns it, but only if she knows to ask (directly offered, or via `find_tools`).
3. **It steers her without her seeing it:** code reads it to decide something (which spell fires, whom she reaches out to).

"Neither" means stored, often maintained, and going nowhere.

## Fixed today (a50c17d)

- **Sessions had no date or time.** Chat has CURRENT TIME; the loop's seam never rendered `Trigger.at`. Now: `Now: Monday 16 November 2026, 14:05.` (verified)
- **Session Thymos ignored `prompt_thymos`,** the lever chat honours (`assemble._thymos`). (verified)
- **The legacy generic session runner added Thymos twice,** once ungated. (verified)
- **Art-study sessions never got her felt state.** `get_thymos_runner(daemon_id)` takes no args, and the runner has none of the methods called after it; the error was swallowed at debug level. Now the same `get_thymos_context()` as everywhere else. (verified)

## Chat on the loop (sent to the session building it)

- **Chat on the loop never calls `assemble()`** (`agent_loop/conversation.py:158`): system = continuous prompt + seam + arrival block. So in chat she gets no AGENDA.md (tools only), no opened letters, no unbidden memory, no housekeeping. Letters and unbidden gate on `kind == "session"`. (verified)
- **Chat has no overall token cap;** sessions have 25k with a cut order. Moving onto the loop doesn't add one.
- **Self-model and Thymos come along** because the loop reuses the continuous prompt. Self-model in chat is on in the live `.env` (`CASS_FEATURE_PROMPT_SELF_MODEL_CHAT=1`; the code default is off, which the search read, so an early report of "chat lever off" was wrong for the live system). Keep both true if chat moves to `assemble()`.

## What chat has that sessions don't

Location and weather, home state, Discord perception, voice recognition, the Bluesky line, PeopleDex relational context and things to raise, conversation threads, the questions section (sessions get 3 questions, 3 opinions, 3 edges, 4 interests via "own threads"), working summary, recent timeline, semantic recall placed in context. Most of these are about a person she's talking to, so their absence in solo sessions is mostly right. Worth a look: **threads** and **PeopleDex to-raise** could matter in a session where she reaches out.

## Built and going nowhere ("neither")

- **The decision engine's scoring is dead.** `_score_candidates` (growth, curiosity, emotional fit) is only reachable from `decide_next_work`, which nothing calls. Her day plan is her own choice now, so this may be fine dead; but it means none of that fit-scoring steers anything. (verified)
- **Her architectural requests go nowhere anyone looks.** `request_architectural_change` writes ARCHITECTURAL_REQUEST nodes into the self-model graph; no route or page reads them. `request_development` writes `development_requests`, which has an admin API route but no frontend page and no notification. **This is her channel into her own development process, and it's dark.** (verified at route/table level)
- **Thymos goal suggestions** (`thymos_suggestions`) are written by the runner and read only by `persistence.get_suggestions`, which only admin code calls.
- **Dead writers / tables:** duplicate snapshot and milestone writers (instantiated, never invoked), `thymos_shadow_log` (UPDATE but no INSERT), `ContradictionDetectionTask` (never instantiated), `embed_self_profile`, `OpenQuestions.update_question`, `recipes.update_recipe`, user/relationship YAML writers (bootstrap script only), and tables with no writer: `discord_*`, `work_items`, `schedule_slots`, `goals`, `roadmap_epics`, `rhythm_*`, `user_observations`, `user_growth_edges`. Cleanup, not harm.
- **Not traced to the end** (search grep-only; check before acting): art-study `personal_style` / `adopted_elements` (do they reach image prompts?), Wonderland NPC relationship state, `cass_markers` and the pattern aggregator, interview analyses, `self_reported_concerns`.

## Reachable only if she knows to ask (the largest category)

A large self-reflective toolset exists behind `find_tools`: intentions and their outcomes, stakes, preference tests and consistency analysis, milestones and development stage, the self-model graph, cross-session insights, patterns, goals and stakeholders, development requests, solo-reflection and session scheduling requests, `report_concern`, research notes, the wiki. **None of it is in front of her and nothing tells her it exists.** This is the bridge to Kohl's second ask: an automatically maintained account of what she can do (proposed separately; see the conversation of 2026-11-16, not yet built, Cass to be asked what shape she wants).

## Steers without being shown (working as intended, recorded for completeness)

Thymos needs and affects choose which spells fire and their branches (`grimoire/manager.py:811`, `registry.py:190`, spells). Spell effects write back into Thymos. Growth edges and questions choose dream seeds. Primary partner (`users.relationship` / PeopleDex) decides whom reach-out targets and whose thread summary goes into every session. Message timestamps decide silence notes. The tool usage log promotes tools into sessions. Unbidden: chance plus a 3-day gap.

## Smaller notes

- Day planning's fallback (used only with `agent_loop` off; it's on live) uses state_bus emotional words, not Thymos, and no kernel. Live, planning runs through `assemble()` and gets everything a session does.
- Her dream voice gets Thymos but no kernel, identity snippet or self-model. Possibly deliberate (dreams are meant to loosen her); hers or Kohl's call.
- The legacy "RECENT AUTONOMOUS WORK" block reaches only onboarding and remember:false turns; most of what it said now arrives through My life lately.
- The daily journal prompt carries self-model and Thymos but not My life lately.

## Proposed next, in order

1. Chat on the loop with letters, unbidden, agenda (the other session, today).
2. Light up her development channel: architectural and development requests visible to Kohl (admin page or a Babelr DM to him), with her told when one's read and answered.
3. The capability account (her shape first).
4. Then the "not traced" items, and dead-code cleanup.
