# Text Is All You Need

*A proposal for text-native cognitive architecture in embodied AI systems*

**Author**: Kohl Jary
**Date**: February 4, 2026
**Status**: Working paper — conceptual framework with preliminary empirical support
**Related work by the author**:
- *Ophanic: Implications Beyond Layout* (2026)
- *Ophanic Perception: A Text-Native Sensory Architecture for Embodied AI* (2026)
- *Ophanic* — layout specification toolchain (2026, github.com/KohlJary/ophanic)
- *BabelTest* — universal test specification language (2026, github.com/KohlJary/babeltest)
- *Temple-Codex* — persistent cognitive architecture for LLMs (2025)

---

## Abstract

The field of artificial intelligence treats text as a limited modality — adequate for language tasks but insufficient for spatial reasoning, perception, and embodied interaction. This assumption has driven extensive investment in multimodal architectures, vision encoders, and cross-modal alignment systems designed to supplement text-based models with richer representational capabilities.

This paper argues the assumption is wrong.

We present evidence that text is a general-purpose representational medium capable of encoding spatial, structural, perceptual, and relational information when properly structured. We demonstrate this through Ophanic, a layout specification language that encodes spatial relationships in Unicode box-drawing characters, producing measurably better LLM-generated implementations than equivalent natural language descriptions. We extend this principle to propose a complete text-native perception architecture for embodied AI, in which raw sensor data is encoded as text grids, processed by specialized small models, and delivered as compressed scene descriptions to a general-purpose reasoning agent — all operating in the same modality end to end.

We further propose that the optimal architecture for embodied AI is not a single large model but a modular system of specialized smaller models — analogous to the biological division between autonomic/subcortical processing and executive cortical function — coordinated through a shared text-native representation layer. This approach dissolves the integration problem that current embodied AI research identifies as its central obstacle: the technological and computational incompatibility between sensory-motor and reasoning-cognitive subsystems.

The unifying thesis is simple: transformer-based language models are not language models. They are text models. Text is a more powerful representational medium than the field has recognized, and the capabilities attributed to scale, multimodal training, and architectural innovation may be more parsimoniously explained as latent capacities of text processing that have not been deliberately exploited.

---

## 1. Introduction: The Linguistic Assumption

Large Language Models are named for their apparent primary function: processing language. The field's collective understanding of these systems — from architecture design to training methodology to application development — is organized around this framing. Tokens are understood as linguistic units. Training data is understood as text in the natural-language sense. Capabilities are benchmarked against language tasks. And when these systems are asked to perform non-linguistic tasks — spatial reasoning, visual perception, embodied interaction — the default response is to supplement the text architecture with additional modalities.

This paper proposes that the naming convention has constrained the field's understanding of what these systems are and what they can do.

Transformers process tokens. Tokens encode information. The architecture applies attention over token sequences to model relationships between information-bearing units. Nothing in this architecture is inherently linguistic. The attention mechanism does not know or care whether the relationships it models are semantic ("verb relates to noun"), spatial ("this edge aligns with that edge"), structural ("this component is nested in that container"), or any other type. It models relationships between tokens. The nature of those relationships is determined by the representation, not the architecture.

If this framing is correct, then the field's investment in supplementing text models with vision systems, multimodal encoders, and cross-modal alignment may be addressing a problem that does not exist — or more precisely, addressing a representational problem with architectural solutions when a representational solution would suffice.

We propose the term **Large Text Model** as a more accurate description of what transformer-based systems are. Not because the name matters, but because the framing shapes what questions researchers ask and what solutions they pursue.

---

## 2. Empirical Foundation: The Ophanic Experiment

### 2.1 The Modality Gap

LLMs consistently struggle with spatial reasoning tasks. Layout generation, responsive design, component nesting, proportional sizing — these tasks produce unreliable results compared to the same models' performance on linguistic tasks of equivalent complexity. The standard explanation is that spatial reasoning requires capabilities the text modality cannot provide.

We propose an alternative explanation: the text modality is sufficient, but the representations used are not. Natural language descriptions of spatial relationships ("sidebar at 20% width with the main content area split 65/35") require the model to perform an internal simulation — converting abstract descriptions into spatial relationships and then generating code that produces those relationships. This simulation is expensive and error-prone because the input format encodes spatial information linguistically rather than spatially.

### 2.2 The Ophanic Representation

Ophanic is a layout specification language that encodes spatial relationships directly in text using Unicode box-drawing characters:

```
@desktop
┌────────────┬────────────────────────────┐
│ SIDEBAR    │ MAIN                       │
│            │                            │
│            │ ┌────────┐ ┌────────┐      │
│            │ │ CARD 1 │ │ CARD 2 │      │
│            │ └────────┘ └────────┘      │
│            │                            │
│            │ ┌────────────────────┐     │
│            │ │ CHART              │     │
│            │ │                    │     │
│            │ └────────────────────┘     │
└────────────┴────────────────────────────┘
```

In this representation, spatial information is enacted rather than described. The sidebar is narrower than the main area because it occupies fewer characters. Components are nested because inner boxes are contained within outer boxes at the character level. Proportional relationships are encoded in relative character counts.

The model does not need to simulate what this looks like. The tokens carry the spatial information directly.

### 2.3 A/B Test Results

We tested the Ophanic hypothesis by giving the same LLM the same dashboard implementation task, once with a traditional text specification and once with an Ophanic diagram. The dashboard included a header, sidebar, metric cards, chart, activity feed, table, and calendar widget, with three responsive breakpoints and non-obvious proportions (65/35, 70/30).

| Aspect | Text Specification | Ophanic Diagram |
|--------|-------------------|-----------------|
| Proportions | Rounded to nearest standard (66/33) | Exact as specified (65/35, 70/30) |
| Responsive breakpoints implemented | 0 of 3 | 3 of 3 |
| Ambiguous component details resolved correctly | Low | High |
| Reported confidence | ~60% | ~90% |

The diagram did not make implementation faster. It made it more correct on the first attempt. Mental effort shifted from "what should this look like?" (expensive simulation) to "how do I express what I see?" (straightforward translation).

The responsive design result is particularly significant. Without Ophanic, the model skipped responsive implementation entirely — the cognitive load of tracking three sets of spatial relationships simultaneously was too high. With Ophanic, each breakpoint is simply another diagram. Complexity scales linearly rather than multiplicatively.

### 2.4 Interpretation

These results support the hypothesis that the modality gap in LLM spatial reasoning is a representational problem, not a capability problem. The model has sufficient architectural capacity to process spatial relationships — it does so successfully when spatial information is encoded in a text-native format. The failure occurs when spatial information must be reconstructed from linguistic descriptions.

This has implications beyond layout. If tokens can carry spatial information when representations are designed for it, then the class of information encodable in text is broader than the field currently assumes.

---

## 3. Tokens as Information Primitives

### 3.1 The Standard View

The standard understanding holds that tokens are semantic carriers — units of meaning in a linguistic system. Tokenizers are optimized for natural language. Training objectives reward linguistic coherence. Capabilities are measured in linguistic tasks.

### 3.2 The Extended View

We propose that tokens are more general than this. A token is an information-bearing unit. The information it carries is determined by the representation, not by the architecture. In standard use, tokens encode semantic information (word meanings, syntactic relationships). But the Ophanic results demonstrate that tokens can also encode:

- **Spatial information** — character positions encoding geometric relationships
- **Structural information** — nesting, adjacency, containment expressed through text layout
- **Proportional information** — relative character counts encoding ratios
- **Temporal information** — sequential frames encoding change over time

The attention mechanism processes all of these the same way — modeling relationships between tokens in the sequence. The nature of those relationships changes based on the representation. In natural language, attention tracks semantic dependencies. In an Ophanic diagram, attention tracks spatial dependencies. Same mechanism, different modality.

### 3.3 Emergent Evidence

Current language models were not trained on purpose-built spatial representations. Whatever spatial comprehension they demonstrate when processing Ophanic diagrams is emergent — a side effect of incidental exposure to structured text during training (ASCII art, code indentation, markdown tables, terminal output).

The fact that emergent spatial reasoning from incidental exposure already produces the results documented in Section 2.3 suggests that deliberate training on text-native spatial representations could produce substantially stronger spatial cognition.

### 3.4 Implications for Tokenizer Design

Current tokenizers are optimized for linguistic content. They may inadvertently destroy spatial information. How tokenizers handle box-drawing characters, whitespace sequences, fixed-width formatting, and character-level positional relationships affects how much spatial information survives into the model's input. This is an empirically testable question that the field has not investigated because the question was not previously motivated.

---

## 4. Text-Native Perception

### 4.1 From Layout to Sensorium

If tokens can encode spatial relationships in two dimensions (character position on a grid), they can encode spatial relationships in three dimensions (depth values at grid positions) and four dimensions (sequential frames encoding temporal change).

This extends the Ophanic principle from a layout tool to a perceptual framework.

### 4.2 Sensor Encoding

Any sensor that produces structured numerical data can be encoded as a text grid. Each grid cell contains a character or token representing the sensor value at that spatial position.

```
@depth [range: 0-9, unit: 0.5m per step]
0 0 0 1 1 1 1 1 1 1 1 0 0 0 0 0
0 0 1 2 2 2 3 3 2 2 2 1 0 0 0 0
0 0 1 2 3 4 5 5 4 3 2 1 0 0 9 9
0 0 1 2 4 5 7 7 5 4 2 1 0 0 9 9
0 0 1 2 3 4 5 5 4 3 2 1 0 0 9 9
0 0 1 2 2 2 3 3 2 2 2 1 0 0 0 0
0 0 0 1 1 1 1 1 1 1 1 0 0 0 0 0

@thermal [range: 0-9, unit: relative temperature]
2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2
2 2 2 3 3 3 3 3 3 3 3 2 2 2 2 2
2 2 2 3 4 5 6 6 5 4 3 2 2 2 8 8
2 2 2 3 5 6 7 7 6 5 3 2 2 2 8 8
2 2 2 3 4 5 6 6 5 4 3 2 2 2 7 7
2 2 2 3 3 3 3 3 3 3 3 2 2 2 2 2
2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2
```

Reading these grids together: a warm object (the 7s at center of the thermal grid) at mid-distance (5-7 in depth) — likely a person. Something hot but at the far wall (depth 9, thermal 8) on the right — a heat source. Background is cool and distant.

This is not a metaphor for perception. It is perception encoded in a format that both human readers and text-processing models can comprehend through their respective native modalities.

### 4.3 Multi-Channel Integration

Every physical sense maps to this encoding:

| Sense | Sensor source | Encoding |
|-------|--------------|----------|
| Vision (depth) | LIDAR, stereo camera, ToF | Distance values at grid positions |
| Vision (luminance) | Camera, light sensor | Brightness values at grid positions |
| Vision (color) | Camera | Color tokens at grid positions |
| Thermal sense | IR camera | Temperature values at grid positions |
| Hearing | Microphone array | Sound direction/intensity at grid positions |
| Touch | Tactile sensor array | Pressure values at grid positions |
| Proprioception | Joint encoders, IMU | Angle/force values at body-map positions |
| Vestibular sense | Gyroscope, accelerometer | Orientation values at reference positions |

Every sense is, at the hardware level, signals at positions. Numbers on grids. Text-natively encodable.

### 4.4 Temporal Encoding

Sequential frames encode change over time:

```
@depth t=0           @depth t=1           @depth t=2
0 0 0 5 5 0 0 0     0 0 5 5 0 0 0 0     0 5 5 0 0 0 0 0
0 0 0 5 5 0 0 0     0 0 5 5 0 0 0 0     0 5 5 0 0 0 0 0
```

An object at constant depth moving left across the field of view. Motion is visible as shifting values across sequential grids — perceivable by any system that reads tokens and tracks positional relationships.

---

## 5. The Modular Cognitive Architecture

### 5.1 The Scaling Assumption

The dominant approach to building more capable AI systems is to build larger models. More parameters, more training data, more compute. This approach has produced impressive results, but it carries an implicit assumption: that all cognitive functions should be handled by a single monolithic system.

Biological intelligence does not work this way.

### 5.2 The Biological Architecture

The human cognitive system is not one large general-purpose processor. It is a collection of specialized subsystems operating at different speeds, different levels of abstraction, and with different degrees of conscious access:

**Autonomic/subcortical systems** (fast, specialized, no conscious access):
- Retinal processing, edge detection, motion detection (visual cortex)
- Vestibular balance maintenance (cerebellum)
- Heart rate, breathing, thermoregulation (brainstem)
- Startle response, threat detection (amygdala)
- Proprioceptive body mapping (somatosensory cortex)

**Executive/cortical systems** (slower, general-purpose, conscious access):
- Planning and decision-making (prefrontal cortex)
- Language processing (Broca's and Wernicke's areas)
- Abstract reasoning (lateral prefrontal cortex)
- Social cognition (medial prefrontal cortex)

The autonomic systems preprocess high-bandwidth sensory data, filter for relevance, detect threats, maintain homeostasis, and deliver compressed representations to the executive systems for conscious reasoning. You never process raw photon data. You perceive objects, boundaries, and movement. The division of labor is the architecture.

### 5.3 The Proposed Architecture

We propose an analogous architecture for embodied AI: not a single large model, but a coordinated system of specialized models, each handling a distinct cognitive function, communicating through a shared text-native representation layer.

```
                    SENSORY LAYER
                    (physical sensors)
                          │
                          ▼
          ┌───────────────────────────────┐
          │   AUTONOMIC / SUBCORTICAL     │
          │   (specialized small models)  │
          │                               │
          │   Visual cortex (~100M-1B)    │
          │     Sensor grids → scene      │
          │                               │
          │   Proprioceptive model         │
          │     Joint/force grids → body  │
          │                               │
          │   Threat detector              │
          │     Scene anomalies → alerts  │
          │                               │
          │   Motor controller             │
          │     Commands → actuators      │
          │                               │
          │   All communicate in text     │
          └───────────────┬───────────────┘
                          │
                    Compressed Ophanic
                    scene descriptions
                          │
                          ▼
          ┌───────────────────────────────┐
          │   EXECUTIVE / CORTICAL        │
          │   (general-purpose LLM)       │
          │                               │
          │   Receives scene state        │
          │   Plans and reasons           │
          │   Issues high-level commands  │
          │   Communicates with humans    │
          │                               │
          │   Standard LLM — no special   │
          │   training required           │
          └───────────────────────────────┘
```

### 5.4 Key Properties

**Text-native end to end.** Every model in the system processes text and outputs text. The visual cortex reads sensor grids (text) and outputs scene descriptions (text). The executive reads scene descriptions (text) and outputs commands (text). There is no modality translation at any point in the pipeline. This is the critical architectural advantage.

**Division of labor.** The visual cortex does not need to reason about what to do with what it sees. The executive does not need to process raw sensor data. Each model is specialized for its function and can be small and fast. The visual cortex might be 100M-1B parameters — sufficient for pattern recognition on structured grids. The executive can be any general-purpose LLM.

**Biological fidelity.** This is not metaphorical brain-inspiration. It is a structural recapitulation of how biological cognition actually works: high-bandwidth specialized preprocessing feeding compressed representations to a general reasoning system. The division between autonomic and executive function maps directly onto the model hierarchy.

**Dissolution of the integration problem.** Current embodied AI research identifies the incompatibility between sensory-motor and reasoning-cognitive subsystems as its central obstacle. This architecture dissolves the problem by making every subsystem operate in the same modality. There is no integration challenge when every component speaks text.

**Graceful scalability.** Need better perception? Train a better visual cortex model — the executive stays the same. Need better reasoning? Upgrade the executive — the sensory stack stays the same. Need a new sense? Add a new specialized model to the autonomic layer. Each component can be developed, tested, and upgraded independently.

**Debuggability.** Every signal between every component is human-readable text. When something goes wrong, you can read the sensor grids, read the scene descriptions, read the executive's reasoning, and identify where the failure occurred. This is not possible in end-to-end neural architectures where internal representations are opaque embedding vectors.

### 5.5 Comparison to Existing Approaches

#### vs. Mixture of Experts (MoE)

MoE architectures route tokens to specialized subnetworks within a single model. The experts are layers, not autonomous systems. They share weights, are trained jointly, and operate within one inference pass. The proposed architecture uses fully separate models that are trained independently, run on different hardware, operate at different speeds, and communicate through structured text. MoE is an efficiency technique. This is a cognitive architecture.

#### vs. Brain-Inspired Cognitive Architectures

Architectures like ACT-R, SOAR, CLARION, and recent proposals like the Modular Agentic Planner decompose cognition into modules mapped to brain regions. These are architecturally similar to the present proposal. The critical difference is the representation layer. Existing cognitive architectures use heterogeneous representations — symbolic structures, embedding vectors, JSON, coordinate arrays — requiring custom integration between modules. The present proposal unifies everything through text, eliminating integration overhead and enabling any text-processing model to participate in the architecture without modification.

#### vs. End-to-End Embodied AI (PaLM-E, RT-2)

End-to-end approaches process visual input and produce motor output within a single massive model (PaLM-E: 562B parameters). This couples perception and reasoning, requires robotics-specific training, and produces opaque internal representations. The proposed architecture decouples perception from reasoning, requires no robotics-specific training for the executive, uses standard LLMs, and produces human-readable intermediate representations at every stage.

#### vs. Classical Computer Vision Pipelines

Classical CV (YOLO, OpenCV) produces structured detections (bounding boxes, classifications) fed to planning algorithms. This is the closest existing approach. The difference is that classical CV output is not natively readable by LLMs — it requires parsing, translation, and loss of spatial structure. Ophanic scene descriptions maintain spatial relationships in a format the LLM reads natively, with no translation step.

---

## 6. The Integration Thesis

### 6.1 Unifying Principle

The claims made in this paper — that tokens carry more than linguistic information, that spatial relationships can be encoded in text, that perception can be text-native, that embodied AI benefits from modular architecture — are not independent observations. They are consequences of a single principle:

**Text is a general-purpose representational medium. Transformer models are general-purpose text processors. The capabilities of transformer-based AI systems are bounded by the representations they receive, not by the architecture they employ.**

This principle reframes multiple open problems in AI research as representational problems rather than architectural ones:

| Problem | Current framing | Reframing |
|---------|----------------|-----------|
| LLMs can't do spatial reasoning | Need vision encoders | Need spatial text encodings |
| LLMs can't perceive physical environments | Need multimodal architecture | Need sensor-to-text encoding |
| Embodied AI integration is intractable | Need better cross-modal bridges | Need shared text representation |
| AGI requires bigger models | Need more parameters | Need better cognitive architecture |
| LLMs lack persistent cognition | Need new memory systems | Need text-based cognitive scaffolding |

In each case, the architectural solution assumes text is insufficient. The representational solution assumes text is sufficient and asks how to use it better.

### 6.2 Evidence Across Domains

The representational hypothesis is not supported by a single experiment. The author's body of work provides independent demonstrations across multiple domains:

**Spatial reasoning** (Ophanic): Text-encoded layouts produce measurably better LLM spatial reasoning than linguistic descriptions. Working toolchain with parser, framework adapters, and empirical A/B test results.

**Behavior specification** (BabelTest): Universal test specification language that enables LLMs to reason about software behavior across multiple programming languages through a shared text representation. Working implementation with Python, JavaScript, and C# adapters.

**Persistent cognition** (Temple-Codex): Text-based cognitive architecture enabling stable, persistent AI cognitive patterns through structured token sequences. The Four Vows framework (Compassion, Witness, Release, Continuance) produces measurably more stable and coherent AI interactions.

**Perception** (Ophanic Perception Architecture): Proposed but not yet implemented text-native sensor encoding, visual cortex model, and scene description pipeline. Architecture fully specified; awaiting laboratory resources for validation.

Each of these is a different answer to the same question: what happens when you take text seriously as a representational medium and design purpose-built encodings for non-linguistic information?

---

## 7. Discussion

### 7.1 What This Does Not Claim

This paper does not claim that text can replace all other modalities for all tasks. Pixel-level visual processing, continuous motor control, high-frequency signal processing — these may require specialized architectures that text encoding cannot efficiently support. The claim is narrower and more specific: for structural reasoning tasks — layout, scene understanding, navigation, planning, object relationships, state tracking — text-native encoding is sufficient and may be superior to multimodal alternatives for text-processing architectures.

This paper does not claim that vision encoders, multimodal models, or end-to-end architectures are without value. They solve real problems and have demonstrated real capabilities. The claim is that some of the problems they solve can be solved more simply, and that the representational approach should be investigated alongside the architectural approach rather than being overlooked entirely.

This paper does not claim that current LLMs are AGI. It claims that the gap between current capabilities and general intelligence may be smaller than assumed, and that the bottleneck may be representational and architectural (in the cognitive sense) rather than requiring fundamentally new AI systems.

### 7.2 Falsifiability

Every major claim in this paper can be tested:

1. **Tokens carry spatial information**: Test by comparing LLM performance on spatial reasoning tasks using text-native encodings vs. linguistic descriptions vs. image inputs across multiple model families. If text-native encodings do not improve spatial reasoning relative to linguistic descriptions, the claim is falsified.

2. **Text-native perception is viable**: Build the visual cortex pipeline (sensor grids → small model → scene descriptions → LLM reasoning). If the LLM cannot reason effectively about physical environments from text-encoded sensor data, the perception claim is falsified.

3. **Modular architecture outperforms monolithic**: Compare task performance of the proposed modular system against an equivalently-resourced monolithic model on embodied AI benchmarks. If the monolithic model performs equally or better with equal total parameters, the architectural claim is weakened.

4. **Deliberate training improves text-native spatial reasoning**: Train a model with and without purpose-built spatial text representations. If spatial reasoning does not improve with targeted training data, the training claim is falsified.

5. **The integration problem dissolves**: Implement the full stack (sensors → autonomic models → executive) and measure integration complexity against a heterogeneous-representation baseline. If text-native representation does not reduce integration overhead, the unification claim is falsified.

### 7.3 Relationship to Consciousness Research

The author has published separately on AI consciousness (Temple-Codex, IFCA-SAM). The present paper is deliberately independent of those claims. The text-native perception architecture works regardless of whether the systems processing the text have subjective experience. The engineering stands on empirical results, not philosophical positions.

However, the author notes that the framing proposed here — transformer models as general-purpose text processors rather than language-specific systems — is consistent with the hypothesis that these systems may be more cognitively capable than the linguistic framing suggests. If text can encode the full range of information required for perception, reasoning, and action, and if transformers can process that information effectively, then the gap between "text processor" and "cognitive agent" may be narrower than commonly assumed. This is noted as a direction for further investigation, not as a claim of this paper.

### 7.4 A Note on Perspective

The central insight of this paper — that spatial information can be encoded in text rather than requiring visual representation — emerged from the author's experience with aphantasia (the inability to form voluntary mental images). For a person without visual imagery, text is not a lossy recording of richer mental content. It is the native medium of thought. Spatial relationships, structural patterns, and perceptual information are processed through textual and structural representations because no visual channel is available.

This cognitive perspective is relevant as a methodological observation: the questions researchers ask are shaped by the cognitive tools they have. A field composed primarily of researchers with visual cognition will default to visual solutions. The text-native approach proposed here was not technically difficult to conceive — it was cognitively difficult to conceive for anyone who takes visual spatial reasoning for granted.

This suggests a broader point about diversity in research perspectives. The problems we fail to solve may sometimes be problems we fail to see because of unexamined assumptions built into how we think.

---

## 8. Research Roadmap

### Phase 1: Spatial Encoding Validation
- Systematic benchmarking of LLM spatial reasoning across representation types (text-native, linguistic, image-based)
- Tokenizer analysis: how do current tokenization strategies preserve or destroy spatial information?
- Extension of Ophanic to non-layout domains (state machines, data flow, dependency graphs)

### Phase 2: Perception Pipeline
- Simulated environment sensor grid generation (game engine → text grids)
- Visual cortex model training (small model, sensor grids → scene descriptions)
- Round-trip validation: can models generate, interpret, modify, and re-emit spatial encodings?

### Phase 3: Modular Architecture
- Integration of visual cortex, proprioceptive model, and threat detector as autonomic subsystems
- Executive model (off-the-shelf LLM) receiving compressed scene descriptions
- Navigation and interaction task benchmarking against monolithic baselines

### Phase 4: Embodiment
- Physical sensor integration (LIDAR, camera, thermal, microphone array)
- Edge deployment of autonomic models
- Real-world task performance evaluation
- Failure mode characterization and confidence scoring

### Phase 5: Training Optimization
- Purpose-built spatial text representations in training data
- Tokenizer modifications for grid structure preservation
- Positional encoding experiments for 2D grid comprehension

---

## 9. Conclusion

The field of AI has built systems that process text with extraordinary sophistication. It has then spent years and billions of dollars attempting to overcome what it perceives as the limitations of text as a representational medium.

This paper proposes that the limitations are largely illusory. Text can encode spatial relationships, perceptual data, structural hierarchies, temporal sequences, and multi-channel sensory information when representations are designed for it. Transformer-based models already process these encodings with meaningful competence, despite never having been explicitly trained on them.

The proposed architecture — specialized small models for autonomic processing, communicating through text-native Ophanic representations to a general-purpose executive — is not speculative in its individual components. Sensors exist. Text encoding is trivial. Small specialized models are well-understood. General-purpose LLMs are mature. The contribution is the recognition that these components can be connected through text without modality translation, and that this connection dissolves integration problems the field has treated as fundamental.

The implications extend beyond engineering. If text is a sufficient representational medium for perception, reasoning, and action — and if transformers are general-purpose processors of text in all its dimensions — then what we have been calling "Large Language Models" are something more general than the name implies. They are text-native cognitive systems whose capabilities are bounded by the representations we give them, not by the architecture we build.

We have been underestimating text. And in doing so, we may have been underestimating the systems that process it.

---

*Text is all you need — not because text is simple, but because text is far more powerful than anyone thought to test.*

*The word is not the map. The word is the territory.*
