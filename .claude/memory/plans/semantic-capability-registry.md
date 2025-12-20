---
name: Semantic Capability Registry for State Bus
summary: Auto-discovery of queryable source capabilities with LLM-generated summaries and semantic matching for natural language capability lookup
created: 2025-12-19
updated: 2025-12-19
resolved: 2025-12-19
status: COMPLETE
---

# Semantic Capability Registry for State Bus

## Goal

Each subprocess reports its capabilities with query/data schemas, auto-updates when capabilities change, and provides semantic summaries so the state bus can find relevant capabilities via natural language.

## Requirements

1. **Self-describing sources**: Each source reports full capability schema
2. **Automatic registration**: Schemas update when sources change
3. **Semantic summaries**: Local LLM generates 1-2 sentence summaries per metric
4. **Relevance matching**: State bus finds capabilities by semantic similarity

## Design

### Enhanced MetricDefinition

```python
@dataclass
class MetricDefinition:
    name: str
    description: str
    data_type: str
    supports_delta: bool = False
    supports_timeseries: bool = False
    unit: Optional[str] = None
    # NEW fields:
    semantic_summary: Optional[str] = None  # LLM-generated, embedding-ready
    example_queries: List[str] = field(default_factory=list)  # Natural language examples
    tags: List[str] = field(default_factory=list)  # Categorical tags for filtering
```

### CapabilityRegistry (new class in state_bus.py)

```python
class CapabilityRegistry:
    """
    Maintains semantic index of all source capabilities.
    Uses ChromaDB for embedding storage and similarity search.
    """

    def __init__(self, daemon_id: str, chroma_client):
        self._daemon_id = daemon_id
        self._collection = chroma_client.get_or_create_collection("capabilities")
        self._ollama_model = "llama3.1:8b"  # For summary generation

    async def register_source(self, source: QueryableSource) -> None:
        """Index all metrics from a source with embeddings."""
        for metric in source.schema.metrics:
            # Generate semantic summary if not provided
            if not metric.semantic_summary:
                metric.semantic_summary = await self._generate_summary(
                    source.source_id, metric
                )

            # Store in ChromaDB with embedding
            self._collection.upsert(
                ids=[f"{source.source_id}:{metric.name}"],
                documents=[metric.semantic_summary],
                metadatas=[{
                    "source": source.source_id,
                    "metric": metric.name,
                    "data_type": metric.data_type,
                    "tags": ",".join(metric.tags),
                }]
            )

    async def find_capabilities(self, query: str, limit: int = 5) -> List[Dict]:
        """Find relevant capabilities by semantic similarity."""
        results = self._collection.query(
            query_texts=[query],
            n_results=limit
        )
        return self._format_results(results)

    async def _generate_summary(self, source_id: str, metric: MetricDefinition) -> str:
        """Use local LLM to generate semantic summary."""
        prompt = f"""Generate a 1-2 sentence summary for this metric that would help someone find it via natural language search.

Source: {source_id}
Metric: {metric.name}
Description: {metric.description}
Type: {metric.data_type}
Unit: {metric.unit or 'none'}

Summary:"""
        # Call Ollama
        ...
```

### State Bus Integration

```python
class GlobalStateBus:
    def __init__(self, daemon_id: str):
        # ... existing init ...
        self._capability_registry = None  # Lazy init when ChromaDB ready

    def register_source(self, source: QueryableSource) -> None:
        # ... existing registration ...

        # Index capabilities for semantic search
        if self._capability_registry:
            asyncio.create_task(
                self._capability_registry.register_source(source)
            )

    async def find_capabilities(self, natural_query: str) -> List[Dict]:
        """Find relevant sources/metrics by natural language."""
        if not self._capability_registry:
            return []
        return await self._capability_registry.find_capabilities(natural_query)

    def describe_capabilities_for_llm(self) -> str:
        """Generate natural language description of all capabilities."""
        ...
```

### New Tool: discover_capabilities

```python
{
    "name": "discover_capabilities",
    "description": "Find what data is available to query by describing what you're looking for",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language description of what data you want"
            }
        },
        "required": ["query"]
    }
}
```

Example usage:
- "What data do we have about user engagement?" → Returns github:views, github:clones, github:stars
- "How much are we spending?" → Returns tokens:cost_usd
- "Repository activity metrics" → Returns github:clones, github:forks, github:views

## Implementation Order

1. **Enhance MetricDefinition** - Add semantic_summary, example_queries, tags fields
2. **Create CapabilityRegistry** - ChromaDB-backed semantic index
3. **Summary generation** - Ollama integration for auto-generating summaries
4. **State bus integration** - Wire registry into source registration
5. **discover_capabilities tool** - Natural language capability lookup for Cass
6. **Admin API** - Endpoint for viewing/refreshing capability index

## Files to Modify

| File | Change |
|------|--------|
| `backend/query_models.py` | Enhance MetricDefinition with semantic fields |
| `backend/state_bus.py` | Add CapabilityRegistry integration |
| `backend/capability_registry.py` | NEW: Semantic capability indexing |
| `backend/handlers/state_query.py` | Add discover_capabilities handler |
| `backend/agent_client.py` | Add discover_capabilities tool |
| `backend/main_sdk.py` | Initialize registry with ChromaDB |

## Open Questions

- Should summaries be regenerated periodically or only on source change?
- Store embeddings in existing ChromaDB or separate collection?
- Include query examples in semantic matching?

## Implementation Summary

### Files Created
- `backend/capability_registry.py` - CapabilityRegistry class with ChromaDB integration and Ollama summary generation

### Files Modified
- `backend/query_models.py` - Enhanced MetricDefinition with semantic_summary, example_queries, tags fields
- `backend/state_bus.py` - Added set_capability_registry, find_capabilities, list_all_capabilities methods
- `backend/handlers/state_query.py` - Added execute_discover_capabilities handler and DISCOVER_CAPABILITIES_TOOL_DEFINITION
- `backend/agent_client.py` - Added discover_capabilities tool with capability discovery keywords
- `backend/main_sdk.py` - Initialize CapabilityRegistry after heavy components, route discover_capabilities tool
- `backend/routes/admin/state.py` - Added /state/capabilities and /state/capabilities/search endpoints

### Key Decisions Made
- Registry initialized lazily after ChromaDB is ready (in _init_heavy_components)
- Separate ChromaDB collection per daemon: `capabilities_{daemon_id}`
- Automatic semantic summary generation via Ollama when not provided
- CapabilityMatch dataclass for structured results
- Similarity score calculated as 1/(1+distance) from ChromaDB L2 distance
