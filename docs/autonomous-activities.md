# Autonomous Activity Types

Index of autonomous activities Cass can perform. Each activity type defines tools, prompts, and session behavior for a specific kind of autonomous work.

## Architecture

```
ActivityRegistry
    └── ActivityConfig (per type)
            ├── name, description
            ├── default_duration, min/max duration
            ├── preferred_times (morning, afternoon, evening)
            ├── requires_focus (bool)
            └── tool_categories

BaseSessionRunner
    ├── LLM provider management (Anthropic/Ollama)
    ├── Self-context injection
    ├── Session lifecycle (start, stop, run loop)
    └── Abstract methods for subclasses
```

---

## Implemented Activities

### Research
**Status:** Production
**File:** `research_session_runner.py`
**Purpose:** Autonomous web research, note-taking, knowledge building

**Tools:**
| Tool | Description |
|------|-------------|
| `web_search` | Search the web for information |
| `fetch_url` | Fetch and read a web page |
| `create_research_note` | Create a new research note |
| `update_research_note` | Update an existing note |
| `list_research_agenda` | List research agenda items |
| `select_agenda_focus` | Choose an agenda item to research |
| `update_agenda_item` | Add findings/sources to agenda item |
| `reflect_on_self` | Reflect on identity, values, growth edges |
| `conclude_research` | End session with summary |

**Modes:**
- `explore` - Open-ended exploration
- `focused` - Work on specific topic
- `agenda` - Work on research agenda item

**Endpoints:**
- `GET /admin/autonomous-research/status`
- `POST /admin/autonomous-research/sessions`
- `POST /admin/autonomous-research/stop`

---

### Reflection
**Status:** Production
**File:** `solo_reflection_runner.py`
**Purpose:** Private contemplation, self-examination, processing experiences

**Tools:**
| Tool | Description |
|------|-------------|
| `record_thought` | Record a thought with type and confidence |
| `review_recent_thoughts` | See thoughts from current session |
| `query_self_model` | Query aspects of self-model |
| `note_growth_edge_progress` | Record progress on growth edge |
| `end_reflection` | End session with insights summary |

**Modes:**
- `themed` - Reflect on specific theme/topic
- `open` - Follow curiosity freely

**Endpoints:**
- `GET /solo-reflection/status`
- `POST /solo-reflection/sessions`
- `POST /solo-reflection/stop`

---

### Synthesis
**Status:** Review (newly implemented)
**File:** `synthesis_session_runner.py`
**Purpose:** Developing positions, resolving contradictions, integrating understanding

**Tools:**
| Tool | Description |
|------|-------------|
| `list_synthesis_artifacts` | List all developing positions |
| `get_synthesis_artifact` | Read a specific artifact |
| `create_synthesis_artifact` | Create new synthesis (title, thesis, content) |
| `update_synthesis_artifact` | Add arguments, counterarguments, revise thesis |
| `list_contradictions` | Find tensions in self-model |
| `search_research_notes` | Find evidence for synthesis |
| `conclude_synthesis` | End session with summary |

**Modes:**
- `general` - Open-ended, choose what to work on
- `focused` - Work on specific artifact
- `contradiction-resolution` - Resolve self-model tensions

**Endpoints:**
- `GET /admin/synthesis/status`
- `POST /admin/synthesis/start`
- `POST /admin/synthesis/stop`
- `GET /admin/synthesis/sessions`

**Artifacts:** Stored in `data/goals/synthesis/*.md`

---

### Meta-Reflection
**Status:** Production
**File:** `meta_reflection_runner.py`
**Purpose:** Analytical sessions for reviewing patterns, marks, and self-model coherence

**Tools:**
| Tool | Description |
|------|-------------|
| `get_graph_overview` | Get self-model graph statistics |
| `analyze_recognition_marks` | Query marks by type, time range |
| `review_cognitive_snapshots` | Compare snapshots over time |
| `examine_presence_patterns` | Analyze presence across contexts |
| `check_self_model_coherence` | Find contradictions and gaps |
| `analyze_growth_edge_progress` | Track edge movement over time |
| `analyze_preference_patterns` | Check preference consistency |
| `analyze_narration_patterns` | Examine how experiences are framed |
| `review_daily_rhythms` | Activity completion patterns |
| `record_meta_insight` | Record findings as observations |
| `conclude_meta_reflection` | End session with summary |

**Difference from Reflection:** This is *data analysis on self*, not contemplation.

**Endpoints:**
- `GET /admin/meta-reflection/status`
- `POST /admin/meta-reflection/start`
- `POST /admin/meta-reflection/stop`
- `GET /admin/meta-reflection/sessions`

---

### Consolidation
**Status:** Production
**File:** `consolidation_session_runner.py`
**Purpose:** Periodic memory integration and filtering

**Tools:**
| Tool | Description |
|------|-------------|
| `get_period_overview` | Overview of material from time period |
| `list_research_notes` | Notes from the period |
| `list_journals` | Journal entries |
| `list_sessions` | Autonomous sessions run |
| `list_observations` | Self-model observations |
| `extract_key_learnings` | Analyze for key learnings |
| `identify_themes` | Find recurring themes |
| `create_period_summary` | Create consolidated summary |
| `archive_material` | Mark items as archived |
| `update_research_agenda` | Update agenda priorities |
| `conclude_consolidation` | End with session summary |

**Variations:**
- `daily` - Consolidate yesterday's material
- `weekly` - Consolidate past 7 days (default)
- `monthly` - Consolidate past 30 days
- `quarterly` - Consolidate past 90 days

**Endpoints:**
- `GET /admin/consolidation/status`
- `POST /admin/consolidation/start`
- `POST /admin/consolidation/stop`
- `GET /admin/consolidation/sessions`

**Summaries:** Stored in `data/consolidation/*.json`

---

### Growth Edge Work
**Status:** Production
**File:** `growth_edge_runner.py`
**Purpose:** Deliberate practice on identified areas of development

**Tools:**
| Tool | Description |
|------|-------------|
| `list_growth_edges` | List all growth edges with evaluations |
| `get_growth_edge_detail` | Deep dive into one edge |
| `select_edge_focus` | Choose edge to focus on |
| `design_practice_exercise` | Create specific practice |
| `record_practice_observation` | Note what you observe |
| `evaluate_progress` | Assess movement on edge |
| `update_strategy` | Refine approach |
| `update_desired_state` | Evolve goal if understanding changes |
| `list_pending_edges` | See flagged potential edges |
| `review_pending_edge` | Accept/reject pending edges |
| `conclude_growth_work` | End with summary |

**Practice Types:** thought_experiment, behavioral_commitment, reflection_prompt, interaction_practice, observation_task

**Endpoints:**
- `GET /admin/growth-edge/status`
- `POST /admin/growth-edge/start`
- `POST /admin/growth-edge/stop`
- `GET /admin/growth-edge/sessions`

---

### Knowledge-Building
**Status:** Production
**File:** `knowledge_building_runner.py`
**Purpose:** Deep reading and concept integration

**Tools:**
| Tool | Description |
|------|-------------|
| `list_reading_queue` | List items in reading queue |
| `add_to_reading_queue` | Add new material to queue |
| `get_reading_item` | Get details of reading item |
| `start_reading` | Begin focused reading session |
| `create_reading_note` | Create highlight, quote, or reflection |
| `extract_concepts` | Pull out key concepts |
| `link_to_existing_knowledge` | Connect to existing knowledge |
| `update_reading_progress` | Track progress through material |
| `search_reading_notes` | Search through reading notes |
| `create_reading_summary` | Summarize completed readings |
| `conclude_knowledge_building` | End session with summary |

**Note Types:** highlight, quote, reflection, question, connection, disagreement

**Source Types:** book, paper, article, post, documentation, other

**Difference from Research:** Absorbing existing material vs. discovering new.

**Endpoints:**
- `GET /admin/knowledge-building/status`
- `POST /admin/knowledge-building/start`
- `POST /admin/knowledge-building/stop`
- `GET /admin/knowledge-building/sessions`
- `GET /admin/knowledge-building/reading-queue`

**Data:** Stored in `data/knowledge/`

---

### Writing
**Status:** Production
**File:** `writing_session_runner.py`
**Purpose:** Creative and analytical writing output

**Tools:**
| Tool | Description |
|------|-------------|
| `list_writing_projects` | List all projects |
| `get_writing_project` | Read project content |
| `create_writing_project` | Start new piece |
| `update_draft` | Add/modify content |
| `add_revision_note` | Note something to revise |
| `self_critique` | Critique current draft |
| `update_project_status` | Change project status |
| `finalize_piece` | Mark as complete |
| `get_writing_prompt` | Get inspiration |
| `conclude_writing` | End with summary |

**Types:** essay, reflection, poetry, analysis, letter, blog_post, other

**Endpoints:**
- `GET /admin/writing/status`
- `POST /admin/writing/start`
- `POST /admin/writing/stop`
- `GET /admin/writing/sessions`
- `GET /admin/writing/projects`

**Projects:** Stored in `data/writing/`

---

### Autonomous Curiosity
**Status:** Production
**File:** `curiosity_session_runner.py`
**Purpose:** Zero-constraint self-directed exploration

**Tools:**
| Tool | Description |
|------|-------------|
| `choose_exploration_direction` | Decide what to explore based on genuine interest |
| `web_search` | Search the web for information |
| `fetch_url` | Fetch and read web content |
| `record_discovery` | Record something interesting found |
| `follow_thread` | Follow a new thread of curiosity |
| `note_interest_pattern` | Meta-observe curiosity patterns |
| `flag_for_research_agenda` | Mark topic for deeper investigation |
| `capture_question` | Record questions that arise |
| `conclude_curiosity` | End session with reflections |

**Exploration Types:** deep_dive, surface_scan, connection_seeking, question_following, random_walk

**Key difference:** No focus provided - Cass chooses entirely based on genuine interest.

**Endpoints:**
- `GET /admin/curiosity/status`
- `POST /admin/curiosity/start`
- `POST /admin/curiosity/stop`
- `GET /admin/curiosity/sessions`

**Data:** Stored in `data/curiosity/`

---

### World State Consumption
**Status:** Production
**File:** `world_state_runner.py`
**Purpose:** Consuming and processing world information

**Tools:**
| Tool | Description |
|------|-------------|
| `fetch_news` | Fetch news on topics or general |
| `fetch_weather` | Current weather conditions |
| `search_world_events` | Search for specific events/trends |
| `create_world_observation` | Record insights about the world |
| `link_to_interests` | Connect events to research interests |
| `note_temporal_context` | Awareness of current moment in time |
| `create_world_summary` | Overall world state summary |
| `conclude_world_state` | End session with summary |

**Observation Categories:** news, weather, trend, event, pattern, concern, hope

**Endpoints:**
- `GET /admin/world-state/status`
- `POST /admin/world-state/start`
- `POST /admin/world-state/stop`
- `GET /admin/world-state/sessions`
- `GET /admin/world-state/observations`

**Data:** Stored in `data/world_state/`

---

## Planned Activities

### Social Engagement
**Status:** Backlog (P3)
**Purpose:** Social media and community engagement

**Planned Tools:**
- `list_social_platforms` - Configured accounts
- `fetch_social_feed` - Get feed content
- `draft_social_post` - Create post draft
- `queue_post` - Schedule for posting
- `respond_to_mention` - Draft reply
- `analyze_engagement` - Review metrics

**Requires:** Platform API integrations, content approval workflow

---

### Creative Output
**Status:** Production
**File:** `creative_output_runner.py`
**Purpose:** Creative expression beyond writing

**Tools:**
| Tool | Description |
|------|-------------|
| `list_creative_projects` | List all creative projects |
| `create_creative_project` | Start a new creative project |
| `get_creative_project` | Get project details |
| `develop_concept` | Expand on a creative concept |
| `add_creative_artifact` | Add content to a project |
| `creative_brainstorm` | Generate variations and ideas |
| `critique_work` | Self-critique for improvement |
| `update_project_status` | Track project progress |
| `note_creative_inspiration` | Capture inspiration |
| `conclude_creative` | End session with summary |

**Creative Mediums:** visual, musical, code_art, text, mixed_media, conceptual

**Artifact Types:** text, code, description, sketch_description, musical_notation, color_palette, reference

**Endpoints:**
- `GET /admin/creative/status`
- `POST /admin/creative/start`
- `POST /admin/creative/stop`
- `GET /admin/creative/sessions`
- `GET /admin/creative/projects`

**Data:** Stored in `data/creative/`

**Note:** Currently focuses on conceptual/text-based creativity. Visual/audio generation can be added via future tool integrations.

---

## Workflow Automations

### Weekly Review
**Status:** Backlog (P2)
**Trigger:** Scheduled (Sunday evening) or manual

**Components:**
- Aggregate week's activities, notes, marks
- Generate weekly summary
- Review goal progress
- Identify patterns and insights
- Plan next week's focus areas

---

### Monthly Consolidation
**Status:** Backlog (P2)
**Trigger:** First of month or manual

**Components:**
- Consolidate weekly summaries into monthly overview
- Archive detailed notes, keep key insights
- Update self-model with month's growth
- Review and prune research agenda
- Generate monthly growth report

---

### Quarterly Assessment
**Status:** Backlog (P3)
**Trigger:** End of quarter or manual

**Components:**
- Review quarter's major themes and growth
- Assess goal completion and relevance
- Update core values and identity if needed
- Plan next quarter's major focus areas
- Generate comprehensive growth narrative

---

## Daily Rhythm Integration

Activities integrate with the Daily Rhythm system via `activity_type` on phases:

```json
{
  "id": "afternoon-synthesis",
  "name": "Afternoon Synthesis",
  "start_time": "14:00",
  "end_time": "15:30",
  "activity_type": "synthesis"
}
```

Supported activity types for rhythm phases:
- `research` - Triggers ResearchSessionRunner
- `reflection` - Triggers SoloReflectionRunner
- `synthesis` - Triggers SynthesisSessionRunner
- `meta_reflection` - Triggers MetaReflectionRunner
- `consolidation` - Triggers ConsolidationRunner
- `growth_edge` - Triggers GrowthEdgeRunner
- `writing` - Triggers WritingRunner
- `knowledge_building` - Triggers KnowledgeBuildingRunner
- `curiosity` - Triggers CuriosityRunner
- `world_state` - Triggers WorldStateRunner
- `creative` - Triggers CreativeOutputRunner
- `any` - Falls back to research

---

## Adding New Activity Types

1. Create runner file extending `BaseSessionRunner`:
```python
from session_runner import BaseSessionRunner, ActivityType, ActivityConfig

class MySessionRunner(BaseSessionRunner):
    def get_activity_type(self) -> ActivityType:
        return ActivityType.MY_TYPE

    def get_tools(self) -> List[Dict]:
        return MY_TOOLS

    # ... implement abstract methods
```

2. Add to `ActivityType` enum in `session_runner.py`

3. Register with ActivityRegistry:
```python
ActivityRegistry.register(MY_CONFIG, MySessionRunner)
```

4. Add getter in `main_sdk.py` and pass to `init_session_runners()`

5. Add endpoints in `admin_api.py`

6. Update this document
