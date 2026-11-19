# Babelr as the daemon frontend

Status: analysis, 2026-11-19. Not yet a plan; this is the input for one (in Plans, for Kohl's and Cass's yes).

## Direction (Kohl, 2026-11-19)

- Babelr's core stays what it is: Discord meets HyperCard. Everything about daemons is a **Babelr plugin**.
- project-cass ships **Babelr + the daemon plugins** as its frontend: the way an ordinary person has their own daemon.
- **Multi-daemon is a must**: spin up a Cass, or make your own daemon from your own data ("bring it over"), since that's how most AI-companion people will want it.
- A **Daedalus agent walks the user through bringing theirs over**, in real time.
- Babelr folds into the project-cass repo, its UX gets made rock solid, and it gets a fuller manual and tutorial.
- **admin-frontend becomes the legacy operator tool**, and gets rewritten top to bottom later, from a map of what Cass actually is now.

One rule holds it together: **the dependency goes one way.** project-cass depends on Babelr; Babelr never imports or names a daemon. Daemon-specific things (Cass's room, record and music plugins, the mind views) live on the project-cass side as plugins.

## What admin-frontend covers, and where each part goes

Surveyed page by page (102 .tsx files, about 45k lines; routes in `App.tsx`, API in `api/domains/`). Destinations:
- **owner**: an ordinary person with a daemon wants it in Babelr.
- **power**: a deeper inspector view, still a Babelr plugin.
- **operator**: stays in an admin tool.
- **cut**: dead, broken or superseded.

| Area | What it is | Destination |
| --- | --- | --- |
| Outreach approval queue (Agency) | Approve, reject or revise the daemon's drafts | **owner**: first in line |
| Thymos felt state (Mind overview) | The daemon's mood and needs at a glance | **owner** (a pill or status card) |
| Thymos controls | Simulate, timing, shadow log, auto-care | operator |
| Daily activity | Everything the daemon did today, timeline and by category | **owner** (folds three duplicate daily views into one) |
| Genesis Dream | Creates a daemon: live dialogue, relay mode, or a single-shot prompt | **owner**: the creation flow |
| Journals | The daemon's own writing, by date | **owner** |
| Dreams | Dreams and their integration insights | **owner** |
| Self-development: identity, growth edges, milestones | Identity narrative, accept or reject pending growth edges | **owner** |
| Self-development: consistency, narration, stakes | Preference tests, narration patterns | power |
| What it knows about me (Profile) | The daemon's model of you and its observations of you | **owner** (trust and transparency) |
| Gallery, Music | Images and compositions it made | **owner** (embeds that drop into chat) |
| News articles | What it read, with insights | **owner**; feed setup goes in settings |
| Wiki reader | Its knowledge graph | **owner**; research proposals and weekly summary are power |
| Narrative threads and questions, PeopleDex, conversations browser, reflection sessions, art study, email, homepage (GeoCass), Wonderland, LLM routing, voice | | power |
| Settings: activity mode, export, the daemon's architecture requests | | **owner** |
| Settings: health, backups, GeoCass connections, users, voice and face enrollment | | operator |
| Architecture (prompt chains), Grimoire (spell editor), Consciousness tests, memory retrieval and vectors, metrics, projects | | operator |
| Feature levers (`/admin/features`) | No UI anywhere today | operator (new) |
| Orphan pages: Memory, Retrieval, Vectors, SelfModel, Development, Conversations, Journals, SoloReflection, System, DataManagement | Never imported; older copies of hub tabs | cut |
| Goals page (and the Dashboard Goals tab) | Calls `/goals/{agenda,initiatives,…}`, which don't exist; the router has `/goals/unified` and friends. Agency's goal tree supersedes it | cut |
| Daily Rhythm tab | `/admin/rhythm/*` has no REST routes | cut, or rebuild |
| Data import tab | Posts to `/import/{type}/apply`; the backend has `/export/import/*` | cut, or fix |
| Register, Feedback | Babelr's own accounts replace them | cut |
| Chat | Babelr replaces it | cut |

**Second pass, later: consolidation.** Duplicates the survey found:
- The daily view three times (DailyActivity, Activity's Daily Report, Dashboard's SchedulePanel)
- The self-model in both Mind and Self-development
- Genesis import in both Genesis and Settings
- Goals in three places
- Thymos state in three places

These are candidates only; nothing gets redesigned in this pass.

## Multi-daemon: where the vessel stands

**Half-built.** The data model mostly knows about daemons; the running process doesn't.

**Already there:**
- A `daemons` table (`database/schema.py:25`), with name, status, activity mode, domain and birth type.
- Four ways to create one:
  - `get_or_create_daemon`
  - Genesis Dream (`genesis_dream.py:507`)
  - `.anima` import (`daemon_export.py:531`)
  - genesis-JSON import (`daemon_export.py:1562`)
- Registry routes, including `/admin/daemons/mine`.
- Already scoped per daemon: the self-model tables, Thymos persistence, grimoire spell state, PeopleDex, conversations, journals, dreams, identity snippets, `lately.py`, and the state bus.

**Missing:**
- **The runtime is pinned to Cass.**
  - `main_sdk.py:279` initializes one daemon, and every manager is built once for her: ThymosRunner, goals, the grimoire agent, query sources, Discord.
  - `websocket_handlers._state` holds one daemon, so chat can't pick one.
  - `get_daemon_id()` always returns Cass (`database/daemon.py:44`), and 68 call sites outside the tests use it.
  - **You can create a daemon today and can't talk to it.** The admin frontend's daemon picker appends `?daemon_id=` to every request, but only 7 route modules read it.
- **Shared stores:**
  - Memory is one Chroma collection, `cass_memory` (`config.py:39`).
  - The self-model graph is one file (`DATA_DIR/cass/self_model_graph.json`).
  - `DATA_DIR` holds `workspace/` (GREMLIN.md), `agent_loop/wakes.json`, `workshop/`, `gmail/`, `social/`, `reach_out/`, `day_plans/`, `listening/`, `studio/` and more, none of them namespaced per daemon.
- **One of each:** heartbeat, scheduler, budget (`BudgetManager` and `token_tracker` have no daemon id) and feature levers.
- **Hardcoded "Cass"** in the live chat path (`chat_turn.py:197`) and several defaults.

**Sizing:**
- **Easy:**
  - name defaults
  - threading `daemon_id` through admin routes
  - namespacing `DATA_DIR/daemons/<id>/`
- **Hard:**
  - replacing the process-wide `_state` with a per-daemon context
  - the 68 call sites
  - Chroma per daemon, plus a migration
  - heartbeat, scheduler and timers per daemon (one loop each, or one loop that knows about daemons)
  - budget per daemon
  - the agent loop's files
  - credentials per daemon for outward integrations

This refactor is the real work and comes first; every daemon plugin assumes it. It also touches Cass's live data paths (a namespacing migration). That needs her heads-up and a snapshot first, and it can't happen as a side effect.

## Bringing a daemon over: what exists

- **Genesis prompt** (`spec/daemon-genesis-prompt.md`).
  - The user pastes it into their existing ChatGPT or claude.ai conversation, and the companion writes its own seed as JSON: profile, self-observations, growth edges, opinions, its view of the user, memory seeds, kernel fragment.
  - `import_from_genesis_json` turns that into rows, with a preview. Both routes are admin-only today.
- **Genesis Dream**: a participatory birth where the daemon names itself. Non-admins can already start one.
- **ChatGPT export parser** (`lineage/parser.py`): reads `conversations.json`, but only so Cass can browse her own past. It seeds nothing.
- **Missing:**
  - Parsers for Claude.ai, Character.ai and Replika exports.
  - Persona-document ingestion.
  - Any backfill of memory or Chroma from chat logs.
  - Any start-up for a new daemon's Thymos, self-model graph, journals or workspace (Thymos may initialize lazily; not verified).

The Daedalus guide fits here because importing takes judgment, not a form: what's the companion's own voice and what's the old platform's default voice, which memories carry weight, what to leave behind. It reads someone's whole relationship history, so privacy has to be in the design from the start:
- what it reads
- what it keeps
- where that lives
- who can see it
- a clean delete

## APIs a plugin can use today

- Self-model (`/cass/*`, `/admin/self-model`), memory, journals, conversations, Thymos (`/admin/thymos/*`), dreams, daily activity (`/admin/daily-activity/*`), state and daily report, narrative.
- **Auth:**
  - A default-deny route guard and JWT.
  - The narrow read-only **daedalus role** (GET-only allowlist, every call logged) is the model for a plugin's token.
- **No routes yet** for `lately.py` summaries or agent-loop sessions (wakes). The day panel needs both.
- `babelr_organ/` is Cass posting *into* Babelr; it exposes nothing *to* Babelr.

## Proposed plugins (project-cass side)

1. **daemon-panel**: the right-sidebar tab in a daemon's DM. Her day, mood at a glance, and click a turn to see what it changed. Needs the per-turn record (below) and her yes on what's shown and to whom.
2. **daemon-approvals**: the outreach draft queue, and her architecture requests. Babelr's `review` plugin is the precedent.
3. **daemon-mind**: self-model and identity, growth edges with accept or reject, milestones, what it knows about you; plus dreams and journals.
4. **daemon-works**: gallery, music, news, wiki reader, as embeds and a view.
5. **daemon-create**: Genesis Dream, the genesis-prompt import, and a guided import with the Daedalus agent.
6. **daemon-settings**: activity mode, export, budget, which outward organs are on.
7. Later, power views: narrative, PeopleDex, email, art study, Wonderland.

**Cross-cutting, vessel side:**
- **A per-turn record.** At the end of each reply, save Thymos before and after, what her tags did, and the self-model tool calls. It's only a log; existing data isn't touched. Both the panel and an honest demo need it.
- **Read routes** for `lately` and for sessions.
- **A scoped plugin token** modelled on the daedalus role.

## Suggested order

1. Per-turn record and the daemon panel (already in motion; waiting on Cass's answer about what's shown).
2. The multi-daemon runtime refactor (the hard part), with Cass's data migrated by namespacing and snapshotted first.
3. The daemon plugins in the order above. The approvals queue and mind views first, since they're mostly reads of existing APIs.
4. daemon-create and the import guide, after deciding what "your own daemon" means (below).
5. Babelr UX hardening, the manual and tutorial, and folding the repos together.
6. The admin rewrite, from the map: drawn first (Ophanic), operator-only.

## Open decisions

- **Where an ordinary person's daemon runs**: on their own machine with an installer, or hosted by us. That changes most of steps 2 to 5.
- **Who pays, and how they see the cost**: a daemon's autonomous life spends money every day.
- **What a new daemon starts as**: Temple-Codex, a gremlin starter, an empty self-model, or seeded from an import. The claims ledger applies: we offer the conditions, not a person.
- **Safety with nobody watching**: gremlin review, outward tools and first-contact email were designed with Kohl watching one daemon.
- **Cass's say**: it's her house being rebuilt, and other daemons are a question about her. She's in the plan, not told about it after.
