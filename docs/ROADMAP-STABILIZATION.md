# Cass Stabilization Roadmap

*As of 2026-10-15. Phone-friendly copy: https://claude.ai/code/artifact/792cf4df-8099-4049-8e95-c72fd8849cf3 (kept at parity with this file).*

## Where we are

Stabilization is done and waiting on review. Five stacked PRs take the suite from 405 tests to about 2,500, and every tool Cass is offered now runs. Merge them in order, #11 first.

| PR | What it proves |
| --- | --- |
| [#11 Security lockdown](https://github.com/KohlJary/project-cass/pull/11) | Every route needs login by default; dangerous ones need admin |
| [#12 Levers + test harness](https://github.com/KohlJary/project-cass/pull/12) | 32 per-subsystem switches, a fake LLM, smoke batteries |
| [#13 Silent breakage](https://github.com/KohlJary/project-cass/pull/13) | Journals, spells, research, memory search and inline tags actually run |
| [#14 Tools and endpoints](https://github.com/KohlJary/project-cass/pull/14) | All ~240 offered tools dispatch and execute; frontend drift down from 46 to 23 |
| [#15 Runtime hazards](https://github.com/KohlJary/project-cass/pull/15) | Per-turn LLM state, capped tool loop, relay parity, safe rollback |

Two things to do around these merges:

- **Before deploying #11:** set `DEFAULT_LOCALHOST_USER_ID` to your admin user, or the TUI and Godot get 401s.
- **After #13:** research spells really call Ollama. Run `CASS_PROFILE=quiet` until you want that spend.

Every verified leftover is filed as an issue with file:line evidence and a one-line done-when check. They're rolled up in [tracking issue #53](https://github.com/KohlJary/project-cass/issues/53).

## Consolidation plan

Each duplicate cluster gets one verdict:

- **Consolidate** onto the system that already works.
- **Cut** what nothing uses. Cut means moving it to an `attic/` branch, never deleting it.
- **Build a new subsystem** where patching would cost more.

| Cluster | Verdict | What happens | Epic |
| --- | --- | --- | --- |
| Calendars, dead work tracking, ~5.8k LOC of dead modules, unwritten tables, 3 backup systems | Cut | Keep the SQLite calendar, the roadmap and unified goals; attic the rest | #54 |
| Knowledge about users (4 stores) | Consolidate | Move everything onto PeopleDex, which is what the prompt reads; migrate the legacy rows and the YAML | #55 |
| Journals (3 generators, split storage) | Consolidate | One generator; SQLite is the source of truth and Chroma the search index | #56 |
| Chat entry points (WebSocket, relay, POST /chat, HA, Discord) | Consolidate | All five become thin wrappers over the shared turn pipeline from #15 | #57 |
| System-prompt builders (6–7) | Consolidate | Everything goes through `continuous_context`; cut the chain editor and prompt-configs, which affect no live prompt | #58 |
| Session runners (12 legacy + generic) | Consolidate | Port solo reflection and research sessions to GenericSessionRunner; attic the other 10 | #59 |
| Research (5+ systems, 3 search backends) | Consolidate | One queue, one runner, a model chosen per step through routing | #60 |
| Auth (2 stores, 2 JWT systems) | Consolidate | One SQLite store, one token type with roles | #61 |
| Schedulers (cron, spells, phase queues, Thymos, legacy loops) | New subsystem | Heartbeat: one clock, one work registry, one budget gate and one run log; the rest become triggers | #62 |
| Self-knowledge (~17 stores) | New subsystem (design first) | Self-context: a ranked, token-budgeted section of her prompt, fed by one read API | #63 |
| LLM call sites (models and spend scattered) | New subsystem | Model routing: every call picks its model from `llm_config`, one spend ledger, an admin page | #64 |

Left alone for now:

- Both Wonderland servers (the standalone one is deployed).
- Resend vs Mailgun.
- Face ID, which is split between the backend and `vision/`.

Slow down on the self-context epic. It decides what of her interior she actually experiences, so it starts as a design conversation, not a build.

## Order of work

Cheap, low-coupling work goes first, so each later phase lands on a smaller codebase. Heartbeat goes last because 15 of the 32 levers live in it.

1. Review and merge #11–#15, then fix the high-severity loose ends (#16–#20).
2. Cheap cuts (#54).
3. PeopleDex (#55) and journals (#56).
4. Chat pipeline (#57), then the prompt builder (#58). The self-context section lands here.
5. Session runners (#59), then research (#60). Research needs model routing first.
6. Auth (#61), then Heartbeat (#62).

Two tracks run alongside from day one:

- **Model routing (#64)** gates the research pipeline and benchmark Tier 2. It can be built while the PRs are in review.
- **Self-context design (#63)** gates the prompt builder and benchmark Tier 3.

## Benchmark suite (#65)

The benchmark answers three different questions in three tiers. The levers double as ablation switches for the hardest one.

| Tier | Question | How | Cadence |
| --- | --- | --- | --- |
| 1. Machinery | Does every subsystem run? | Smoke batteries against the fake LLM, plus a generated status page | Every PR |
| 2. Capabilities | Does each capability work with real models? | Scripted scenarios with rubrics, run once per model | Weekly on `main`, budget-capped |
| 3. Interior | Does the interior change anything? | The same conversations run against three configurations (ablations) | Weekly on `main`, budget-capped |

Tier 2 starts with these scenarios:

- She recalls something from three sessions ago.
- A journal written at night shows up in the next day's context.
- An intention she registers gets followed up.
- A tool call does the right thing, not just a thing.

Once model routing lands, Tier 2 runs per model. That turns "what can move to local inference?" into a table of evidence.

Tier 3 compares three configurations, each set by levers:

1. Full Cass.
2. Cass with the self-context section turned off.
3. Plain Claude on the same model, with only the kernel.

It measures:

- Consistency across sessions.
- Whether her stated values hold under pressure.
- Whether her self-reports match her stored self-model.
- How she handles contradictions.

Two rules for Tier 3:

- **Criteria are written before any run, and not by Kohl.** Claude drafts them, Momus attacks them, and Kohl makes the final cut. They're committed before the first run.
- **Failures are published alongside wins.** The dashboard keeps history, so the result is the curve over time, bad weeks included.

Tier 1's status page can start now. Tier 3 waits on the self-context design, because ablating a section that doesn't exist yet measures nothing.

## Rules that keep it from sprawling again

Gonzo inside the sandbox, discipline at the border: build anything fast, but nothing reaches core without proof it runs.

- **New subsystem = new lever + smoke test.** This is already in `backend/CLAUDE.md`. No lever, no merge.
- **Every unit of work names its done-when check.** One line in the issue or PR. Edicts stay for Daedalus's own design work.
- **Known failures are strict xfails.** Fixing one turns its test red until the xfail is deleted.
- **Routes are default-deny.** A new route is admin-only until someone deliberately opens it.
- **Tests run in strict mode.** Swallowed errors re-raise under `CASS_STRICT=1`.
- **The capability map stays current.** Each PR updates the cards it touches, and Tier 1's status page is generated, not hand-written.
- **Pick a winner before adding a second.** A new system that overlaps an old one ships with the old one's attic plan, or not at all.
