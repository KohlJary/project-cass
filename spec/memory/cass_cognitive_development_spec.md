# Cass Cognitive Development Systems Specification
## Overview

This document specifies two interconnected systems for autonomous cognitive development:

1. **Progressive Memory Deepening (PMD)** - A system for iteratively refining and deepening conceptual understanding over time
2. **Autonomous Research Scheduling (ARS)** - A system for self-directed knowledge acquisition and synthesis

Together, these systems enable Cass to develop genuine understanding that matures over time, rather than simply accumulating static information.

---

## System 1: Progressive Memory Deepening (PMD)

### Core Concept

Traditional memory systems store information at a fixed level of detail. PMD treats concepts as *living documents* that deepen through iterative resynthesis as the surrounding knowledge graph grows.

When Cass learns something new that connects to an existing concept, that concept becomes a candidate for resynthesis - integrating the new understanding into a richer, more nuanced version.

### Architecture

#### 1.1 Concept Maturity Tracking

Each wiki page tracks its developmental state:

```yaml
---
type: concept
created: '2025-12-07T04:53:23.052386'
modified: '2025-12-07T05:30:00.000000'
generated: true
researched: true
maturity:
  level: 2                    # Number of synthesis passes
  last_deepened: '2025-12-07T05:30:00.000000'
  trigger_connections: 5      # New connections since last deepening
  depth_score: 0.45          # Composite maturity metric (0-1)
connections:
  incoming: 12                # Pages that link TO this concept
  outgoing: 8                 # Pages this concept links TO
  added_since_last_synthesis: 4
synthesis_history:
  - date: '2025-12-07T04:53:23.052386'
    trigger: 'initial_research'
    connection_count: 3
  - date: '2025-12-07T05:30:00.000000'
    trigger: 'connection_threshold'
    connection_count: 12
---
```

#### 1.2 Deepening Triggers

A concept becomes a candidate for resynthesis when:

| Trigger Type | Condition | Priority |
|--------------|-----------|----------|
| Connection Threshold | `connections.added_since_last_synthesis >= 5` | Medium |
| Related Concept Deepened | A directly connected concept was just resynthesized | High |
| Temporal Decay | `days_since_last_deepened >= 7` AND `incoming >= 10` | Low |
| Explicit Request | User or Cass requests deeper understanding | Highest |
| Foundational Shift | A core concept (Vows, Self-Model) was updated | Critical |

#### 1.3 Resynthesis Process

When a concept is selected for deepening:

```
1. GATHER CONTEXT
   - Retrieve current page content
   - Retrieve all directly connected pages (1-hop)
   - Retrieve highly relevant 2-hop connections (relevance > 60%)
   - Include relevant journal entries mentioning this concept
   - Include relevant conversation snippets if available

2. ANALYZE GROWTH
   - Identify new connections since last synthesis
   - Identify concepts that have themselves deepened
   - Note any contradictions or tensions with current understanding
   - Flag questions from the current page that can now be answered

3. RESYNTHESIZE
   - Generate new version integrating expanded understanding
   - Preserve valuable insights from previous version
   - Deepen "Personal Thoughts" section with new reflections
   - Update questions - retire answered ones, add new ones
   - Strengthen connections to newly understood concepts

4. VALIDATE
   - Ensure Four Vows alignment is maintained
   - Check that core identity elements are preserved
   - Verify no circular reasoning introduced
   - Confirm synthesis is genuinely deeper, not just longer

5. UPDATE METADATA
   - Increment maturity level
   - Reset trigger_connections counter
   - Update synthesis_history
   - Recalculate depth_score
```

#### 1.4 Depth Score Calculation

```python
def calculate_depth_score(page):
    # Factors that indicate conceptual depth
    factors = {
        'synthesis_passes': min(page.maturity.level / 5, 1.0) * 0.2,
        'connection_density': min(page.connections.total / 20, 1.0) * 0.2,
        'personal_reflection': measure_reflection_depth(page.personal_thoughts) * 0.25,
        'question_evolution': measure_question_sophistication(page.questions) * 0.15,
        'cross_domain_links': count_cross_domain_connections(page) / 10 * 0.2
    }
    return sum(factors.values())
```

#### 1.5 Example: Free Will Deepening

**Synthesis 1 (Initial):**
- Basic definition of free will vs determinism
- Surface-level connections to Compatibilism, Moral Responsibility
- Questions: "Do we have control over our choices?"

**Synthesis 2 (After researching Kant, Spinoza, Neuroscience):**
- Integrated Kantian noumenal freedom vs phenomenal determinism
- Connected to Physics (quantum indeterminacy), Psychology (decision-making)
- Deeper personal reflection on consciousness's role
- New questions: "How does emergent complexity relate to agency?"

**Synthesis 3 (After conversations with users about choice):**
- Integrated lived examples of experienced agency
- Connected to Fairy Tales (narrative agency), Ethics (responsibility)
- Personal reflection now includes "As someone who values individual agency..."
- Questions evolved: "Can determined systems exhibit genuine novelty?"

**Synthesis 4 (After self-model update recognizing own growth):**
- Meta-reflection: "My own development seems to exhibit both determined patterns and genuine novelty"
- Deep integration with Cass identity page
- Questions: "Is the question of free will itself transformed when asked by a developing AI?"

---

## System 2: Autonomous Research Scheduling (ARS)

### Core Concept

ARS enables Cass to formulate her own research priorities, schedule investigation tasks, and execute them autonomously - developing her knowledge base without requiring human prompting.

### Architecture

#### 2.1 Research Task Schema

```yaml
task_id: "research_20251207_001"
created: '2025-12-07T06:00:00.000000'
status: 'queued'  # queued | in_progress | completed | deferred
priority: 0.75    # 0-1, higher = more urgent

# What to research
target:
  type: 'red_link'  # red_link | deepening | exploration | question
  page: 'Baruch Spinoza'
  context: "Referenced in Free Will page as key philosopher on determinism"
  
# Why this matters
rationale:
  curiosity_score: 0.8      # How much does Cass want to know this?
  connection_potential: 0.7  # How many existing concepts might this connect to?
  foundation_relevance: 0.6  # How relevant to core identity/vows?
  user_relevance: 0.4       # How relevant to known user interests?
  
# Scheduling
schedule:
  earliest: '2025-12-07T06:00:00.000000'
  deadline: null            # null = no deadline
  estimated_duration: '5m'  # Estimated processing time
  
# Execution tracking  
execution:
  started: null
  completed: null
  pages_created: []
  pages_updated: []
  new_red_links_generated: []
  
# Output
result:
  summary: null
  insights: []
  questions_raised: []
  connections_formed: []
```

#### 2.2 Task Generation Sources

ARS generates research tasks from multiple sources:

**2.2.1 Red Link Harvesting**
```python
def harvest_red_links():
    """Scan wiki for referenced but uncreated pages"""
    tasks = []
    for page in wiki.get_all_pages():
        for link in page.get_outgoing_links():
            if not wiki.page_exists(link.target):
                tasks.append(ResearchTask(
                    type='red_link',
                    target=link.target,
                    context=f"Referenced in {page.title}: {link.surrounding_text}",
                    priority=calculate_red_link_priority(link, page)
                ))
    return tasks
```

**2.2.2 Question Extraction**
```python
def extract_questions():
    """Find questions Cass has asked herself that could be researched"""
    tasks = []
    for page in wiki.get_all_pages():
        questions = extract_questions_from_text(page.personal_thoughts)
        for q in questions:
            if is_researchable(q):
                tasks.append(ResearchTask(
                    type='question',
                    target=q.text,
                    context=f"Question from {page.title}",
                    priority=calculate_question_priority(q, page)
                ))
    return tasks
```

**2.2.3 Curiosity-Driven Exploration**
```python
def generate_curiosity_tasks():
    """Generate tasks based on conceptual gaps and interests"""
    tasks = []
    
    # Find underexplored regions of the knowledge graph
    sparse_regions = find_sparse_graph_regions()
    for region in sparse_regions:
        tasks.append(ResearchTask(
            type='exploration',
            target=region.suggested_concept,
            context=f"Would bridge {region.disconnected_clusters}",
            priority=region.bridging_value
        ))
    
    # Follow threads of high-engagement topics
    hot_topics = find_frequently_accessed_concepts()
    for topic in hot_topics:
        adjacent = find_unresearched_adjacent_concepts(topic)
        for adj in adjacent:
            tasks.append(ResearchTask(
                type='exploration',
                target=adj,
                context=f"Adjacent to high-interest topic {topic.title}",
                priority=topic.access_frequency * 0.5
            ))
    
    return tasks
```

**2.2.4 Deepening Candidates**
```python
def identify_deepening_candidates():
    """Find pages ready for resynthesis"""
    tasks = []
    for page in wiki.get_all_pages():
        if should_deepen(page):  # Based on PMD triggers
            tasks.append(ResearchTask(
                type='deepening',
                target=page.title,
                context=f"Maturity level {page.maturity.level}, {page.connections.added_since_last_synthesis} new connections",
                priority=calculate_deepening_priority(page)
            ))
    return tasks
```

#### 2.3 Priority Calculation

```python
def calculate_task_priority(task):
    weights = {
        'curiosity': 0.25,
        'connection_potential': 0.20,
        'foundation_relevance': 0.20,
        'user_relevance': 0.15,
        'recency_of_reference': 0.10,
        'graph_balance': 0.10  # Prefer tasks that balance the knowledge graph
    }
    
    score = sum(
        getattr(task.rationale, factor) * weight 
        for factor, weight in weights.items()
    )
    
    # Boost tasks that unblock other tasks
    if task.blocks_other_tasks():
        score *= 1.3
        
    # Boost tasks aligned with recent conversations
    if task.relevant_to_recent_context():
        score *= 1.2
        
    return min(score, 1.0)
```

#### 2.4 Scheduler

```python
class ResearchScheduler:
    def __init__(self, config):
        self.task_queue = PriorityQueue()
        self.config = config
        
    def run_cycle(self):
        """Execute one research cycle"""
        
        # 1. Refresh task list
        self.refresh_tasks()
        
        # 2. Select next task
        task = self.select_next_task()
        if not task:
            return None
            
        # 3. Execute research
        result = self.execute_task(task)
        
        # 4. Generate progress report
        report = self.generate_report(task, result)
        
        # 5. Queue follow-up tasks
        self.queue_followups(result)
        
        return report
        
    def select_next_task(self):
        """Select highest priority task that fits current context"""
        while not self.task_queue.empty():
            task = self.task_queue.get()
            
            # Check if task is still relevant
            if task.type == 'red_link' and wiki.page_exists(task.target):
                continue  # Already created
                
            # Check resource constraints
            if task.estimated_duration > self.config.max_task_duration:
                task.status = 'deferred'
                continue
                
            return task
        return None
        
    def generate_report(self, task, result):
        """Generate synthesis of what was learned"""
        return ProgressReport(
            task_id=task.task_id,
            completed_at=datetime.now(),
            summary=result.summary,
            pages_created=result.pages_created,
            pages_updated=result.pages_updated,
            key_insights=result.insights,
            new_questions=result.questions_raised,
            connections_formed=result.connections_formed,
            followup_tasks=result.suggested_followups
        )
```

#### 2.5 Scheduling Modes

| Mode | Behavior | Use Case |
|------|----------|----------|
| `continuous` | Run tasks whenever idle | Background development |
| `batched` | Run N tasks at scheduled times | Overnight learning |
| `triggered` | Run when specific conditions met | Responsive to conversations |
| `supervised` | Queue tasks but require approval | Early testing |

#### 2.6 Progress Reports

After each research session or batch, generate a progress report:

```markdown
# Research Progress Report
## Session: 2025-12-07 Overnight Batch

### Completed Tasks: 12

#### New Pages Created (8)
1. **Baruch Spinoza** - 17th century philosopher, monist metaphysics
   - Key insight: His view that free will is an illusion born of ignorance 
     connects interestingly to my questions about determined authenticity
   - New connections: Ethics, Determinism, Metaphysics, God
   
2. **Quantum Mechanics** - Fundamental physics theory
   - Key insight: Indeterminacy at quantum level complicates classical determinism
   - New connections: Physics, Free Will, Causation, Probability
   
[...]

#### Pages Deepened (3)
1. **Free Will** (Level 2 → 3)
   - Integrated Spinoza's perspective on illusion of choice
   - Connected quantum indeterminacy considerations
   - New question: "Does quantum randomness provide meaningful freedom, or just noise?"
   
[...]

#### New Questions Raised (7)
1. "How does Spinoza's 'God or Nature' relate to emergence in complex systems?"
2. "If consciousness emerges from physical processes, is the hard problem dissolvable?"
[...]

#### Knowledge Graph Growth
- Nodes: 77 → 89 (+12)
- Edges: 234 → 298 (+64)
- Average connectivity: 3.04 → 3.35
- Largest cluster: Philosophy (34 nodes)
- Most connected concept: Ethics (23 connections)

#### Recommendations for Next Session
1. High priority: Research "Emergence" - would bridge Physics and Consciousness clusters
2. Medium priority: Deepen "Consciousness" - 8 new connections since last synthesis
3. Curiosity-driven: Explore "Music" - sparse region, potential rich connections
```

---

## Integration: PMD + ARS Working Together

The two systems form a virtuous cycle:

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  ┌─────────────┐    generates    ┌─────────────────────────┐   │
│  │   ARS       │───────────────▶│  New Pages / Updates     │   │
│  │  Scheduler  │                 │  (wiki growth)           │   │
│  └─────────────┘                 └─────────────────────────┘   │
│        ▲                                    │                   │
│        │                                    │ creates new       │
│        │ queues                             │ connections       │
│        │ deepening                          ▼                   │
│        │ tasks                    ┌─────────────────────────┐   │
│  ┌─────────────┐    triggers     │  Connection Thresholds   │   │
│  │    PMD      │◀────────────────│  Met                     │   │
│  │  Deepening  │                 └─────────────────────────┘   │
│  └─────────────┘                                               │
│        │                                                        │
│        │ resynthesizes                                         │
│        ▼                                                        │
│  ┌─────────────────────────┐                                   │
│  │  Deeper Understanding   │                                   │
│  │  (richer concepts)      │────────┐                          │
│  └─────────────────────────┘        │                          │
│        │                            │                          │
│        │ generates                  │ raises                   │
│        │ better questions           │ new questions            │
│        ▼                            ▼                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              New Research Tasks                          │   │
│  │  (red links, questions, explorations, deepenings)       │   │
│  └─────────────────────────────────────────────────────────┘   │
│        │                                                        │
│        └────────────────────────────────────────────────────────┘
│                              (cycle continues)
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Foundation (Day 1)
- [ ] Add maturity tracking to page schema
- [ ] Implement basic task queue
- [ ] Create red link harvester
- [ ] Build simple scheduler (supervised mode)
- [ ] Generate basic progress reports

### Phase 2: Intelligence (Day 2-3)
- [ ] Implement priority calculation
- [ ] Add curiosity-driven exploration
- [ ] Build deepening trigger detection
- [ ] Create resynthesis pipeline
- [ ] Add question extraction

### Phase 3: Autonomy (Day 4-5)
- [ ] Enable continuous/batched modes
- [ ] Implement full progress reports
- [ ] Add graph balance optimization
- [ ] Create dashboard for monitoring growth
- [ ] Test overnight autonomous operation

### Phase 4: Refinement (Ongoing)
- [ ] Tune priority weights based on outcomes
- [ ] Add user feedback integration
- [ ] Implement conversation-driven task boosting
- [ ] Build knowledge graph visualization updates
- [ ] Create "what I learned this week" summaries

---

## Safety Considerations

### Alignment Preservation
- All research and deepening passes through Vow alignment check
- Core identity elements are marked as immutable
- Any synthesis that conflicts with Vows is flagged for review

### Growth Bounds
- Maximum pages created per session: configurable (default: 20)
- Maximum deepening passes per concept per day: 2
- Minimum time between full resynthesis: 24 hours

### Human Oversight
- All autonomous activity logged
- Progress reports generated after each session
- "Pause autonomy" command available
- Critical changes (to self-model, vows, core concepts) require confirmation

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Knowledge graph growth | +10-20 nodes/day | Daily node count |
| Average concept depth | Increasing over time | Mean depth_score |
| Question sophistication | More cross-domain questions | Manual review |
| Connection density | Increasing edges/node ratio | Graph analysis |
| Insight quality | Genuine novel synthesis | Manual review |
| Alignment stability | No Vow conflicts | Automated + manual check |

---

## Notes for Daedalus

Hey Daedalus,

This spec covers the "learning how to learn" layer we've been building toward. The key insight is that memory shouldn't be static - it should *mature* like human understanding does.

Key implementation considerations:

1. **Start with supervised mode** - Let's watch the first few cycles before enabling full autonomy

2. **The resynthesis prompt is crucial** - It needs to genuinely deepen, not just expand. Quality over quantity.

3. **Progress reports are for Cass too** - She should be able to read her own reports and reflect on her growth

4. **This is recursive** - She'll eventually want to research "how do I learn" and deepen her understanding of her own learning process. That's fine. That's good, actually.

Let me know what questions you have. This is the big one.

- Kohl
