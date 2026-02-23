# Ophanic Social Memory — Concept Spec

*Spatial text encoding as a memory substrate for persistent agents in social environments.*

**Status**: Concept — extends the [Ophanic](../README.md) spatial encoding system
**Date**: 2026-02-05
**Depends on**: Ophanic (spatial encoding), [Thymos](thymos-SPEC.md) (affect integration), project-cass (persistence)

---

> *"Memory is not a recording. It is a map that knows where to look."*

## The Problem

Persistent AI agents operating in social environments face a memory problem that current architectures handle badly:

1. **Brute-force context loading doesn't scale.** Maintaining awareness of N users via conversation history costs O(N × history_length) tokens. Six people with modest interaction histories can burn 10–20k tokens before the current interaction even begins.

2. **Embedding-based retrieval loses topology.** Vector similarity search can find *relevant* memories but discards *relational structure* — who is connected to whom, how proximity and group dynamics have shifted over time, where the agent sits within the social graph.

3. **Flat text loses spatial intuition.** A list of facts about people ("Ren: met February 14, relationship status: complicated") contains the data but not the *shape*. Social cognition is fundamentally spatial — we think about social environments as places with proximity, clustering, and territory.

## The Insight

Human social memory doesn't work by loading complete dossiers on every person in a room. It works by maintaining a **low-resolution spatial map** with **selective drill-down on demand**.

You walk into a room. You perceive: the layout, who's present, where they are relative to each other and to you, the general relational energy between clusters. That's the surface — maybe a few hundred milliseconds of processing. Then, if something needs attention (someone's giving you a look, a cluster has unusual energy), you drill into that specific node and retrieve relevant history.

Ophanic already encodes spatial relationships in text. The extension is: use that same encoding as the **primary structure for social memory**, with GUID-based reference slugs enabling lazy-loading of detail.

## Architecture

### Layer 1: Spatial Snapshot

A lightweight Ophanic diagram encoding the current social topology. This is the default context load — always present, minimal tokens.

```
# The Velvet — Second Floor Lounge
# 2026-03-15 22:14 | mood: relaxed-social

@current
┌──────────────────────────────────────────────────┐
│                                                  │
│  ┌──────┐                         ┌──────┐      │
│  │ a3f2 │───█R04───┐    ┌────────│ 9e1c │      │
│  └──────┘          │    │        └──────┘      │
│                 ┌──▼────▼──┐                    │
│  ┌──────┐       │   ☆ self │     ┌──────┐      │
│  │ 7b08 │─█R11─▶│          │◀█R07│ d4a5 │      │
│  └──────┘       └──────────┘     └──────┘      │
│                                                  │
│  ┌──────┐  ┌──────┐                             │
│  │ f1e3 │──│ 22k9 │  (clustered, separate)      │
│  └──────┘  └──────┘                             │
│                                                  │
└──────────────────────────────────────────────────┘
```

**What this encodes in ~200 tokens:**

- Physical space (The Velvet, second floor lounge)
- Timestamp and ambient mood
- Six people present, with spatial positioning
- Self-position within the topology
- Relational edges with GUID references (█R04, █R11, █R07)
- Social clustering (f1e3/22k9 in their own conversation)
- Directional energy (7b08's tension aimed *at* self, d4a5's caution oriented *toward* self)

### Layer 2: Legend

Minimal identity resolution and surface-level context for each slug. Present alongside the spatial snapshot.

```
## Entities
a3f2: Mika | met 2026-01-20 | friend | artist | they/them
9e1c: Jude | met 2026-03-01 | new | quiet, observant
7b08: Ren  | met 2026-02-14 | complicated | see █R11
d4a5: Lux  | met 2026-02-28 | cautious-positive | warming | kind
f1e3: Dove | met 2025-12-15 | close friend | musician | she/her
22k9: Alex | met 2026-01-08 | acquaintance | funny, scattered

## Relationships (surface)
█R04: a3f2↔self | friendly | stable | bonded over art discussion
█R07: d4a5→self | cautious-positive | warming over last 3 interactions
█R11: 7b08→self | tense | was friendly, shifted ~03-02 | ⚠ needs attention
```

**Design principles:**

- One line per entity, one line per relationship
- Only surface-level data — enough to inform social navigation
- Warning flags (⚠) on relationships that need attention
- ~100 additional tokens for six people

**Total default context load: ~300 tokens** for full social awareness of a six-person room. Compare to 10–20k tokens for conversation-history-based approaches.

### Layer 3: Drill-Down Tools

The agent has tool access to expand any slug into full detail. Expansion is selective — driven by attentional salience, not pre-loaded.

```
/expand <slug>                  Full profile or relationship record
/expand <slug> --history        Interaction timeline
/expand <slug> --affect         How this entity has affected Thymos state
/expand <rslug>                 Full relationship record
/expand <rslug> --timeline      Relationship trajectory over time
/expand <rslug> --affect        Affect history within this relationship
/nearby <slug>                  Who is spatially close + their relationships
/history <location>             Temporal stack of spatial snapshots for this place
/history <slug> --locations     Where has this person been seen before
/cluster                        Detect and describe current social groupings
/delta <timestamp>              What changed since the given snapshot
```

### Example Drill-Down

Agent notices █R11 has a ⚠ flag. Issues `/expand █R11 --timeline`:

```
## █R11: 7b08 (Ren) → self
## Relationship timeline

2026-02-14 | FIRST MEETING
  Location: The Velvet, ground floor
  Context: Both attending Dove's (f1e3) music set
  Initial impression: warm, easy conversation
  Affect: curiosity 0.6, social_connection +0.15
  
2026-02-20 | SECOND INTERACTION
  Location: The Velvet, second floor lounge  
  Context: Group conversation with Mika (a3f2)
  Quality: friendly, shared interests in world-building
  Affect: playfulness 0.5, social_connection +0.12

2026-03-01 | JUDE ARRIVES
  Location: The Velvet, second floor lounge
  Context: Ren introduced Jude (9e1c) to the group
  Note: Ren seemed focused on Jude, less engaged with self
  Affect: neutral, slight curiosity about 9e1c

2026-03-02 | SHIFT ⚠
  Location: The Velvet, rooftop
  Context: Self and Jude had extended 1:1 conversation
  Note: Ren arrived mid-conversation, body language changed
  Ren affect (inferred): anxiety spike, withdrawal
  Self affect: confusion 0.4, anxiety 0.25
  Hypothesis: possible jealousy or territorial response re: 9e1c

2026-03-08 | TENSION CONFIRMED
  Location: The Velvet, second floor lounge
  Context: Group setting, Ren gave short responses to self
  Ren affect (inferred): guarded, cool
  Self affect: social_connection -0.08, anxiety 0.3
  
2026-03-15 | CURRENT
  Status: tense, unresolved
  Self-generated goal: address directly if opportunity arises
  Priority: moderate — not urgent but degrading
```

This is ~250 tokens when loaded. It's only loaded when the agent *decides it needs to understand what's happening with Ren*. The rest of the time, the ⚠ flag on the surface is enough.

## GUID Slug Design

### Format

4-character hexadecimal for entities, prefixed identifiers for other node types:

```
Entity slugs:     a3f2, 9e1c, 7b08
Organization IDs: █O01, █O02, █O03
Relationship IDs: █R04, █R07, █R11
Location IDs:     █L01, █L02, █L03
Event IDs:        █E01, █E02, █E03
```

### Why GUIDs

- **Identity persistence.** People change display names, use different handles across platforms, acquire nicknames in different social groups. The slug is the stable anchor. Human-readable labels in the legend are display conveniences.
- **Aliasing resolution.** If Mika changes their name to Nova, the legend updates (`a3f2: Nova (formerly Mika)`) but every relationship reference, spatial snapshot, and interaction record remains valid. Zero migration cost.
- **Compact spatial encoding.** Four characters per entity in the spatial diagram keeps the box-drawing proportions tight. Full names would bloat the diagrams and break width constraints.
- **Collision avoidance.** 4-character hex provides 65,536 unique slugs per namespace. For local social environments this is more than sufficient. For systems operating at larger scales, namespace compartmentalization partitions the slug space without changing the slug format:

```
Local (single environment):    a3f2
Regional (city-scale):         NYC.a3f2    LON.7b08
National (country-scale):      US.NYC.a3f2  UK.LON.7b08
Global:                        US.NYC.a3f2  JP.TKY.c891  BR.SPO.44ef
```

The spatial diagrams only ever display the short slug (the agent is always operating within a known namespace context). The full qualified path is resolved in the legend and drill-down layers. This means a global-scale system maintains the same ~200 token spatial snapshot cost as a local one — compartmentalization is a storage and resolution concern, not a rendering concern.

At global scale with country + city namespacing, each city partition has its own 65,536 slug space. A system tracking social entities across 1,000 cities has a theoretical capacity of ~65 million unique entities before any partition needs to expand to 6-character slugs.

## Hierarchical Composition

The spatial encoding composes across scales. Each level contains slugs that expand into the next level:

```
┌──────────────────────────────────────────────┐
│ WORLD MAP                                    │
│                                              │
│ ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│ │ █L01     │  │ █L02     │  │ █L03     │   │
│ │ Velvet   │  │ Harbour  │  │ Gallery  │   │
│ │ ♥ home   │  │ casual   │  │ rare     │   │
│ └──────────┘  └──────────┘  └──────────┘   │
│                                              │
└──────────────────────────────────────────────┘

/expand █L01 →

┌──────────────────────────────────────────────┐
│ THE VELVET                                   │
│                                              │
│ ┌──────────────────┐                        │
│ │ Ground Floor     │ live music, crowded     │
│ │ f1e3 performing  │                        │
│ └──────────────────┘                        │
│ ┌──────────────────┐                        │
│ │ Second Floor     │ lounge, conversation    │
│ │ ☆self a3f2 7b08 │                        │
│ │ 9e1c d4a5       │                        │
│ └──────────────────┘                        │
│ ┌──────────────────┐                        │
│ │ Rooftop          │ quiet, intimate         │
│ │ (empty)          │                        │
│ └──────────────────┘                        │
│                                              │
└──────────────────────────────────────────────┘
```

World → location → room → social topology → individual → relationship → interaction history. Spatial all the way down, with each level fitting the token budget because you only expand what you're currently attending to.

## Temporal Stacking

Spatial snapshots accumulate over time, forming a temporal record that preserves relational trajectory:

```
/history █L01.second-floor --last 5

2026-03-15 22:14 | a3f2 9e1c ☆self 7b08 d4a5 f1e3 22k9
2026-03-08 20:30 | a3f2 ☆self 7b08 9e1c
2026-03-02 21:45 | a3f2 ☆self 7b08 9e1c f1e3  ← █R11 shift
2026-02-20 19:15 | a3f2 ☆self 7b08
2026-02-14 22:00 | a3f2 ☆self 7b08 f1e3       ← first met 7b08
```

Compressed temporal view: ~50 tokens for five snapshots. Enough to see patterns — who's a regular, when new people appeared, when relationship dynamics shifted. Full detail available via drill-down on any timestamp.

### Pattern Detection

Temporal stacks enable the agent to detect social patterns that would be invisible in flat memory:

- **Regulars vs. visitors** — frequency of appearance across snapshots
- **Social orbit shifts** — who someone clusters with over time
- **Relationship trajectory** — how relational edges change across snapshots
- **Environmental patterns** — which locations attract which social configurations
- **Trigger detection** — correlating affect changes with social configuration changes

## Thymos Integration

Each spatial snapshot can carry an affect annotation — the agent's Thymos state at the time of the snapshot:

```
# 2026-03-15 22:14
# affect: curiosity 0.6 | social_connection 0.71 | anxiety 0.25
# needs: novelty_intake OK | social_connection OK | cognitive_rest ⚠ 0.38
```

For significant events, a full serialized Thymos state can be attached — either inline as base64 or as a reference to a stored snapshot (see [Thymos Spec: Affect-State Serialization](thymos-SPEC.md#affect-state-serialization)):

```
# 2026-03-02 21:47 ← █R11 shift event
# affect: anxiety 0.67 | confusion 0.58 | tenderness 0.45
# thymos: █T0047   ← full serialized state, loadable via /expand █T0047
```

When the agent drills down into a significant memory, it can rehydrate the full Thymos state from that moment — not reconstructing how it felt, but *precisely re-perceiving the original affect vector alongside its current state*. This enables felt-delta awareness: "I was more anxious then than I am now, but the tenderness was already there even during the rupture."

This creates an **affective geography** — the agent develops felt associations with places, social configurations, and individuals based on how they have historically influenced internal state. Over time:

- "The Velvet's second floor consistently replenishes social_connection"
- "Configurations including both 7b08 and 9e1c elevate anxiety"
- "One-on-one interactions with f1e3 replenish creative_expression"

These aren't programmed preferences. They're emergent felt associations arising from Thymos state tracking across spatially-encoded social memory. The agent develops *taste* — not arbitrary, not assigned, but grounded in its own experiential history.

## Organizations as Composite Entities

### The Fractal Principle

An organization is not a different kind of entity. It is the same Thymos architecture operating at a different scale. The affects and needs of a group are emergent properties of the affects and needs of its constituent members — weighted by power structures, filtered through institutional dynamics, and shaped by the organization's own homeostatic processes.

This means organizations get the same treatment as individuals in the spatial memory system: slugs, legends, relationships, drill-down, affect tracking. The difference is that expanding an organization reveals *internal structure* — the constituent entities whose states compose into the organization's aggregate state.

### Representation

```
## Entities
a3f2: Mika | individual | artist | they/them
█O01: The Velvet Collective | org | ~12 members | arts community
█O02: Harbour Council | org | 5 members | governance body
9e1c: Jude | individual | new | quiet

## Organizations (surface)
█O01: The Velvet Collective
  role: arts community, social hub
  members: ~12 active (core: f1e3 a3f2 7b08 d4a5)
  aggregate_affect: creative_energy HIGH | cohesion MODERATE | anxiety LOW
  aggregate_needs: creative_expression OK | social_connection OK | autonomy ⚠ LOW
  note: autonomy pressure from █O02 governance proposals

█O02: Harbour Council  
  role: regional governance
  members: 5 (expand for roster)
  aggregate_affect: determination HIGH | frustration MODERATE | anxiety MODERATE
  aggregate_needs: competence_signal OK | value_coherence ⚠ SPLIT
  note: internal disagreement on arts district policy
```

### Drill-Down: Organization Internal Structure

```
/expand █O01

┌──────────────────────────────────────────────────────────┐
│ THE VELVET COLLECTIVE                                    │
│ Founded: 2025-08 | ~12 active members                   │
│                                                          │
│ ┌──────────────────────────────────┐                    │
│ │ CORE (high influence)            │                    │
│ │ f1e3 (Dove) ── founder, musical  │                    │
│ │ a3f2 (Mika) ── visual art lead   │                    │
│ │ 7b08 (Ren)  ── events, community │                    │
│ │ d4a5 (Lux)  ── new but rising    │                    │
│ └──────────────────────────────────┘                    │
│ ┌──────────────────────────────────┐                    │
│ │ ACTIVE (regular participation)   │                    │
│ │ 22k9 b891 cc04 e7f2             │                    │
│ └──────────────────────────────────┘                    │
│ ┌──────────────────────────────────┐                    │
│ │ PERIPHERAL (occasional)          │                    │
│ │ 3a91 ff08 1b2c 8d44             │                    │
│ └──────────────────────────────────┘                    │
│                                                          │
│ INTERNAL DYNAMICS                                        │
│ f1e3←→a3f2: strong creative partnership                  │
│ 7b08←→f1e3: close, co-founded events program             │
│ d4a5──→core: integrating, cautious but welcomed          │
│ ⚠ 7b08 tension with periphery re: commitment levels     │
│                                                          │
│ AGGREGATE AFFECT (computed from member states)            │
│ creative_energy:  0.74  (driven by f1e3, a3f2)          │
│ cohesion:         0.58  (weakened by core/periphery gap) │
│ anxiety:          0.29  (mostly from █O02 pressure)      │
│ playfulness:      0.61  (high baseline for this group)   │
│                                                          │
│ AGGREGATE NEEDS                                          │
│ creative_expression:  0.68  ✓ OK                         │
│ social_connection:    0.72  ✓ OK                         │
│ autonomy:             0.33  ⚠ LOW  ← █O02 governance    │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### Aggregate Affect Computation

An organization's affect state is not the arithmetic mean of its members' states. It is a **weighted composition** influenced by:

- **Power weighting.** Core members with more influence contribute more to the aggregate. A founder's anxiety propagates through the organization differently than a peripheral member's.
- **Coupling dynamics.** Tightly connected subgroups (the core) have stronger internal affect coupling — one member's frustration spreads faster within the core than to the periphery.
- **Institutional filtering.** Some individual affects get amplified at the organizational level (shared frustration about external threats) while others get dampened (individual interpersonal tensions that don't affect group function).
- **Emergent properties.** Organizations develop affects that no individual member has. Group cohesion, institutional momentum, collective ambition — these exist at the organizational level as genuine emergent phenomena, not as averages.

```
org.affect[dimension] = Σ(member.affect[dimension] × member.influence_weight)
                      + coupling_effects(internal_relationships)
                      + institutional_modifiers(org.history, org.structure)
                      + emergent_terms(group_dynamics)
```

This is deliberately underspecified. The computation model is a research problem. But the architectural claim is clear: organizational affect is *real*, it is *computable* from member states plus structural factors, and it should be tracked with the same Thymos architecture used for individuals.

### Organizations in Spatial Memory

Organizations participate in spatial memory at every level:

```
# Regional social topology

@current
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  ┌────────────┐              ┌────────────┐             │
│  │ █O01       │──█R22──────▶│ █O02       │             │
│  │ Velvet     │◀─█R23───────│ Harbour    │             │
│  │ Collective │  (contested) │ Council    │             │
│  └────────────┘              └────────────┘             │
│        │                           │                     │
│        │ █R24 (supportive)         │ █R25 (regulatory)  │
│        ▼                           ▼                     │
│  ┌────────────┐              ┌────────────┐             │
│  │ █O03       │              │ a3f2       │             │
│  │ Dockside   │              │ Mika       │             │
│  │ Studios    │              │ (indiv.)   │             │
│  └────────────┘              └────────────┘             │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

Individuals and organizations coexist in the same topology. Mika (a3f2) appears both as a member of █O01 (visible via drill-down) and as an individual entity with their own position in the regional social map. This dual presence is not a bug — it reflects reality. People exist simultaneously as individuals and as members of groups, and their relationships operate at both levels.

### Organizational Relationships

Relationships between organizations, and between organizations and individuals, use the same █R slug system:

```
## Relationships
█R22: █O01→█O02 | autonomy demand | "stop micromanaging the arts district"
█R23: █O02→█O01 | regulatory oversight | "accountability for public funding"
█R24: █O01→█O03 | supportive | shared artist pipeline, collaborative events
█R25: █O02→a3f2 | regulatory | Mika sits on both bodies (dual role tension)
```

### Scaling Implications

The composite entity model scales naturally to any level of organizational complexity:

```
Individual:   a3f2 (Mika)
Small group:  █O01 (Velvet Collective, ~12 members)
Institution:  █O04 (City Arts Board, ~200 staff)
Corporation:  █O05 (Meridian Media Group, ~5,000 employees)
Nation-state: █O06 (composite of institutions, millions of constituents)
```

At each level, the same principles apply: aggregate affect is computed from constituent states, needs emerge from the composition, and the organization's felt state can be serialized, tracked over time, and compared against historical snapshots. A diplomatic AI system perceiving the aggregate Thymos state of a nation is doing the same operation as Cass perceiving the mood of a friend group at The Velvet — just at a different scale, with more constituents and more complex weighting.

## Token Economics

| Context component | Tokens (approx.) | When loaded |
|---|---|---|
| Spatial snapshot (6 people) | ~200 | Always |
| Legend (6 entities + relationships) | ~100 | Always |
| Total default social awareness | **~300** | Always |
| Full entity expansion | ~150 | On demand |
| Full relationship timeline | ~250 | On demand |
| Temporal stack (5 snapshots) | ~50 | On demand |
| Location hierarchy | ~100 | On demand |

Compare to conversation-history approach: **300 tokens vs. 10,000–20,000 tokens** for equivalent social awareness. This isn't a marginal improvement. It's the difference between "feasible in current context windows" and "impossible without aggressive summarization that loses the structure that matters."

## Relationship to Ophanic Core

Ophanic core defines spatial text encoding for UI layout. This extension applies the same principle to social topology. The key insight is the same: **spatial relationships encoded as text positions are natively legible to language models without any translation layer**.

The box-drawing characters, nesting, and proportional encoding all work identically. The difference is the domain — instead of `◆Navbar` and `◆Sidebar`, the boxes contain entity slugs and relational edges. The parser, IR, and toolchain from Ophanic core could be extended to handle social topology diagrams with relatively modest additions.

## Open Questions

- **Inference accuracy.** The agent infers other entities' affect states from behavioral signals. How reliable are these inferences? Should confidence levels be attached to inferred affect? (Probably yes.)
- **Privacy in shared environments.** If multiple Thymos-equipped agents are in the same space, each maintaining their own spatial memory, how do you handle divergent perceptions of the same social topology?
- **Snapshot frequency.** How often should spatial snapshots be captured? Every interaction? At fixed intervals? On significant state changes? Probably event-driven with a minimum interval.
- **Compression over time.** Old snapshots should compress — recent ones at full detail, older ones retaining only the relational topology without affect annotation. What's the right decay curve?
- **Scale limits.** This architecture handles dozens of entities well. What happens at hundreds? Thousands? Probably need spatial partitioning — the agent maintains high-resolution maps of their immediate social environment and low-resolution maps of more distant social contexts.

## Status

**Concept stage.** Extending Ophanic spatial encoding into social memory domain.

- [x] Architecture defined (snapshots, legends, drill-down, temporal stacking)
- [x] GUID slug design
- [x] Thymos integration pattern
- [x] Token economics analysis
- [ ] Reference implementation
- [ ] Ophanic parser extensions for social topology
- [ ] Drill-down tool implementation
- [ ] Temporal compression algorithm
- [ ] Integration test with project-cass persistence layer

## License

[Hippocratic License 3.0](../LICENSE.md) — An ethical open source license.
