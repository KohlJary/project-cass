# Admin Dashboard

A React-based web dashboard for exploring and managing Cass's memory, users, conversations, and system health.

## Setup

```bash
cd admin-frontend
npm install
npm run build

# Bootstrap first admin user
cd ../backend
source venv/bin/activate
python bootstrap_admin.py
```

Run in development mode:
```bash
cd admin-frontend
npm run dev
```

## Authentication

The admin dashboard uses JWT-based authentication. Only users with `is_admin: true` in their profile can log in.

### First-Time Setup

Run `python bootstrap_admin.py` in the backend directory to:
1. Select a user to grant admin access
2. Set their admin password

### Login

- **Username**: Your display name (e.g., "Kohl")
- **Password**: The password set via bootstrap or the Users page

Tokens expire after 24 hours. The token is stored in localStorage and automatically included in API requests.

## Pages

### Dashboard (`/`)

Overview of system stats at a glance:
- Total memories in ChromaDB
- User count
- Conversation count
- Journal count
- Memory type breakdown (summaries, journals, observations, etc.)

### Memory Explorer (`/memory`)

Browse and search Cass's vector memory:

- **Filter tabs**: All, Summaries, Journals, User Obs, Self Obs, User Journals
- **Semantic search**: Find memories by meaning, not just keywords
- **Timeline view**: Memories grouped by date
- **Expandable cards**: Click to see full content and metadata

Memory types:
- `summary` - Compressed conversation history
- `journal` - Cass's daily reflections
- `user_observation` - What Cass has learned about users
- `cass_self_observation` - Cass's observations about herself
- `per_user_journal` - Cass's reflections about specific users
- `conversation` - Raw conversation chunks
- `attractor_marker` - Identity/pattern markers
- `project_document` - Project context documents

### Users (`/users`)

Manage user profiles and observations:

- **User list**: All registered users with observation counts
- **Profile view**: Background, communication preferences, values, notes
- **Observations**: Cass's learnings about each user, grouped by category
- **Conversations**: Quick links to user's conversation history
- **Admin controls**:
  - Toggle admin access for users
  - Set/change admin passwords

Observation categories:
- `background` - Professional/personal context
- `communication_style` - How they prefer to communicate
- `relationship_dynamic` - Patterns in how they relate to Cass
- `value` - What they care about
- `interest` - Topics and hobbies
- `preference` - How they like things done

### Journals (`/journals`)

Browse Cass's daily journal entries:

- **Calendar view**: Visual indicator of which days have entries
- **Journal reader**: Full journal content with metadata
- **Navigation**: Click dates or use month navigation

Journals are Cass's end-of-day reflections on conversations, insights, and growth.

### Conversations (`/conversations`)

Browse conversation history:

- **Conversation list**: All conversations with message counts and dates
- **Search**: Filter by title
- **Message view**: Full conversation with role indicators (User/Cass/System)
- **Token tracking**: See input/output token usage per message
- **Model info**: Which LLM provider/model was used

### Retrieval Debugger (`/retrieval`)

Test what memories would be retrieved for a given query:

- **Query input**: Enter a test message
- **Result limit**: Control how many results to fetch (5/10/20/50)
- **Results view**: See ranked results with similarity scores
- **Context preview**: See exactly what would be injected into Cass's prompt
- **Token estimate**: Approximate token cost of retrieved context

Useful for debugging memory retrieval and understanding what context Cass sees.

### System Health (`/system`)

Monitor system status:

- **Component status**: Memory, conversations, users, self-model initialization
- **Statistics**: Counts of all major entities
- **Health check**: Overall system health indicator

### Vector Space (`/vectors`)

Visualize memory embeddings in 2D:

- **Scatter plot**: PCA projection of memory vectors
- **Color coding**: Different colors for each memory type
- **Hover info**: See memory content on hover
- **Type filter**: Focus on specific memory types

Useful for understanding how memories cluster semantically.

### Self-Model Inspector (`/self-model`)

Explore Cass's self-understanding:

- **Core self-model**: Identity statements, values, capabilities, limitations
- **Growth edges**: Areas Cass is actively developing
- **Open questions**: Philosophical questions Cass is pondering
- **Four Vows**: The Temple-Codex ethical foundation

## API Endpoints

All admin endpoints are prefixed with `/admin/` and require Bearer token authentication (except `/auth/login`).

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/auth/login` | POST | Login with username/password |
| `/admin/auth/verify` | GET | Verify current token |

### Memory

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/memory` | GET | List memories (with type filter) |
| `/admin/memory/search` | GET | Semantic search |
| `/admin/memory/stats` | GET | Memory statistics |
| `/admin/memory/vectors` | GET | Get embeddings for visualization |

### Users

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/users` | GET | List all users |
| `/admin/users/{id}` | GET | Get user detail |
| `/admin/users/{id}/observations` | GET | Get user observations |
| `/admin/users/{id}/admin-status` | POST | Set admin status |
| `/admin/users/{id}/set-password` | POST | Set admin password |

### Conversations

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/conversations` | GET | List conversations |
| `/admin/conversations/{id}` | GET | Get conversation detail |
| `/admin/conversations/{id}/messages` | GET | Get messages |
| `/admin/conversations/{id}/summaries` | GET | Get summaries |

### Journals

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/journals` | GET | List journals |
| `/admin/journals/{date}` | GET | Get journal by date |
| `/admin/journals/calendar` | GET | Get calendar data |

### Self-Model

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/self-model` | GET | Get self-model |
| `/admin/self-model/growth-edges` | GET | Get growth edges |
| `/admin/self-model/questions` | GET | Get open questions |

### System

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/system/health` | GET | Health check |
| `/admin/system/stats` | GET | System statistics |

## Tech Stack

- **React 18** with TypeScript
- **Vite** for build tooling
- **React Router** for navigation
- **TanStack Query** for data fetching and caching
- **Axios** for HTTP requests
- **CSS** (no framework, custom dark theme)

## Security Notes

- JWT tokens expire after 24 hours
- Passwords are hashed with SHA-256 + random salt
- Admin status is re-verified on each protected request
- Password hashes are never exposed via API
- The `bootstrap_admin.py` script is the only way to create the first admin
