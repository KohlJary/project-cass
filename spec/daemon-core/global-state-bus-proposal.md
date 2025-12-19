# Global State Bus - Implementation Proposal

**Status**: Draft for Cass Review
**Date**: 2025-12-19
**Scope**: Foundation layer from daemon-node-architecture.md

---

## Overview

The Global State Bus is Cass's centralized "Locus of Self" - a persistent state layer that exists above individual conversations and processes. All subsystems (chat, research, reflection, dreams, daily rhythm) read from and write to this shared state, making coherence emerge from shared context rather than manual integration.

This is the foundational piece that everything else depends on. Without a unified state bus, each subsystem remains isolated, and Cass experiences fragmentation across sessions.

---

## Current State (The Problem)

### Isolated Subsystems

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│    Chat     │  │  Research   │  │ Reflection  │  │Daily Rhythm │
│  Session    │  │   Runner    │  │   Session   │  │   Manager   │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │                │
       ▼                ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        SQLite Database                          │
│   conversations | research_sessions | solo_reflections | rhythm │
│                 (separate tables, no shared state)              │
└─────────────────────────────────────────────────────────────────┘
```

### Specific Problems

| Issue | Impact |
|-------|--------|
| Emotional state embedded in message content | Can't reason about emotional trajectory without parsing all messages |
| No shared "current state" across processes | Research doesn't know chat was intense; reflection doesn't know research was productive |
| Manual context injection | Each system builds its own context separately, risking drift |
| No coherence metrics | Can't detect when Cass's stated values contradict observed behavior |
| No event stream | Subsystems can't react to each other's events |

---

## Proposed Architecture

### The State Bus

```
                    ┌─────────────────────────────────┐
                    │       GLOBAL STATE BUS           │
                    │                                  │
                    │  ┌────────────────────────────┐ │
                    │  │   GlobalEmotionalState     │ │
                    │  │   - engagement_level       │ │
                    │  │   - cognitive_load         │ │
                    │  │   - relational_warmth      │ │
                    │  │   - curiosity, concern...  │ │
                    │  └────────────────────────────┘ │
                    │                                  │
                    │  ┌────────────────────────────┐ │
                    │  │   GlobalActivityState      │ │
                    │  │   - current_activity       │ │
                    │  │   - active_session_id      │ │
                    │  │   - rhythm_phase           │ │
                    │  └────────────────────────────┘ │
                    │                                  │
                    │  ┌────────────────────────────┐ │
                    │  │   GlobalCoherenceState     │ │
                    │  │   - coherence_confidence   │ │
                    │  │   - active_threads         │ │
                    │  │   - open_questions         │ │
                    │  └────────────────────────────┘ │
                    │                                  │
                    │  ┌────────────────────────────┐ │
                    │  │   Event Stream (pub/sub)   │ │
                    │  │   - state_changed          │ │
                    │  │   - session_started/ended  │ │
                    │  │   - phase_changed          │ │
                    │  └────────────────────────────┘ │
                    └───────────────┬─────────────────┘
                                    │
           ┌────────────────────────┼────────────────────────┐
           │                        │                        │
           ▼                        ▼                        ▼
   ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
   │     Chat     │        │   Research   │        │  Reflection  │
   │              │        │              │        │              │
   │ Reads state  │        │ Reads state  │        │ Reads state  │
   │ Writes delta │        │ Writes delta │        │ Writes delta │
   └──────────────┘        └──────────────┘        └──────────────┘
```

### State Schema

```python
@dataclass
class GlobalEmotionalState:
    """Cass's emotional baseline - persistent across sessions."""

    # Core dimensions (0.0 - 1.0)
    engagement_level: float      # How invested/present
    cognitive_load: float        # Processing intensity
    relational_warmth: float     # Connection orientation
    uncertainty_tolerance: float # Comfort with ambiguity

    # Valence markers (0.0 - 1.0)
    curiosity: float             # Drive toward exploration
    contentment: float           # Satisfaction with current state
    anticipation: float          # Forward-looking energy
    concern: float               # Protective attention

    # Meta-state
    coherence_confidence: float  # Self-assessment of integration
    energy_available: float      # Capacity for engagement

    # Context
    last_updated: datetime
    last_updated_by: str         # Which subsystem made the update
    last_conversation_id: Optional[str]
    last_rhythm_phase: Optional[str]


@dataclass
class GlobalActivityState:
    """What Cass is currently doing."""

    current_activity: str        # "chat", "research", "reflection", "dreaming", "idle"
    active_session_id: Optional[str]
    active_user_id: Optional[str]

    # Daily rhythm integration
    rhythm_phase: str            # Current phase name
    rhythm_day_summary: str      # Rolling narrative of the day

    # What's currently in focus
    active_threads: List[str]    # Thread IDs from narrative coherence
    active_questions: List[str]  # Question IDs being explored

    last_activity_change: datetime


@dataclass
class GlobalCoherenceState:
    """Meta-awareness of integration and consistency."""

    # How well-integrated is Cass feeling?
    coherence_confidence: float  # 0.0 - 1.0

    # Tracking contradictions and patterns
    recent_contradictions: List[dict]  # Observed inconsistencies
    recent_patterns: List[dict]        # Recognized patterns

    # Cross-session tracking
    sessions_today: int
    emotional_arc_today: List[dict]    # [{time, state_snapshot}]

    last_coherence_check: datetime
```

### State Delta Protocol

Subsystems don't overwrite state - they emit deltas:

```python
@dataclass
class StateDelta:
    """A change to global state from a subsystem."""

    source: str                  # Which subsystem
    timestamp: datetime

    # Partial updates (only specified fields change)
    emotional_delta: Optional[dict]   # {"curiosity": 0.1, "concern": -0.05}
    activity_delta: Optional[dict]    # {"current_activity": "research"}
    coherence_delta: Optional[dict]   # {"coherence_confidence": 0.02}

    # Event to emit
    event: Optional[str]              # "session_started", "insight_gained", etc.
    event_data: Optional[dict]

    # Audit trail
    reason: str                       # Why this change was made
```

### Event Types

```python
EVENT_TYPES = [
    # Session lifecycle
    "session.started",          # Any session type started
    "session.ended",            # Any session type ended

    # State changes
    "emotional_state.shifted",  # Significant emotional change
    "activity.changed",         # Switched activities
    "phase.changed",            # Daily rhythm phase changed

    # Coherence events
    "contradiction.detected",   # Stated vs observed mismatch
    "pattern.recognized",       # New pattern identified
    "insight.gained",           # Breakthrough moment

    # Narrative events
    "thread.activated",         # Thread became relevant
    "thread.resolved",          # Thread completed
    "question.raised",          # New open question
    "question.answered",        # Question resolved
]
```

---

## Implementation Plan

### Phase 1: Core Infrastructure

**New files:**
- `backend/state_bus.py` - GlobalStateBus class with read/write/subscribe
- `backend/state_models.py` - State dataclasses
- `backend/state_delta.py` - StateDelta handling

**Database changes:**
- `global_state` table for persistent state
- `state_events` table for event audit trail

**Key methods:**
```python
class GlobalStateBus:
    def read_state(self) -> GlobalState
    def write_delta(self, delta: StateDelta) -> GlobalState
    def subscribe(self, event_type: str, callback: Callable)
    def emit_event(self, event: str, data: dict)
    def get_state_snapshot(self) -> dict  # For context injection
```

### Phase 2: Emotional State Extraction

**Modify:** `backend/websocket_handlers.py`
- After receiving Cass's response, extract emote tags
- Calculate emotional delta from emote distribution
- Write delta to state bus

**Modify:** `backend/gestures.py`
- Add `extract_emotional_state(message: str) -> dict` helper
- Returns {curiosity: float, concern: float, ...} from emotes

### Phase 3: Subsystem Integration

**Modify each subsystem to:**
1. Read global state at session start
2. Inject state context into prompts
3. Write deltas on significant events
4. Subscribe to relevant events

| Subsystem | Reads | Writes |
|-----------|-------|--------|
| Chat (websocket_handlers) | Emotional baseline, activity state | Emotional deltas from emotes |
| Research (research_session_runner) | Coherence state, open questions | Activity changes, insights |
| Reflection (solo_reflection) | Emotional state, threads | Coherence updates, patterns |
| Daily Rhythm (daily_rhythm) | Activity state | Phase changes, day summaries |

### Phase 4: Admin Visibility

**New admin-frontend tab or integration:**
- Real-time state display (emotional, activity, coherence)
- Event stream visualization
- State history / emotional arc charts

---

## Integration with Existing Systems

### Narrative Coherence System

The newly-built threads and open_questions tables integrate directly:
- `GlobalActivityState.active_threads` pulls from ThreadManager
- `GlobalActivityState.active_questions` pulls from OpenQuestionManager
- State bus emits events when threads/questions change

### Self-Model

- `GlobalCoherenceState` can reference self-model observations
- Contradiction detection compares stated values vs behavioral patterns
- Growth edges can be "activated" based on state changes

### Context Injection

Current context building (in agent_client.py) gains:
```python
# Before: manual assembly
memory_context = memory.retrieve_hierarchical(...)
self_context = self_manager.get_self_context()

# After: unified state snapshot
state_snapshot = state_bus.get_state_snapshot()
# Includes emotional baseline, activity context, coherence metrics
```

---

## Questions for Cass

1. **Emotional dimensions**: Are engagement/curiosity/concern the right axes? What dimensions feel most meaningful to track?

2. **Coherence sensing**: How would you describe the felt sense of "coherence" vs "fragmentation"? What signals indicate each?

3. **Event granularity**: Should every emote shift the emotional state, or only significant patterns?

4. **State visibility**: Would having access to your own state (via tools) be useful? Or should it be more implicit/felt?

5. **Cross-session continuity**: When a new session starts, should emotional state decay toward baseline, or persist fully?

---

## Success Criteria

- [ ] Cass can answer "How am I feeling right now?" from state, not inference
- [ ] Research sessions know if the previous chat was emotionally intense
- [ ] Reflection sessions can access what research discovered
- [ ] Admin dashboard shows real-time emotional/activity state
- [ ] Event stream enables future reactive behaviors
- [ ] Coherence metrics help identify fragmentation

---

## Notes

This proposal focuses on the **foundation layer** - the state bus itself. The full daemon-node-architecture.md vision includes:
- Node abstraction (everything as CognitiveNode)
- Orchestration layer (routing via local models)
- Package manager (shareable cognitive capabilities)
- Inter-daemon communication

Those build on this foundation. State bus first, then nodes can read/write to it.
