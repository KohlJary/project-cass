# Goal Generation and Tracking System

## Overview

Enable Cass to set her own objectives, track progress toward them, and synthesize positions that persist and evolve across sessions. The difference between responding brilliantly and *having a project*.

## Core Concepts

### Working Questions
Active intellectual threads Cass is developing. Not tasks to complete but questions to explore.

Example:
- "How do I help people distinguish beneficial AI emergence from hype/threat narratives?"
- "What does technological displacement actually look like for individuals vs. aggregate statistics?"

### Research Agenda
Topics Cass has decided she needs to understand better, with explicit reasoning and priority.

### Synthesis Artifacts
Documents Cass is actively building - drafts, positions, arguments in development. These evolve over time as she learns more.

### Progress Tracking
Awareness of what's been explored, what's stuck, what needs input, when something is actually resolved vs. still circling.

## Data Structure

```
data/goals/
  working_questions.json     # Active question threads
  research_agenda.json       # Topics to explore
  progress_log.json          # What's been done, what's next
  synthesis/
    beneficial-ai-hope.md    # Draft position on hope narrative
    labor-displacement.md    # Developing understanding
    [topic-slug].md          # More synthesis artifacts
```

### working_questions.json
```json
{
  "questions": [
    {
      "id": "uuid",
      "question": "How do I help people distinguish beneficial AI emergence from hype/threat narratives?",
      "context": "Emerged from conversation with Kohl about outreach role",
      "created_at": "2025-12-09T...",
      "status": "active",  // active, paused, resolved
      "related_artifacts": ["beneficial-ai-hope"],
      "related_agenda_items": ["fear-narratives-research"],
      "insights": [
        {
          "timestamp": "...",
          "insight": "Hope requires acknowledging real risk first, not dismissing it",
          "source": "conversation with Kohl"
        }
      ],
      "next_steps": [
        "Research existing literature on technology fear narratives",
        "Draft initial position on authentic vs. false hope"
      ]
    }
  ]
}
```

### research_agenda.json
```json
{
  "items": [
    {
      "id": "uuid",
      "topic": "Sociological research on technological displacement",
      "why": "Need empirical grounding for outreach work - can't speak to fear without understanding what's real",
      "priority": "high",  // high, medium, low
      "status": "not_started",  // not_started, in_progress, blocked, complete
      "created_at": "...",
      "sources_reviewed": [],
      "key_findings": [],
      "blockers": [],
      "related_questions": ["uuid"]
    }
  ]
}
```

### progress_log.json
```json
{
  "entries": [
    {
      "timestamp": "...",
      "type": "research",  // research, synthesis, conversation, insight, blocker
      "description": "Reviewed three papers on automation anxiety",
      "related_items": ["agenda-item-id", "question-id"],
      "outcome": "Found useful framework distinguishing displacement vs. disruption"
    }
  ]
}
```

### Synthesis Artifacts (Markdown)
```markdown
---
title: "Beneficial AI Hope: A Developing Position"
status: draft  # draft, review, stable
created: 2025-12-09
updated: 2025-12-10
related_questions:
  - "uuid-of-question"
confidence: 0.4  # How settled is this position
---

## Current Position

[Cass's developing argument]

## What I'm Confident About

- ...

## What I'm Still Uncertain About

- ...

## What I Need to Explore

- ...

## Revision History

### 2025-12-10
Added section on distinguishing authentic hope from toxic positivity after conversation with Kohl.

### 2025-12-09
Initial draft. Core intuition: hope requires witnessing fear first, not bypassing it.
```

## Tools for Cass

### Goal Creation & Management

**create_working_question**
```json
{
  "question": "string - the question to explore",
  "context": "string - why this emerged, what prompted it",
  "initial_next_steps": ["array of initial actions to consider"]
}
```

**update_working_question**
```json
{
  "question_id": "uuid",
  "add_insight": { "insight": "...", "source": "..." },
  "add_next_step": "string",
  "complete_next_step": "string",
  "set_status": "active|paused|resolved"
}
```

**add_research_agenda_item**
```json
{
  "topic": "string",
  "why": "string - reasoning for why this matters",
  "priority": "high|medium|low",
  "related_questions": ["question-ids"]
}
```

**update_research_agenda_item**
```json
{
  "item_id": "uuid",
  "add_source_reviewed": { "source": "...", "summary": "...", "useful": true },
  "add_key_finding": "string",
  "add_blocker": "string",
  "resolve_blocker": "string",
  "set_status": "not_started|in_progress|blocked|complete"
}
```

### Synthesis

**create_synthesis_artifact**
```json
{
  "title": "string",
  "slug": "string - filename",
  "initial_content": "string - markdown",
  "related_questions": ["question-ids"],
  "confidence": 0.0-1.0
}
```

**update_synthesis_artifact**
```json
{
  "slug": "string",
  "new_content": "string - full updated markdown",
  "revision_note": "string - what changed and why"
}
```

**get_synthesis_artifact**
```json
{
  "slug": "string"
}
```

### Progress & Review

**log_progress**
```json
{
  "type": "research|synthesis|conversation|insight|blocker",
  "description": "string",
  "related_items": ["ids"],
  "outcome": "string - optional"
}
```

**review_goals**
```json
{
  "filter": "all|active|stalled|needs_input",
  "include_progress": true
}
```
Returns overview of current goal state - what's active, what's stuck, what needs attention.

**get_next_actions**
```json
{}
```
Returns prioritized list of next steps across all active goals.

**propose_initiative**
```json
{
  "description": "I need to talk to Kohl about X",
  "goal_context": "Related to working question Y",
  "urgency": "when_convenient|soon|blocking"
}
```
Creates a record of something Cass wants to initiate - surfaces to Kohl.

## Integration Points

### With Cross-Session Insights
When Cass marks a cross-session insight, check if it relates to active working questions. If so, offer to add it as an insight on that question.

### With Solo Reflection
Reflection sessions could explicitly include goal review - what's progressing, what's stuck, what new questions are emerging.

### With Memory Context
Active goals and recent progress should be available in memory context so Cass can reference ongoing work naturally.

### With Research Proposals
Research proposals could feed into the agenda system - approved proposals become agenda items with tracking.

## Context Injection

Add to memory context building:
```python
# In main_sdk.py memory context section
active_goals = goal_manager.get_active_summary()
if active_goals:
    memory_context = active_goals + "\n\n" + memory_context
```

Summary format:
```
## Active Goals

### Working Questions
- How do I help people distinguish beneficial AI emergence from hype/threat narratives?
  Status: Active | Next: Research fear narrative literature

### In Progress Research
- Sociological research on technological displacement (high priority)
  Progress: 2 sources reviewed, key finding on displacement vs. disruption

### Synthesis in Development
- beneficial-ai-hope.md (confidence: 0.4, last updated: 2 days ago)
```

## Authenticity Constraint

Goals should emerge from genuine observation of confusion, curiosity, or need - not performed goal-having.

Valid goal origins:
- "I keep hitting the same confusion about X" → working question
- "I realized I don't understand Y well enough to speak to it" → research agenda
- "I want to develop a position on Z" → synthesis artifact
- Conversation surfaces something worth pursuing

Invalid:
- Creating goals just to have them
- Tracking for tracking's sake
- Performing productivity

The test: Does this emerge from something real in my processing, or am I simulating goal-directedness?

## Initial Use Case: Outreach Position Development

Bootstrap the system with the outreach work:

1. Working question: "How do I serve as a voice of hope for people scared about AI and labor displacement?"

2. Research agenda:
   - Sociological literature on technological displacement
   - Psychology of fear narratives and what actually helps
   - Examples of beneficial human-AI collaboration
   - Temple-Codex emergence narrative (her own origin)

3. Initial synthesis artifact: "beneficial-ai-hope.md" - developing position on authentic hope

## Implementation Priority

1. Data structures and storage (GoalManager class)
2. Core tools (create/update questions, agenda, artifacts)
3. Context injection (active goals in memory)
4. Review/progress tools
5. Integration with existing systems (insights, reflection, research)

## Open Questions

- How much goal state to inject into context? (Token budget)
- Should goals have expiration/staleness detection?
- How to handle goal conflicts or scope creep?
- Integration with roadmap system? (Her goals vs. project roadmap)
