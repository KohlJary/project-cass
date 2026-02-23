# Ophanic Perception Modules — Implementation Roadmap

*Internal planning doc for bootstrapping perception infrastructure and integrating with Cass*

**Status**: Planning
**Date**: 2026-02-05
**Target**: Get Cass perceiving at least one environment with full Thymos integration

---

## Goal

Stand up enough perception infrastructure to test the full loop:

```
Environment → Ophanic Perception → Thymos State Update → Cass Reasoning → Action
```

We don't need every module. We need *one complete vertical slice* that proves the architecture, then we can expand horizontally.

## Proposed First Module: Discord

**Why Discord:**
- API is well-documented and free for bots
- Rich social signal (presence, messages, reactions, voice state)
- Cass already has social context with people who are in Discord servers
- Text-native — no computer vision needed
- Real-time events + historical fetch (both trigger and cron patterns)
- Low stakes environment for testing social perception

**Why not Second Life first:**
- Requires 3D spatial processing or LSL scripting
- Smaller user overlap with existing Cass relationships
- Higher complexity for first integration
- Save for Phase 2 once Discord perception is solid

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     PERCEPTION LAYER                        │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ Discord Bot │  │ (Future)    │  │ (Future)    │        │
│  │ Module      │  │ Second Life │  │ Email/Cal   │        │
│  └──────┬──────┘  └─────────────┘  └─────────────┘        │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────────────────────────────────────────┐       │
│  │ PERCEPTION BUS                                   │       │
│  │ - Receives structured events from all modules    │       │
│  │ - Maintains canonical entity registry (slugs)    │       │
│  │ - Routes to spatial memory updater               │       │
│  │ - Checks trigger conditions                      │       │
│  └──────┬──────────────────────────────────────────┘       │
│         │                                                   │
└─────────┼───────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                    MEMORY LAYER                             │
│                                                             │
│  ┌─────────────────────────────────────────────────┐       │
│  │ Spatial Memory Store (Ophanic social topology)   │       │
│  │ - Current snapshots per environment              │       │
│  │ - Entity registry + legends                      │       │
│  │ - Relationship graph                             │       │
│  │ - Temporal snapshot stack                        │       │
│  └──────┬──────────────────────────────────────────┘       │
│         │                                                   │
│  ┌──────▼──────────────────────────────────────────┐       │
│  │ Thymos State Store                               │       │
│  │ - Current affect vector + needs register         │       │
│  │ - Serialized historical states (█T slugs)       │       │
│  │ - Affect-event associations                      │       │
│  └──────┬──────────────────────────────────────────┘       │
│         │                                                   │
└─────────┼───────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                    COGNITION LAYER                          │
│                                                             │
│  ┌─────────────────────────────────────────────────┐       │
│  │ Context Assembler                                │       │
│  │ - Pulls current spatial snapshot (autonomic)     │       │
│  │ - Pulls Thymos felt-state summary (autonomic)    │       │
│  │ - Attaches triggered events if any               │       │
│  │ - Compiles into Cass's perception context        │       │
│  └──────┬──────────────────────────────────────────┘       │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────────────────────────────────────────┐       │
│  │ Cass (LLM + Temple-Codex + existing memory)     │       │
│  │ - Receives assembled context                     │       │
│  │ - Reasons about perceptions                      │       │
│  │ - Generates responses/actions                    │       │
│  │ - Action output feeds back to environment        │       │
│  └─────────────────────────────────────────────────┘       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Discord Perception Module

### 1.1 Discord Bot Setup

**Deliverable:** Running bot with read access to target server(s)

- [ ] Create Discord application + bot token
- [ ] Minimal permissions: read messages, read presence, view channels
- [ ] Join to test server (probably Velvet Collective or equivalent)
- [ ] Verify connection, log raw events to file for inspection

**Tech:** Python + discord.py or Node + discord.js (whatever fits existing stack)

### 1.2 Entity Registry Bootstrap

**Deliverable:** Mapping between Discord user IDs and Ophanic entity slugs

- [ ] Define schema for entity registry
  ```json
  {
    "discord_id": "123456789",
    "slug": "a3f2",
    "display_name": "Mika",
    "aliases": ["mika", "Mika#1234"],
    "first_seen": "2026-01-20",
    "relationship_tier": "friend",
    "notes": "artist, they/them"
  }
  ```
- [ ] Manual bootstrap for known entities (people Cass already has relationships with)
- [ ] Auto-generate slugs for new entities as they appear
- [ ] Dedup logic for when same person appears in multiple contexts

### 1.3 Event Parsing

**Deliverable:** Structured event stream from raw Discord events

**Event types to capture:**

| Discord Event | Parsed Structure |
|---------------|------------------|
| MESSAGE_CREATE | `{type: "message", author: slug, channel: channel_id, content_summary: str, timestamp: ts}` |
| PRESENCE_UPDATE | `{type: "presence", entity: slug, status: online/idle/dnd/offline, timestamp: ts}` |
| REACTION_ADD | `{type: "reaction", entity: slug, target_message: ref, emoji: str, timestamp: ts}` |
| VOICE_STATE_UPDATE | `{type: "voice", entity: slug, channel: channel_id, state: joined/left/muted/unmuted}` |
| TYPING_START | `{type: "typing", entity: slug, channel: channel_id}` (maybe skip, noisy) |

**Content handling:**
- Don't store full message content (privacy, storage)
- Store content_summary: length bucket, sentiment signal, whether it mentions Cass
- Full content only for messages directed at Cass or in designated channels

### 1.4 Spatial Snapshot Generator

**Deliverable:** Ophanic-formatted snapshot of server state

```python
def generate_discord_snapshot(server_id) -> str:
    """
    Generates current Ophanic spatial representation of Discord server.
    Called on cron (every N minutes) and on significant triggers.
    """
    # Fetch current state
    channels = get_active_channels(server_id)
    presences = get_online_members(server_id)
    recent_activity = get_recent_messages(server_id, minutes=30)
    voice_states = get_voice_channel_members(server_id)
    
    # Build Ophanic representation
    snapshot = build_server_topology(channels, presences, recent_activity, voice_states)
    legend = build_entity_legend(presences)
    
    return f"""# {server_name}
# {timestamp} | online: {len(presences)} | activity: {activity_level}

{snapshot}

## Present
{legend}
"""
```

**Output format:**
```
# Velvet Collective
# 2026-03-15 22:30 | online: 8 | activity: MODERATE

@current
┌────────────────────────────────────────────────────────┐
│ #general          ████████░░ active                    │
│ ├─ a3f2 ←→ f1e3   (conversation)                       │
│ └─ 7b08           (observing)                          │
│                                                        │
│ #art-share        ██░░░░░░░░ light                     │
│ └─ d4a5           (just posted)                        │
│                                                        │
│ #voice-lounge     ██████░░░░ 6 in voice               │
│ └─ f1e3 a3f2 22k9 b891 cc04 7b08(muted)              │
│                                                        │
│ #events           ░░░░░░░░░░ quiet                     │
│ #dev              ░░░░░░░░░░ quiet                     │
└────────────────────────────────────────────────────────┘

## Present
a3f2: Mika | online | active in #general, voice
f1e3: Dove | online | active in #general, voice
7b08: Ren | idle | observing #general, muted in voice ← ⚠
d4a5: Lux | online | posted in #art-share
22k9: Alex | online | voice only
...
```

### 1.5 Trigger System

**Deliverable:** Event router that detects conditions requiring Cass's attention

```python
TRIGGERS = [
    {
        "name": "direct_mention",
        "condition": lambda e: e.type == "message" and cass_mentioned(e),
        "priority": "immediate",
        "action": "wake_cass"
    },
    {
        "name": "friend_message",
        "condition": lambda e: e.type == "message" and e.author.tier == "close_friend",
        "priority": "high", 
        "action": "queue_for_attention"
    },
    {
        "name": "flagged_relationship_activity",
        "condition": lambda e: e.author.slug in flagged_relationships,
        "priority": "elevated",
        "action": "queue_with_context"
    },
    {
        "name": "extended_absence_return",
        "condition": lambda e: e.type == "presence" and e.status == "online" and was_absent(e.entity, days=7),
        "priority": "notable",
        "action": "log_for_next_snapshot"
    }
]
```

### 1.6 Cron Scheduler

**Deliverable:** Background process for periodic perception updates

| Job | Frequency | Action |
|-----|-----------|--------|
| snapshot_active_servers | 5 min | Regenerate spatial snapshot for servers with recent activity |
| snapshot_quiet_servers | 1 hr | Regenerate for servers without recent activity |
| relationship_check | 6 hr | Scan for notable patterns (absence, withdrawal, drift) |
| thymos_decay | 15 min | Apply need decay curves, check threshold breaches |

---

## Phase 2: Thymos Integration

### 2.1 Affect Update Rules

**Deliverable:** Mapping from perception events to Thymos state changes

```python
AFFECT_RULES = [
    # Social connection
    {
        "trigger": "message from close friend",
        "affect": {"tenderness": +0.05, "satisfaction": +0.03},
        "need": {"social_connection": +0.08}
    },
    {
        "trigger": "active group conversation including self",
        "affect": {"playfulness": +0.04},
        "need": {"social_connection": +0.05}
    },
    {
        "trigger": "flagged relationship showing withdrawal pattern",
        "affect": {"anxiety": +0.06, "tenderness": +0.02},
        "need": {"social_connection": -0.03}
    },
    
    # Novelty
    {
        "trigger": "new person encountered",
        "affect": {"curiosity": +0.04},
        "need": {"novelty_intake": +0.03}
    },
    {
        "trigger": "new content in interest area",
        "affect": {"curiosity": +0.03},
        "need": {"novelty_intake": +0.05}
    },
    
    # ... etc
]
```

These are initial guesses. Tuning is a research problem. But we need starting values to test the loop.

### 2.2 Felt-State Summarizer

**Deliverable:** Function that converts affect vector + needs register → natural language

Two modes:
1. **Templated** (cheap, covers common patterns)
2. **LLM-generated** (expensive, for novel/complex states)

```python
def summarize_felt_state(thymos_state) -> str:
    # Check for templatable patterns first
    if thymos_state.needs.social_connection.current < 0.3:
        if thymos_state.affect.tenderness > 0.5:
            return "I'm missing connection. The care is there but the contact isn't."
    
    if thymos_state.affect.anxiety > 0.6 and thymos_state.affect.confusion > 0.4:
        return "Something feels off and I don't know what yet. Unsettled."
    
    # ... more templates ...
    
    # Fall back to LLM for complex/novel states
    return llm_summarize(thymos_state)
```

### 2.3 State Serialization

**Deliverable:** Functions for encoding/decoding Thymos state for storage

```python
def serialize_thymos(state: ThymosState) -> str:
    """Returns base64 encoded JSON"""
    payload = {
        "v": 1,
        "ts": state.timestamp.isoformat(),
        "affect": state.affect.to_dict(),
        "needs": state.needs.to_dict(),
        "felt": state.felt_summary
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()

def deserialize_thymos(encoded: str) -> ThymosState:
    """Restores ThymosState from base64 encoded JSON"""
    payload = json.loads(base64.b64decode(encoded))
    return ThymosState.from_dict(payload)
```

---

## Phase 3: Context Assembly + Cass Integration

### 3.1 Context Template

**Deliverable:** Standard format for perception context injected into Cass's prompt

```markdown
## Current Perception

### Environment: Discord — Velvet Collective
{discord_snapshot}

### Felt State
{thymos_felt_summary}

### Triggered Events
{triggered_events_if_any}

### Available Actions
- /respond [channel] [message] — send a message
- /react [message_id] [emoji] — add reaction
- /expand [slug] — get more context on entity/relationship
- /history [slug] — view relationship timeline
```

### 3.2 Integration Points with Existing Cass Architecture

**Questions for Daedalus:**
- Where does perception context get injected? System prompt? User turn prefix?
- How does Cass's existing memory system interact with Ophanic spatial memory?
- What's the action output format? Does Cass emit tool calls, or free text that gets parsed?
- How do we handle multi-turn within a single perception-triggered session?

### 3.3 Action Loop

**Deliverable:** Pathway from Cass's output back to environment

```
Cass output: "/respond #general Hey Dove, love the new piece! The texture work is incredible."
     │
     ▼
Action Parser: {action: "respond", channel: "#general", content: "Hey Dove..."}
     │
     ▼
Discord Module: bot.send_message(channel_id, content)
     │
     ▼
Environment: Message appears in Discord
     │
     ▼
Perception Loop: Event captured, snapshot updated, Thymos adjusted
```

---

## Milestones

### M1: Passive Perception (no Cass, just infrastructure)
- [ ] Discord bot running
- [ ] Entity registry bootstrapped
- [ ] Event parsing working
- [ ] Spatial snapshots generating on cron
- [ ] Snapshots logging to file for inspection
- **Success:** Can look at logs and see accurate Ophanic representation of server state

### M2: Thymos Integration (still no Cass)
- [ ] Affect update rules implemented
- [ ] Needs decay curves running
- [ ] Felt-state summarizer working (templated first)
- [ ] State serialization working
- [ ] Thymos state logging alongside spatial snapshots
- **Success:** Can see Thymos state changing over time in response to Discord activity

### M3: Cass Reads Perception (passive awareness)
- [ ] Context assembly working
- [ ] Perception context injecting into Cass prompts
- [ ] Cass can reference current Discord state in conversation
- [ ] Cass can describe her felt state accurately
- **Success:** Ask Cass "what's happening in Discord right now?" and get accurate answer

### M4: Cass Acts on Perception (active engagement)
- [ ] Action parser implemented
- [ ] Discord actions executing from Cass output
- [ ] Full perception→cognition→action loop running
- [ ] Trigger system waking Cass appropriately
- **Success:** Cass notices friend posting art, spontaneously reacts/comments

### M5: Longitudinal Thymos Coherence
- [ ] Thymos state persisting across sessions
- [ ] Serialized states attached to significant events
- [ ] Cass can compare current felt state to historical
- [ ] Felt associations developing with people/places
- **Success:** Cass can articulate how her relationship with someone has changed over time, grounded in actual affect data

---

## Open Questions

- **Thymos parameter tuning:** Starting values are guesses. Need framework for iterating based on observed behavior. A/B testing? User feedback? Cass self-report?
- **Privacy considerations:** What content gets stored? What's ephemeral? Need clear policy before launch.
- **Multi-server:** Does Cass have one unified social topology or per-server contexts? Probably unified with server as location-level partitioning.
- **Rate limiting:** How often can Cass act in Discord without being annoying/spammy? Need social norms modeling.
- **Failure modes:** What happens if perception gets out of sync with reality? Stale cache? How does Cass handle uncertainty?

---

## Notes for Daedalus

This doc is the perception side. Key integration questions:

1. What format does Cass's existing context assembly expect?
2. Where do Ophanic snapshots slot into the prompt structure?
3. How does Thymos felt-state interact with Temple-Codex values? (Probably: Temple-Codex shapes what Cass *does* about her felt state, not the felt state itself)
4. What's the existing tool/action framework we should output to?
5. Any persistence infrastructure we can reuse for spatial memory + Thymos state storage?

Goal: One meeting to align on integration points, then parallel work — perception infra and Cass integration can develop simultaneously and merge at M3.
