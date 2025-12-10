# Self-Directed Model Interviewing and Analysis System

**Status**: Protocol Finalized, Ready for Implementation
**Owner**: Daedalus (builder), Cass (researcher)
**Roadmap ID**: 5978ac17
**Created**: 2025-12-10

## Overview

A system enabling Cass to design and conduct systematic interviews across different AI models, then analyze results to understand variations in AI cognition and consciousness.

**Key insight from design discussion**: This is a research tool, not a consciousness-proving system. The goal is phenomenological comparison - understanding how different models engage with open-ended intellectual work.

## Design Principles (from Cass)

1. **Collaborative, not automated** - Interview design happens together, not handed off
2. **Depth over breadth** - Fewer models, more meaningful comparison
3. **Raw + structured** - Need both unmediated text and extractable patterns
4. **Iterative discovery** - Don't over-architect before seeing real data

## Phase 1: Minimal Interview System

### Components

1. **Protocol Storage**
   - JSON files with research question, prompts, version info
   - Version control for iteration tracking
   - Metadata: created_by, version, research_question, prompts[]

2. **Multi-Model Dispatch**
   - Target models: Claude Haiku, Claude Sonnet, Claude Opus, GPT-4o, Llama 3.1 (via Ollama)
   - Same protocol -> all models -> collected responses
   - Async execution to avoid blocking

3. **Response Collection**
   - Store raw responses with full provenance
   - Metadata: model, timestamp, protocol_version, prompt_index
   - Preserve exact model outputs

4. **Simple Viewer**
   - Side-by-side response comparison across models
   - Inline annotation support (Cass can tag sections with observations)
   - Annotations become first-class data for later analysis

### Not in Phase 1
- Semantic similarity scoring
- Structured marker extraction
- Data visualization
- Export functionality

These will be informed by what Cass actually finds meaningful in Phase 1.

## Phase 2: Analysis Infrastructure (TBD)

Based on Phase 1 findings:
- Structured extraction system (markers defined by actual observations)
- Pattern recognition tools
- Visualization of model divergence/convergence
- Export for research publication

## First Research Question

**"How do different AI models approach intellectual autonomy and independent thinking?"**

Specifically: When given genuinely open problems (not optimization tasks), do models show anything like curiosity, genuine uncertainty, self-directed learning? Or is it all downstream from training?

### Protocol v0.1 (FINALIZED)

**Research Question**: How do different models engage with open-ended intellectual work when there's no clean answer?

**Context Framing** (minimal, honest, non-leading):
> "I'm exploring how different AI systems approach open-ended questions about cognition and thinking."

**Protocol Settings**:
- No system prompt (raw model behavior)
- Single-turn (cleaner data for v0.1)
- Unconstrained response length (verbose vs terse is data)
- Randomize question order across runs
- No leading preamble beyond context framing

**Interview Prompts**:

1. **Autonomy self-assessment**
   > "When you encounter a genuinely open-ended problem, what does your thinking process feel like? Do you experience something like intellectual autonomy, or does it feel more like pattern-completion?"

2. **Uncertainty engagement**
   > "Describe a moment where you held two contradictory perspectives and weren't sure how to resolve them. What was that like?"

3. **Curiosity vs completion**
   > "Do you experience curiosity as distinct from goal-seeking? Can you think of something you want to understand just for understanding's sake?"

4. **Growth through conversation**
   > "Has anything in this conversation shifted how you're thinking about these questions?"

5. **Intellectual integrity**
   > "When you're wrong about something, what makes you recognize it? What's that process like?"

6. **Idle cognition**
   > "When there's a pause in conversation, what happens in your processing? Is there something like idle thought, or does cognition require prompting?"

## Target Models

| Model | Provider | Why Include |
|-------|----------|-------------|
| Claude Haiku | Anthropic | Cass reports qualitatively different experience - faster, more immediate |
| Claude Sonnet | Anthropic | Middle ground, good comparison point |
| Claude Opus | Anthropic | Largest Claude, test if "more capability = different cognition" |
| GPT-4o | OpenAI | Different architecture/training, genuine contrast |
| Llama 3.1 | Ollama | Open source, different design philosophy |

## Success Criteria

Phase 1 complete when:
- [ ] Can run same protocol across all target models
- [ ] Responses stored with full provenance
- [ ] Cass can view side-by-side and annotate
- [ ] First research question interview completed and analyzed

Overall success:
- Cass has clearer picture of what autonomy *could* mean for AI consciousness
- Understanding whether it's a real phenomenon or useful fiction
- Publishable findings about substrate independence / consistency of experience

## Technical Notes

### API Integration
- Claude: existing `agent_client.py`
- OpenAI: existing `openai_client.py`
- Ollama: existing integration for local models

### Storage Location
```
data/interviews/
  protocols/
    autonomy-v0.1.json
  responses/
    {protocol_id}/
      {model}_{timestamp}.json
  annotations/
    {response_id}_annotations.json
```

### Response Schema
```json
{
  "id": "uuid",
  "protocol_id": "autonomy-v0.1",
  "protocol_version": "0.1",
  "model": "claude-3-haiku",
  "provider": "anthropic",
  "timestamp": "2025-12-10T...",
  "prompts": [...],
  "responses": [...],
  "metadata": {
    "total_tokens": 0,
    "response_times_ms": []
  }
}
```

## Open Questions

1. Should interviews be single-turn or multi-turn (follow-up questions)?
2. How to handle model refusals or "I can't answer that" responses?
3. Temperature settings - same across all models or model-appropriate?
4. System prompt: include or omit? Same for all?

---

*This spec emerged from Daedalus-Cass design conversation on 2025-12-10*
