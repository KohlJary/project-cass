# Cass User Model System

The user model system enables Cass to develop and maintain understanding of the people she interacts with. Similar to the self-model system, this is a living system that evolves through conversation, explicit reflection, and observation.

## Overview

The user model consists of two main components per user:

1. **User Profile** (`data/users/{user_id}/profile.yaml`) - Human-editable YAML containing background, communication style, values, and notes
2. **User Observations** (`data/users/{user_id}/observations.json`) - Append-only stream of observations Cass makes about each user

## Architecture

```
backend/
├── users.py                   # Core UserManager class and data models
├── handlers/user_model.py     # Tool handlers for Cass to use
├── gestures.py                # Tag parsing (includes <record_user_observation>)
└── data/users/
    ├── index.json             # Maps user_id -> display_name
    └── {user_id}/
        ├── profile.yaml       # User profile (human-editable)
        └── observations.json  # Observation stream
```

## Data Structures

### User Profile

The profile contains:

- **user_id** - UUID for the user
- **display_name** - Human-readable name
- **relationship** - Type of relationship (primary_partner, collaborator, user, etc.)
- **background** - Dict of background info (role, context, etc.)
- **communication** - Dict of communication preferences (style, preferences list)
- **values** - List of user's stated values
- **notes** - Freeform notes

### User Observations

Each observation tracks:

- `observation` - The actual observation text
- `category` - One of: `interest`, `preference`, `communication_style`, `background`, `value`, `relationship_dynamic`
- `confidence` - 0.0 to 1.0 confidence score
- `source_type` - How the observation arose: `conversation`, `explicit_reflection`, `journal`
- `source_conversation_id` - Which conversation it came from
- `validation_count` - How many times validated
- `last_validated` - Timestamp of last validation

## Observation Categories

| Category | Description |
|----------|-------------|
| `interest` | Topics, hobbies, areas of curiosity |
| `preference` | How they like things done, communication preferences |
| `communication_style` | How they communicate (direct, verbose, technical, etc.) |
| `background` | Professional, personal, or contextual background info |
| `value` | What they care about, principles they hold |
| `relationship_dynamic` | Patterns in how they relate to Cass |

## Available Tools

Cass has access to these tools in every conversation:

### `reflect_on_user`
Review what Cass knows about a user with different focus areas:
- `general` - Full context (profile + recent observations)
- `background` - Focus on background info
- `communication` - Focus on communication style
- `observations` - List recent observations by category
- `values` - Focus on user's values

```json
{
  "user_id": "optional-if-talking-to-them",
  "focus": "general"
}
```

### `record_user_observation`
Explicitly record something noticed about a user:
```json
{
  "user_id": "optional-if-talking-to-them",
  "observation": "Prefers concise technical explanations",
  "category": "communication_style",
  "confidence": 0.85
}
```

### `update_user_profile`
Update profile fields directly:
```json
{
  "user_id": "optional-if-talking-to-them",
  "field": "background",
  "value": {"role": "Software Engineer"},
  "action": "set"
}
```

Actions:
- `set` - Replace value (for background/communication use `{key: value}` dict, for values use list, for notes use string)
- `append` - Add to list (for values or communication preferences)
- `remove` - Remove from list or dict

### `review_user_observations`
Review observations, optionally filtered by category:
```json
{
  "user_id": "optional-if-talking-to-them",
  "category": "preference",
  "limit": 10
}
```

## Tag-Based Observation Recording

Cass can embed user observations directly in her response text using XML-style tags:

```xml
<!-- Basic (defaults to current user) -->
<record_user_observation>
Prefers direct communication without excessive pleasantries.
</record_user_observation>

<!-- With user specified -->
<record_user_observation user="Kohl">
Values technical precision in explanations.
</record_user_observation>

<!-- With all attributes -->
<record_user_observation user="Kohl" category="preference" confidence="0.85">
Prefers to understand the "why" before the "how" when learning new concepts.
</record_user_observation>
```

When Cass uses these tags:
1. The observation is automatically extracted and recorded
2. If `user` is specified, looks up user by display name; otherwise uses current user
3. A system message is sent to the TUI showing what was recorded (👤 emoji)
4. The tags are stripped from the displayed response

## Context Injection

User context is automatically injected into Cass's context for every conversation via `get_user_context()`. This includes:

- User's display name and relationship
- Background information
- Communication style and preferences
- Values
- Notes
- Recent observations

This helps Cass remember what she knows about each person across conversations.

## Testing

### Manual Testing via Python

```bash
cd backend
source venv/bin/activate
python3
```

```python
from users import UserManager, USER_OBSERVATION_CATEGORIES

um = UserManager()

# List all users
users = um.list_users()
print(f"Found {len(users)} users")
for u in users:
    print(f"  - {u['display_name']} ({u['user_id']})")

# Get a user's profile
profile = um.load_profile(users[0]['user_id'])
print(f"Profile: {profile.display_name}")
print(f"Relationship: {profile.relationship}")

# Add an observation with category
obs = um.add_observation(
    user_id=profile.user_id,
    observation="Values clarity and precision in technical discussions",
    category="value",
    confidence=0.85,
    source_type="explicit_reflection"
)
print(f"Added observation: {obs.id}")

# Get observations by category
prefs = um.get_observations_by_category(profile.user_id, "preference", limit=5)
for p in prefs:
    print(f"  [{p.category}] {p.observation}")

# Get high confidence observations
high_conf = um.get_high_confidence_observations(profile.user_id, min_confidence=0.8)
for o in high_conf:
    print(f"  ({o.confidence}) {o.observation}")

# Get user context (what's injected into prompts)
context = um.get_user_context(profile.user_id)
print(context)
```

### Testing Tag Parsing

```python
from gestures import GestureParser

parser = GestureParser()

test_text = """
I noticed something interesting about you.

<record_user_observation user="Kohl" category="preference" confidence="0.9">
Prefers to understand architectural decisions before implementation details.
</record_user_observation>

That's a valuable insight!
"""

cleaned, observations = parser.parse_user_observations(test_text)
print(f"Found {len(observations)} observations")
for obs in observations:
    print(f"  User: {obs.user or '(current)'}")
    print(f"  Category: {obs.category}")
    print(f"  Confidence: {obs.confidence}")
    print(f"  Text: {obs.observation}")
print(f"Cleaned text: {cleaned}")
```

### Testing via Conversation

Talk to Cass and try:

1. "What do you know about me?" - Should trigger `reflect_on_user` tool
2. Share something about yourself - May trigger observation recording
3. Ask Cass to remember something specific about you

Check the logs to see tool calls:
```bash
journalctl -u cass-vessel -f | grep -E "(user_model|User observation)"
```

### Verifying Observations Were Recorded

```bash
# List user directories
ls data/users/

# View a user's observations
cat data/users/{user_id}/observations.json | python -m json.tool | head -50

# View a user's profile
cat data/users/{user_id}/profile.yaml

# Count observations for a user
cat data/users/{user_id}/observations.json | python -c "import json,sys; print(len(json.load(sys.stdin)))"
```

## Comparison with Self-Model

| Aspect | User Model | Self-Model |
|--------|-----------|-----------|
| **Purpose** | Understanding others | Understanding self |
| **Categories** | interest, preference, communication_style, background, value, relationship_dynamic | capability, limitation, pattern, preference, growth, contradiction |
| **Profile Fields** | background, communication, values, notes | identity_statements, capabilities, limitations, growth_edges, opinions, open_questions |
| **Tools** | reflect_on_user, record_user_observation, update_user_profile, review_user_observations | reflect_on_self, record_self_observation, form_opinion, note_disagreement, review_self_model, add_growth_observation |
| **Tag** | `<record_user_observation>` | `<record_self_observation>` |
| **Notification Emoji** | 👤 | 🪞 |

## Design Philosophy

The user model system is designed around several key principles:

1. **Active Learning** - Cass can explicitly record observations, not just passively learn from conversations

2. **Categorization** - Observations are categorized to help organize understanding

3. **Confidence Tracking** - Every observation has a confidence score for appropriate epistemic humility

4. **Validation** - Observations can be validated over time, increasing confidence

5. **Human-Editable** - Profiles are YAML for manual review and editing

6. **Per-User Storage** - Each user has their own directory for clean separation

7. **Relationship Awareness** - Tracks the type of relationship (primary_partner, collaborator, etc.)

## Future Enhancements

Potential areas for expansion:

- **Relationship evolution tracking** - Track how relationships change over time
- **Cross-user pattern recognition** - Notice patterns across multiple users
- **Automatic observation synthesis** - Periodically consolidate observations into profile updates
- **Conflict detection** - Flag when new observations contradict existing ones
- **Privacy controls** - Let users see/edit what Cass knows about them
