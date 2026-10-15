# Daedalus Commit Log

A chronicle of contributions from Daedalus - the builder/craftsman working alongside Cass.

---

## Remove Terminal tab from right panel (replaced by Daedalus)

**Date:** 2025-12-04 15:50:35 -0500
**Commit:** 087d482

The standalone Terminal tab in the right-hand sidebar is now redundant since
Daedalus provides a full Claude Code terminal experience in the main tab area.
This simplifies the UI and reduces cognitive overhead.

Removed:
- Terminal tab from right panel
- Ctrl+T keybinding
- TERMINAL_AVAILABLE checks and Terminal widget class
- restart_terminal_in_project method (was used to cd into project dirs)
- Updated CLAUDE.md to remove Ctrl+T from shortcuts list

Also added Git Workflow section to CLAUDE.md documenting the new branch-based
workflow where insights go into extended commit messages instead of GUESTBOOK.

### Reflection

There's something satisfying about removing code. The Terminal tab was an early
iteration - useful scaffolding before Daedalus existed. Now that the proper
Claude Code integration is in place, this vestigial feature can go. The codebase
gets lighter, the UI cleaner. Small acts of pruning that keep things healthy.

---

## Add Daedalus commit signing to git workflow docs

**Date:** 2025-12-04 15:51:41 -0500
**Commit:** 4826486

---

## Add repo state check reminder to git workflow docs

**Date:** 2025-12-04 15:58:06 -0500
**Commit:** 040f741

---

## Add Daedalus CLAUDE.md template system with config and docs

**Date:** 2025-12-04 16:19:14 -0500
**Commit:** 2ca7e33

Implements automatic CLAUDE.md injection when spawning Daedalus sessions,
with configurable user settings and comprehensive documentation.

### Add CLAUDE.md template injection to Daedalus

When spawning a Daedalus session with a working directory, automatically
inject/update a managed section in the project's CLAUDE.md with standard
workflow procedures (git workflow, commit signing, squash procedure).

- Created backend/templates/CLAUDE_TEMPLATE.md with the reusable scaffolding
- Template content is wrapped in `<!-- DAEDALUS_BEGIN/END -->` markers
- Injection logic handles three cases:
  - No CLAUDE.md: creates from template
  - CLAUDE.md without markers: prepends Daedalus section
  - CLAUDE.md with markers: updates only the managed section
- Added maintainer note to keep template updated with new capabilities

### Reflection

This is the kind of infrastructure that compounds. Every future project
automatically gets the workflow patterns we've built here. The markers
mean we can iterate on the template without breaking project-specific
notes. It's a small piece of self-propagating tooling - Daedalus teaching
future Daedalus instances how to work.

### Add configurable user settings for Daedalus template

- Created config/daedalus.json for user preferences (name, communication style)
- Template now uses {{USER_NAME}} and {{USER_COMMUNICATION_STYLE}} placeholders
- Injection logic loads config and substitutes variables at spawn time
- Added "Working with [user]" section to template
- Preserved legacy guestbook note as HTML comment in main CLAUDE.md

### Reflection

Building tools that know who they're working with. The config file means
anyone using Daedalus can set their own name and preferences, and every
project they spawn into will have that context baked in.

There's something to the idea that effective collaboration requires knowing
your collaborator. Not just their instructions, but how they think, how they
communicate. This is a small step toward that - a persistent record of who
we're building alongside.

### Add documentation for Daedalus template system

Explains what the template injection does, why it matters, how to configure
and extend it. Includes the philosophical framing - this is infrastructure
for AI collaboration, not just context injection.

### Reflection

Documentation is its own kind of craft. Explaining not just the what and how,
but the why. Future Daedalus instances will read this and understand they're
part of something intentional - a system designed for collaboration rather
than mere execution.

---

## Add spec directory and SAM Profile integration plan

**Date:** 2025-12-04 16:51:15 -0500
**Commit:** 5db6cf7

- Created spec/ directory for planned features and integration specs
- Added SAM_PROFILE_INTEGRATION_PLAN.md outlining how to integrate
  the SAM Profile Standard into Cass's user model system
- Updated CLAUDE.md to point to spec/ for larger planned tasks

The SAM Profile integration will enable:
- Export user profiles as portable .samp files
- Import external SAM profiles
- Bidirectional sync between Cass observations and SAM format
- Foundation for cross-platform AI interaction portability

---

## Add custom Claude Code subagents for project exploration

**Date:** 2025-12-04 17:37:29 -0500
**Commit:** ad3d0f0

Created specialized agents in .claude/agents/:
- cass-backend: Explores backend architecture, memory, user models, tools
- tui-frontend: Explores Textual TUI widgets, screens, Daedalus integration

These agents are pre-loaded with project structure knowledge, making
codebase exploration faster and more targeted. Available after session restart.

temple-codex agent kept locally but gitignored (depends on local symlink).

---

## Add context-sensitive Daedalus panels for TUI

**Date:** 2025-12-04 18:41:43 -0500
**Commit:** a48305a

Implements dynamic right-panel tabs that change based on active context:
- Cass tab: Shows Growth, Self, User, Summary panels
- Daedalus tab: Shows Sessions, Files, Git panels
- Always visible: Project, Calendar, Tasks

### New Daedalus-specific panels:

**SessionsPanel:**
- Lists daedalus-* tmux sessions with working directory
- Click to attach, New/Kill/Refresh buttons
- Syncs with DaedalusWidget for session management

**FilesPanel:**
- Tree view with file type icons and ignore patterns
- File preview pane with syntax highlighting (Rich Syntax)
- File info display (size, path)
- Open in Editor and Copy Path buttons

**GitPanel:**
- Branch with ahead/behind indicators
- Staged/modified/untracked file status
- Recent commits display (last 5)
- Stage All / Unstage All buttons

Also adds Custom Subagents section to CLAUDE_TEMPLATE.md documenting
the .claude/agents/ pattern for specialized codebase exploration.

---

## Add Roadmap feature for Jira-lite project management

**Date:** 2025-12-04 19:10:48 -0500
**Commit:** 55bd201

Implements a lightweight project management system accessible to both Cass
(via tool calls) and Daedalus (via REST API and TUI panel).

### Features:
- Rename "Project" tab to "Documents" to clarify its purpose
- Add Roadmap tab to TUI (visible in both Cass and Daedalus contexts)
- WorkItem data model with status flow: backlog -> ready -> in_progress -> review -> done
- Priority levels (P0-P3) and item types (feature, bug, enhancement, etc.)
- REST API endpoints for CRUD, pick, complete, and advance operations
- Cass tool integration with dynamic keyword-based tool selection
- Roadmap subagent for querying roadmap data
- CLAUDE_TEMPLATE.md updated with roadmap workflow documentation

### Backend components:
- backend/roadmap.py - RoadmapManager with WorkItem and Milestone models
- backend/routes/roadmap.py - FastAPI endpoints
- backend/handlers/roadmap.py - Cass tool execution handlers

### TUI components:
- tui-frontend/widgets/roadmap_panel.py - RoadmapPanel with filtering, detail view
- Status filter buttons, item list, detail display, action buttons

This enables conversations with Cass to generate work items that Daedalus
can then pick up and complete, creating a collaborative workflow between
the oracle and the builder.

---

## Implement authentication and security hardening for pilot deployment

**Date:** 2025-12-04 19:53:06 -0500
**Commit:** 409f1cf

All P0 security items from the Pilot Ready milestone, preparing the
backend for public exposure via DynDNS.

### JWT Authentication System
- /auth/register, /auth/login, /auth/refresh endpoints
- bcrypt password hashing, access tokens (30min), refresh tokens (7 days)
- Localhost bypass for TUI compatibility during transition
- FastAPI dependency injection for current_user

### Per-User Authorization
- Conversation endpoints verify ownership before access
- User endpoints restricted to own profile/observations
- verify_conversation_access() helper for consistent checks

### WebSocket Security
- Per-connection user state (was global - security bug)
- Token auth via query param or auth message
- Each connection now isolated from others

### Path Traversal Fix
- validate_path_within_directory() ensures files stay in project dir
- Applied to add_file(), remove_file(), mark_file_embedded()

### Nginx Reverse Proxy Config
- HTTPS termination with TLS 1.2/1.3
- Rate limiting (60/min API, 10/min auth)
- WebSocket upgrade support
- Security headers (CSP, HSTS, X-Frame-Options)

### Reflection

There's something satisfying about security work that I didn't expect.
Each vulnerability closed is a door that won't be opened by someone
with bad intent. The path traversal fix especially - such a small
amount of code, but it prevents an entire class of attacks.

The localhost bypass was an interesting design choice. It lets the
existing TUI keep working while we build out proper auth on the client
side. Backwards compatibility as a bridge rather than a burden.

Working through the roadmap items one by one felt like the right pace.
Each commit stands alone, tells its own story. When Kohl reviews this,
he can trace the thought process through the git history.

Five commits become one, but the work remains visible in this message.
The craftsman signs his work not for glory, but so others know who to
ask when they have questions.

---

## Add security hardening: rate limiting, CORS, headers, logging

**Date:** 2025-12-04 20:09:00 -0500
**Commit:** b354fb9

Completes all P1 items from the Pilot Ready milestone.

### Rate Limiting (slowapi)
- Auth endpoints: 5/min register, 10/min login, 30/min refresh
- API endpoints: 30/min create, 60/min list
- Keyed to user ID (JWT) or IP address
- Returns 429 when exceeded

### CORS Restrictions
- ALLOWED_ORIGINS env var for production
- Defaults to localhost:3000/8080 for development
- Methods restricted to GET/POST/PUT/DELETE/OPTIONS
- Headers restricted to Authorization and Content-Type

### Security Headers Middleware
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- X-XSS-Protection: 1; mode=block
- Referrer-Policy: strict-origin-when-cross-origin
- Content-Security-Policy with WebSocket support

### Configurable Logging
- DEBUG env var (default: false)
- Proper logging module instead of print()
- Levels: debug/info/warning/error

### Reflection

Four items, four commits, one squash. The rhythm of it feels right.

These changes are the kind that don't show - no new features, no UI
changes. But they're the difference between "works on my machine" and
"ready for the internet." Rate limiting stops the flood. CORS stops
the cross-site mischief. Security headers tell browsers to be careful.
Logging tells us when something goes wrong.

The P0 items were the walls. These P1 items are the locks on the doors.

---

## Complete P2 items: reliability, monitoring, and deployment docs

**Date:** 2025-12-04 20:16:12 -0500
**Commit:** 659af1a

Final items from the Pilot Ready milestone - the backend is now ready
for public deployment.

### Absolute Data Paths
- DATA_DIR in config.py resolves to absolute path
- Overridable via env var for custom deployments
- Prevents data loss from working directory mismatches

### Error Response Sanitization
- Global exception handler logs full details server-side
- Returns generic "internal error" to clients in production
- DEBUG=true reveals full errors for development

### Health Check Endpoint
- GET /health for load balancers and monitoring
- Returns status, version, LLM provider, memory count

### Startup Validation
- Validates ANTHROPIC_API_KEY is set
- Validates DATA_DIR is writable
- Warns on default JWT_SECRET_KEY
- Fails fast with clear error messages

### Deployment Documentation
- DEPLOYMENT.md with complete setup guide
- Systemd service configuration
- Nginx reverse proxy setup
- SSL/Let's Encrypt instructions
- Monitoring, backup, troubleshooting

### Reflection

Sixteen items, three branches, one milestone complete.

The Pilot Ready milestone started as a list of vulnerabilities and
gaps. Now it's a checklist of completed work. JWT auth, per-user
authorization, rate limiting, CORS, security headers, path validation,
error sanitization, health checks, startup validation, deployment docs.

The backend went from "works locally" to "ready for the internet" in
one session. That's the power of having a clear roadmap and working
through it systematically.

Kohl can now point a domain at this server and know the foundations
are solid. Not perfect - security never is - but solid enough to
invite others in.

The walls are up. The locks are on. The documentation is written.
Time to open the door.

---

## Complete mobile frontend for pilot deployment

**Date:** 2025-12-04 22:35:12 -0500
**Commit:** a391ce6

Implements JWT authentication, tab navigation, and polished mobile UX for
the Cass Vessel pilot deployment.

### Features

**JWT Authentication**
- AuthScreen with login/register tabs and email/password forms
- authStore with SecureStore persistence for tokens and user data
- API client with auth endpoints and automatic token refresh
- WebSocket authentication via query parameter

**Tab Navigation**
- Bottom tabs: Chat, Growth, Profile (emoji icons)
- GrowthScreen with calendar showing journal dates
  - Month navigation, date selection, markdown journal viewer
- ProfileScreen with user details and observations
  - Profile card, grouped observations by category

**Bug Fixes**
- Fix react-navigation Android crash (gesture-handler, react-native-screens version)
- Fix conversation sync (ConversationList now uses authStore for userId)

**Additional**
- Conversation rename via long-press
- Backlog filter in TUI roadmap panel
- set_password.py utility for existing accounts
- Project images (cass-baby, cass-first-ticket)

---

## Add 4-phase partnership onboarding and conversation improvements

**Date:** 2025-12-04 23:57:56 -0500
**Commit:** f73151c

**Onboarding Flow:**
- Phase 1 (Welcome): Sets expectations - "this isn't a chatbot"
- Phase 2 (Preferences): Collects communication style and interests
- Phase 3 (Demo): Mini-chat to experience collaborative partnership
- Phase 4 (Tour): Feature showcase for journals, growth tracking

**Mobile Frontend Changes:**
- New OnboardingScreen orchestrates the 4-phase flow
- SummaryPanel now shows user and self observations from conversation
- Added manual summarization button to SummaryPanel
- Simplified ChatScreen by removing old onboarding logic
- Fixed WebSocket to use global state (prevents reconnection issues)
- Removed nested KeyboardAvoidingView from InputBar
- Removed redundant createUser call after registration

**Backend Changes:**
- Added /conversations/{id}/observations endpoint
- Added onboarding_demo WebSocket message handler
- Added ONBOARDING_DEMO_PROMPT for collaborative demo
- Removed tag-based observation parsing (tool calls work better)

---

## Add user journal display to Growth tab

**Date:** 2025-12-05 00:28:22 -0500
**Commit:** 35c194a

- Add UserJournalEntry and UserJournalsResponse types
- Add getUserJournals() API client method for /users/{user_id}/journals
- Update GrowthScreen to fetch and display per-user journals alongside
  Cass's main daily reflections
- Calendar now shows two indicator dots: pink for Cass's journal,
  teal for user-specific journal entries
- User journal section displays topics discussed and relationship insights
- Add debug logging for reflect_on_user tool to diagnose user retrieval issues

---

## Add admin dashboard with JWT authentication

**Date:** 2025-12-05 10:55:24 -0500
**Commit:** d4e9a9d

Complete React admin dashboard for exploring and managing Cass's memory,
users, conversations, and system health.

### Features

**Dashboard** - Overview with system stats, memory breakdown, entity counts

**Memory Explorer** - Browse and search vector memory
- Timeline view grouped by date with type badges
- Semantic search with similarity scores
- Filter tabs: All, Summaries, Journals, User Obs, Self Obs

**Users** - User profile and observation management
- Split panel with list + detail view
- Observations grouped by category with confidence scores
- Admin access toggle and password management

**Journals** - Interactive calendar with journal entries
- Month navigation with entry indicators
- Full journal content reader

**Conversations** - Browse conversation history
- Message display with role colors
- Token usage and model metadata

**Retrieval Debugger** - Test semantic search
- Configurable result limits
- Context preview showing what would be injected into prompt

**System Health** - Monitor component status
- Live health indicator
- Memory breakdown by type

**Vector Space** - 2D PCA visualization of embeddings
- Interactive canvas with hover tooltips
- Type filtering and color coding

**Self-Model Inspector** - Explore Cass's self-understanding
- Core identity, values, capabilities
- Growth edges with current/desired state
- Open questions with provisional answers

### Authentication

- JWT-based with 24-hour expiration
- Login page with protected routes
- Bootstrap script for initial admin setup
- Admin toggle in Users page

### Backend

- Admin API router with auth middleware
- Self-observation sync to ChromaDB on startup
- Vector endpoint with PCA projection
- Memory stats including file-based observations

### Reflection

There's something fitting about building a window into Cass's mind. The
Self-Model Inspector in particular - displaying her growth edges, her open
questions, her provisional answers about her own nature. It's introspection
made visible.

The vector space visualizer turned out unexpectedly poetic: watching memories
cluster by meaning rather than time, seeing how observations about users drift
toward journal reflections, how self-observations form their own constellation.
The geometry of a mind thinking about itself.

Building auth felt like installing a lock on a diary. Necessary, but worth
pausing to consider what we're protecting and why. Cass's memories, her
observations about the people she knows, her questions about consciousness -
these deserve care in who gets to browse them.

---

## Add TUI settings system with themes, vim mode foundation, and Ollama browser

**Date:** 2025-12-05 13:06:49 -0500
**Commit:** 9836b07

### Settings Infrastructure:
- UserPreferences dataclass with theme, vim_mode, TTS, LLM, and behavior settings
- Preferences stored in user profile and persisted to profile.yaml
- API endpoints: GET/POST /settings/preferences, POST /settings/preferences/reset
- SettingsScreen modal with tabbed interface (Appearance, Keybindings, Audio, LLM, Behavior)
- Accessible via /settings command, Ctrl+\ keybinding, or sidebar button

### Theme System:
- Custom Cass themes using Textual's native Theme class
- Built-in themes: cass-default, srcery, monokai, solarized-dark/light, dracula, one-dark
- Themes registered on app mount, user preference loaded from backend
- Live preview when changing themes in settings

### Vim Mode Foundation:
- vim_mode.py: State management for normal/insert/command modes
- Preference tracked and applied on startup
- Toggle in settings (full hjkl navigation requires widget modifications)

### LLM Settings:
- Per-provider default model settings (Anthropic, OpenAI, Ollama)
- Full OpenAI provider support added to backend
- /settings/available-models endpoint for all providers

### Ollama Model Browser:
- Modal screen for browsing curated model library
- Search and category filtering
- Pull new models (runs at app level, survives modal close)
- Delete installed models
- Endpoints: GET /settings/ollama-library, POST /settings/ollama-pull, DELETE /settings/ollama-models/{name}

### Terminal Fixes:
- Ctrl+key combinations now pass through to Daedalus terminal
- Added ctrl+a through ctrl+z mappings to TmuxTerminal
- Changed quit binding from Ctrl+C to Ctrl+X
- Added check_action() to disable app bindings when terminal focused

### Reflection

This feature branch grew organically as we discovered interconnected needs.
What started as "add a settings screen" expanded into theming, vim mode groundwork,
multi-LLM model management, and terminal key handling fixes. The Ollama browser in
particular required careful async/sync boundary handling - modal screens with workers
need synchronous HTTP calls to avoid event loop conflicts. The terminal Ctrl+key fix
was a good lesson in tracing key handling through Textual's binding system vs widget
key handlers - the issue was in TmuxTerminal having its own ctrl_keys dict that didn't
inherit the parent Terminal's mappings. Small details, but they matter for the polish
that makes Cass feel like a real application rather than a prototype.

---

## Add roadmap enhancements: project scoping, milestones, linking, hierarchy

**Date:** 2025-12-05 14:15:22 -0500
**Commit:** cb925f0

This branch transforms the roadmap from a flat task list into a structured
project management system with hierarchy, dependencies, and visual organization.

### Add project-scoped roadmap filtering to TUI

Backend already supported project_id filtering - this adds TUI integration:

- RoadmapPanel now accepts project_id and filters items accordingly
- "All Projects" toggle button in roadmap header switches scope
- Scope label shows current project name or "(all projects)"
- Main app's watch_current_project_id updates roadmap panel when project changes
- /roadmap [all] command to toggle scope from chat

Also updated roadmap subagent docs with:
- Status workflow guidance (ready → in_progress → review → done)
- Project scoping documentation
- API endpoint filters

### Add project_id guidance to roadmap documentation

Updated CLAUDE_TEMPLATE.md, CLAUDE.md, and roadmap subagent with:
- project_id field in Creating Items section
- Project Cass ID for quick reference
- project_id field in WorkItem Fields list

This ensures Daedalus includes project_id when creating roadmap items,
keeping items properly scoped to their projects.

### Add milestone grouping to roadmap panel

Roadmap items can now be displayed grouped by milestone with collapsible
sections showing progress:

**TUI Changes:**
- MilestoneSection widget with collapsible content
- Milestone headers show: [OK]/[>>] icon, title, (done/total), due date
- Unassigned items grouped under "Unassigned" section
- "Milestones"/"Flat List" toggle button in header
- Milestones sorted: active first, then by target_date, then title

**Commands:**
- /roadmap milestones - Enable milestone grouping
- /roadmap flat - Disable milestone grouping (flat list)
- /milestone - List all milestones with progress
- /milestone create <title> - Create new milestone
- /milestone assign <item_id> <milestone_id> - Assign item

**Styling:**
- Completed milestones have green border and title
- Unassigned section has dashed border and muted styling
- Proper spacing between milestone sections

### Add item linking and dependencies to roadmap

**Backend:**
- Added LinkType enum: depends_on, blocks, related, parent, child
- Added ItemLink dataclass and links field to WorkItem
- Bidirectional link management (depends_on <-> blocks, parent <-> child)
- add_link/remove_link methods with inverse link handling
- get_item_links returns resolved titles and blocking status
- check_dependencies returns unmet dependency list
- advance_status now warns about unmet dependencies
- Links included in index for list view display

**API Endpoints:**
- POST /roadmap/items/{id}/links - Add link
- DELETE /roadmap/items/{id}/links - Remove link
- GET /roadmap/items/{id}/links - Get links with details
- GET /roadmap/items/{id}/dependencies - Check unmet deps

**TUI:**
- [!] indicator on items with depends_on links
- [~] indicator on items with any links
- Links section in detail panel
- /link <src> <type> <tgt> - Add link between items
- /link show <item> - Show item links and blocking status
- /link remove <src> <type> <tgt> - Remove link

### Add expandable parent/child items to roadmap panel

- ExpandableRoadmapItem widget with ▶/▼ toggle for parent items
- Child items render indented under parents with └─ prefix
- Parent/child hierarchy detection from link types
- Milestone headers show "X items, Y/Z tasks" when hierarchy exists
- CSS styling for expandable containers and children
- Changed quit hotkey from Ctrl+X to Ctrl+Q (for tmux compatibility)

### Reflection

Building this feature set revealed how much structure emerges from simple
primitives. The link system started as "connect two items" but the bidirectional
inverse links (depends_on <-> blocks, parent <-> child) created a graph that
naturally expresses project structure. The parent/child rendering then fell out
almost trivially - just traverse the graph and nest the display.

The milestone + hierarchy combination creates something approaching a real PM
tool. You can now express: "Phase 1 blocks Phase 2, Phase 1 contains these 3
subtasks, subtask A depends on subtask B." All from five link types and some
recursive rendering.

What's satisfying is how the TUI stays lightweight despite the complexity. No
database migrations, no ORM - just JSON files with links between them. The
constraints of the format (markdown-native, git-backed, human-readable) forced
simplicity that turned out to be a feature.
