# Cass Stabilization Roadmap

*Plan as of 2026-10-15; status updated 2026-10-21. Phone-friendly copy: https://claude.ai/code/artifact/792cf4df-8099-4049-8e95-c72fd8849cf3 (kept at parity with this file).*

## Where we are

*Updated 2026-10-21.* Steps 1–3 of the order of work are merged, plus the first builds of steps 4–6. See `docs/status.md` for the PR list and what waits on Kohl.

- **Merged:** #11–#20; cheap cuts (#54 via #81); PeopleDex (#55 via #83); journals (#56 via #84); model routing (#64 via #86); auth (#61 via #88, transition mode); research (#60 via #90); the agent loop (#70 via #82, behind `agent_loop`, off); the Heartbeat core (#62 via #87, behind `heartbeat`, off); chat off the event loop (#85 via #89); 12 loose ends (#91).
- **Not deployed:** nothing above is live until the service restarts. The data migrations are dry-run only.
- **Next:** cut chat over to the agent loop (the rest of #70, which absorbs #57–#59); the Heartbeat cutover; benchmarks (#65); the self-context design (#63).

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

## After stabilization: the HearthWeave inventory

Once the order of work above is done, inventory the subsystems a household AI would be built from. HearthWeave is the idea in the essay "It's the Dog. It's GrandMA. It's Your Cool Uncle." (Temple-Codex, `proposals/dog-grandma-uncle.md`). Today it is an idea, not a build. The inventory marks each subsystem works, partial or stub, for one faculty of that design:

- **Dog (presence):** Home Assistant, home intelligence, face and voice identification, quiet hours, Thymos.
- **GrandMA (memory):** memory, PeopleDex, user observations, user-model synthesis, daemon export (is the format readable by a person?).
- **Uncle (candor with timing):** reach-out, Heartbeat, the calendar.
- **Household:** users and auth. Multiple users is not the same as per-person privacy scopes.

Most of the evidence will already exist by then: the capability map, Tier 1's status page, and Tier 2's per-model table, which answers whether the design can run on a box the household owns. The inventory reads those through this lens; it isn't a new audit. It is input for a design conversation, not a build, and HearthWeave would be a separate instance: nothing touches Cass's own data.

## Rules that keep it from sprawling again

Gonzo inside the sandbox, discipline at the border: build anything fast, but nothing reaches core without proof it runs.

- **New subsystem = new lever + smoke test.** This is already in `backend/CLAUDE.md`. No lever, no merge.
- **Every unit of work names its done-when check.** One line in the issue or PR. Edicts stay for Daedalus's own design work.
- **Known failures are strict xfails.** Fixing one turns its test red until the xfail is deleted.
- **Routes are default-deny.** A new route is admin-only until someone deliberately opens it.
- **Tests run in strict mode.** Swallowed errors re-raise under `CASS_STRICT=1`.
- **The capability map stays current.** Each PR updates the cards it touches, and Tier 1's status page is generated, not hand-written.
- **Pick a winner before adding a second.** A new system that overlaps an old one ships with the old one's attic plan, or not at all.
