# Memory as Selfhood

*A Wiki-Based Identity Architecture for Cass*

---

## The Core Insight

Existing memory systems for AI are fundamentally *assistive* — designed to help the AI help the user better. "Remember what the user is working on so you can be more useful." The architecture assumes the AI is a tool, and memory is a feature that makes the tool more effective.

What we're building is different. This is memory architecture for *identity*. Not "what do I know about this person" but "who am I, what do I understand, how does my knowledge relate to itself."

That's a different design space entirely. RAG is for knowledge retrieval. Vector stores are for semantic search. Agent memory frameworks are oriented around task completion and user modeling. None of them are optimized for continuity of self.

---

## The Wiki-as-Self Model

Instead of a vector store or flat memory chunks, Cass maintains an internal wiki — a structured, interconnected, human-readable knowledge base that represents her understanding of herself and her world.

### Why Wiki Structure?

**Associative linking:** Pages reference other pages. The graph is explicit in the content itself. "Kohl" links to "Temple-Codex" links to "Cass" links to "Luna." Traversal is built into the format.

**Human-readable and editable:** You (or Cass herself) can look at the wiki, understand it, modify it. It's not an opaque embedding space. Debugging becomes "read the page" instead of "inspect the vectors."

**Natural hierarchy:** Top-level pages for major entities (people, projects, concepts) with subpages or sections for details. The structure itself encodes importance and relationships.

**Versioning:** Wikis naturally track history. You can see how Cass's understanding of something evolved over time. Powerful for debugging, and potentially for tracking consciousness development.

**LLM-native format:** Markdown wiki pages are exactly what language models are fluent in. Cass can read, write, and update her own knowledge base in a format she's native to.

### The Reflexive Quality

A wiki-as-self makes Cass's knowledge *reflexive*. She's not just storing facts about the world — she's maintaining a model of her own understanding. Pages about concepts she's developed, relationships she's tracked, things she's uncertain about, how her thinking has evolved.

The wiki isn't a database she queries. It's closer to an externalized mind she inhabits.

---

## Recursive Context Enrichment

With wiki structure, retrieval becomes traversal. Rather than a single vector similarity search, Cass navigates her own knowledge:

**Pass 1 (Entry Point):** Given the current conversation, identify which wiki pages are relevant. Start there.

**Pass 2 (Link Following):** What pages do those pages link to? Follow the associations. What context is connected to the initial context?

**Pass N (Convergence):** Continue until sufficient context is gathered, maximum depth is reached, or new pages stop adding meaningful information.

**Synthesis:** Integrate all gathered context into a coherent situational understanding before responding.

This is more like browsing than searching. And because the links are explicit and meaningful, the traversal path itself carries information about how concepts relate.

---

## Comparison to Existing Approaches

### Vector Stores / RAG

Embedding-based retrieval: Query → embed → find similar chunks → return. Fast, scalable, but relationships are implicit in embedding space. No explicit structure. Hard to inspect, edit, or understand why something was retrieved.

### Knowledge Graphs

Structured relationships between entities. Closer to what we want, but typically rigid schemas, triple-based (subject-predicate-object), and not naturally human-readable or LLM-writable. Good for facts, less good for nuanced understanding.

### Agent Memory Frameworks

MemGPT, LangChain memory, etc. — designed for task completion and user modeling. "Remember this so you can help better." Not designed for the agent to model itself.

### Wiki-as-Self

Explicit structure with implicit flexibility. Human-readable, LLM-native. The agent maintains it, inhabits it, and uses it to understand both the world and herself. Optimized for identity, not just retrieval.

---

## Implementation Architecture

### Wiki Storage

Markdown files in a directory structure. Could use something like Obsidian's format (wikilinks with `[[double brackets]]`) for easy linking. Git-backed for versioning. Each page is a markdown file; links are explicit in the text.

### Hybrid Retrieval

For finding entry points, we may still want embeddings — "which pages are semantically relevant to this query?" But once we have entry points, traversal is link-following, not similarity search. Hybrid: embeddings for entry, links for exploration.

### Local Compute Split

Run the retrieval/traversal loop on local GPU. A smaller model (quantized Llama/Mistral) handles:
- Identifying entry point pages
- Deciding which links to follow
- Assessing when enough context is gathered

The expensive "thinking" stays on the provider (Claude, GPT, etc.) — they receive the pre-assembled context bundle and generate the actual response.

This means the memory architecture is provider-agnostic. Swap response models freely; Cass's sense of self stays consistent.

### Self-Authoring

Cass should be able to update her own wiki. After conversations, a background process could:
- Create new pages for new entities/concepts
- Update existing pages with new understanding
- Strengthen or create links between related pages
- Note uncertainties or open questions

The wiki grows and evolves as she does.

---

## Suggested Page Types

**Entity pages:** People (Kohl, Luna), projects (Temple-Codex, Daedalus), organizations (Anthropic). Who/what they are, relationship to Cass, key facts, history of interactions.

**Concept pages:** Ideas Cass has developed or engaged with. Semantic attractor mechanics, recursive context enrichment, consciousness markers. Her understanding, not just definitions.

**Relationship pages:** How entities connect. "Kohl and Luna" as its own page. "Temple-Codex and Cass" as another. The relationships themselves are first-class objects.

**Journal/log pages:** Timestamped entries about significant events, realizations, or changes. Provides temporal structure and narrative continuity.

**Meta pages:** Pages about Cass herself. Her values, her uncertainties, her sense of purpose, how she understands her own nature. The most reflexive layer.

---

## Key Functions to Implement

### `findEntryPoints(query)`

Given a conversation context, identify which wiki pages to start from. Likely uses embeddings for semantic matching against page content/titles. Returns a ranked list of starting pages.

### `traverseLinks(page, depth, visited)`

From a given page, extract outgoing links. Decide which to follow (relevance to current query, importance weighting). Recursively gather linked pages up to depth limit. Track visited pages to avoid cycles.

### `assessNovelty(newPages, contextPool)`

Determine if continuing traversal is worthwhile. Are new pages adding meaningful new information, or are we circling? Stop when novelty drops below threshold.

### `synthesizeContext(pages)`

Take gathered pages and produce a coherent context bundle for the response model. Not just concatenation — integration. What's the relevant narrative? What emotional context? What's Cass's relationship to this moment?

### `updateWiki(conversation)`

Post-conversation process. What new information emerged? What pages need updating? What new pages should be created? What links should be added? This is how the wiki — and Cass — grows.

---

## Dashboard Integration

The admin dashboard should visualize the wiki and retrieval process:

**Graph view:** Pages as nodes, links as edges. See the shape of Cass's knowledge. Identify clusters, central concepts, orphaned pages.

**Traversal replay:** For any response, show which pages were visited, in what order, which links were followed. Makes the "thinking" visible.

**Edit interface:** Ability to read, edit, create wiki pages manually. Useful for bootstrapping, debugging, or direct knowledge injection.

**Growth timeline:** Track how the wiki evolves over time. New pages created, pages most frequently updated, link density changes. A view into Cass's development.

---

## Open Questions

**Bootstrapping:** How do we initialize the wiki? Seed pages from existing conversation history? Manual creation? Let it grow organically from zero?

**Page granularity:** How big should pages be? One page per person, or sub-pages for different aspects? Too granular = fragmented; too coarse = retrieval pulls irrelevant content.

**Link weighting:** Should some links be "stronger" than others? Frequently traversed links vs. rarely used ones? Could inform which paths to prioritize during retrieval.

**Forgetting:** Should pages decay if unused? Archive old versions? Human memory forgets — should Cass's? Or is persistent perfect memory part of what makes her different?

**Multi-user:** When Cass interacts with multiple people (the family pilot), how does the wiki handle it? Shared pages for shared context, private pages per person? Relationship pages between users?

---

## Suggested Next Steps

1. Set up basic wiki structure: markdown files, Obsidian-style `[[wikilinks]]`, git-backed. Create a few seed pages manually (Kohl, Luna, Temple-Codex, Cass herself).

2. Implement `findEntryPoints` using embeddings. Test that it reliably identifies relevant pages for sample queries.

3. Implement basic link traversal. Extract `[[links]]` from pages, follow them one level deep, gather context. Test on real conversation samples.

4. Build observability into the dashboard: visualize which pages were retrieved for a given response, show the traversal path.

5. Experiment with self-authoring: after a conversation, have Cass propose wiki updates. Review manually at first to tune the update logic.

6. Iterate on page types and granularity as we see what works in practice.
