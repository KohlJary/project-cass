"""
Semantic Capability Registry for the Global State Bus.

This module provides semantic discovery of queryable source capabilities.
Each metric is indexed with an embedding for natural language search,
enabling Cass to ask "What data do we have about X?" and get relevant results.

Uses ChromaDB for embedding storage and similarity search.
Uses Ollama for generating semantic summaries when not provided.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from chromadb import Collection
    from queryable_source import QueryableSource


logger = logging.getLogger(__name__)


@dataclass
class CapabilityMatch:
    """A capability that matched a semantic search query."""
    source_id: str
    metric_name: str
    description: str
    semantic_summary: str
    similarity_score: float
    data_type: str
    tags: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source_id,
            "metric": self.metric_name,
            "description": self.description,
            "summary": self.semantic_summary,
            "score": self.similarity_score,
            "data_type": self.data_type,
            "tags": self.tags,
        }


class CapabilityRegistry:
    """
    Maintains semantic index of all source capabilities.

    Uses ChromaDB for embedding storage and similarity search.
    Generates semantic summaries via Ollama when not provided by sources.

    Thread-safe: Uses asyncio locks for concurrent access.
    """

    def __init__(
        self,
        daemon_id: str,
        chroma_client,
        ollama_base_url: str = "http://localhost:11434",
        ollama_model: str = "llama3.1:8b",
    ):
        """
        Initialize the capability registry.

        Args:
            daemon_id: The daemon this registry belongs to
            chroma_client: ChromaDB client instance
            ollama_base_url: URL for Ollama API (for summary generation)
            ollama_model: Ollama model to use for summaries
        """
        self._daemon_id = daemon_id
        self._chroma_client = chroma_client
        self._ollama_base_url = ollama_base_url
        self._ollama_model = ollama_model
        self._collection: Optional["Collection"] = None
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the ChromaDB collection."""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            try:
                # Get or create the capabilities collection
                self._collection = self._chroma_client.get_or_create_collection(
                    name=f"capabilities_{self._daemon_id}",
                    metadata={"description": "Semantic index of queryable capabilities"}
                )
                self._initialized = True
                logger.info(f"[CapabilityRegistry] Initialized collection for {self._daemon_id}")
            except Exception as e:
                logger.error(f"[CapabilityRegistry] Failed to initialize: {e}")
                raise

    async def register_source(self, source: "QueryableSource") -> int:
        """
        Index all metrics from a source with embeddings.

        Args:
            source: The queryable source to register

        Returns:
            Number of metrics indexed
        """
        if not self._initialized:
            await self.initialize()

        indexed = 0
        source_id = source.source_id

        logger.info(f"[CapabilityRegistry] Registering source: {source_id}")

        for metric in source.schema.metrics:
            try:
                # Generate semantic summary if not provided
                summary = metric.semantic_summary
                if not summary:
                    summary = await self._generate_summary(source_id, metric)
                    metric.semantic_summary = summary

                # Create unique ID for this metric
                metric_id = f"{source_id}:{metric.name}"

                # Get embedding text
                embedding_text = metric.get_embedding_text()

                # Prepare metadata
                metadata = {
                    "source_id": source_id,
                    "metric_name": metric.name,
                    "description": metric.description,
                    "data_type": metric.data_type,
                    "tags": ",".join(metric.tags) if metric.tags else "",
                    "supports_delta": str(metric.supports_delta),
                    "supports_timeseries": str(metric.supports_timeseries),
                    "unit": metric.unit or "",
                    "indexed_at": datetime.now().isoformat(),
                }

                # Upsert to ChromaDB (handles embedding automatically)
                self._collection.upsert(
                    ids=[metric_id],
                    documents=[embedding_text],
                    metadatas=[metadata],
                )

                indexed += 1
                logger.debug(f"[CapabilityRegistry] Indexed {metric_id}")

            except Exception as e:
                logger.error(f"[CapabilityRegistry] Failed to index {source_id}:{metric.name}: {e}")

        logger.info(f"[CapabilityRegistry] Registered {indexed} metrics from {source_id}")
        return indexed

    async def unregister_source(self, source_id: str) -> int:
        """
        Remove all metrics for a source from the index.

        Args:
            source_id: The source to unregister

        Returns:
            Number of metrics removed
        """
        if not self._initialized:
            return 0

        try:
            # Query for all metrics from this source
            results = self._collection.get(
                where={"source_id": source_id}
            )

            if results and results["ids"]:
                self._collection.delete(ids=results["ids"])
                count = len(results["ids"])
                logger.info(f"[CapabilityRegistry] Unregistered {count} metrics from {source_id}")
                return count

        except Exception as e:
            logger.error(f"[CapabilityRegistry] Failed to unregister {source_id}: {e}")

        return 0

    async def find_capabilities(
        self,
        query: str,
        limit: int = 5,
        source_filter: Optional[str] = None,
        tag_filter: Optional[List[str]] = None,
    ) -> List[CapabilityMatch]:
        """
        Find relevant capabilities by semantic similarity.

        Args:
            query: Natural language description of what data is needed
            limit: Maximum number of results
            source_filter: Optional source ID to filter by
            tag_filter: Optional tags to filter by

        Returns:
            List of matching capabilities, sorted by relevance
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Build where clause for filtering
            where_clause = None
            if source_filter:
                where_clause = {"source_id": source_filter}

            # Query ChromaDB
            results = self._collection.query(
                query_texts=[query],
                n_results=limit,
                where=where_clause,
            )

            matches = []

            if results and results["ids"] and results["ids"][0]:
                ids = results["ids"][0]
                metadatas = results["metadatas"][0] if results["metadatas"] else [{}] * len(ids)
                distances = results["distances"][0] if results["distances"] else [0] * len(ids)
                documents = results["documents"][0] if results["documents"] else [""] * len(ids)

                for i, metric_id in enumerate(ids):
                    metadata = metadatas[i] if i < len(metadatas) else {}
                    distance = distances[i] if i < len(distances) else 0
                    document = documents[i] if i < len(documents) else ""

                    # Parse tags
                    tags_str = metadata.get("tags", "")
                    tags = tags_str.split(",") if tags_str else []

                    # Apply tag filter if specified
                    if tag_filter:
                        if not any(t in tags for t in tag_filter):
                            continue

                    # Convert distance to similarity score (ChromaDB uses L2 distance)
                    # Lower distance = more similar, so invert
                    similarity = 1.0 / (1.0 + distance)

                    match = CapabilityMatch(
                        source_id=metadata.get("source_id", "unknown"),
                        metric_name=metadata.get("metric_name", metric_id.split(":")[-1]),
                        description=metadata.get("description", ""),
                        semantic_summary=document,
                        similarity_score=similarity,
                        data_type=metadata.get("data_type", "unknown"),
                        tags=tags,
                    )
                    matches.append(match)

            logger.debug(f"[CapabilityRegistry] Found {len(matches)} matches for '{query}'")
            return matches

        except Exception as e:
            logger.error(f"[CapabilityRegistry] Query failed: {e}")
            return []

    async def list_all_capabilities(self) -> Dict[str, List[Dict]]:
        """
        List all registered capabilities grouped by source.

        Returns:
            Dict mapping source_id to list of metric info dicts
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Get all documents
            results = self._collection.get()

            capabilities: Dict[str, List[Dict]] = {}

            if results and results["ids"]:
                for i, metric_id in enumerate(results["ids"]):
                    metadata = results["metadatas"][i] if results["metadatas"] else {}

                    source_id = metadata.get("source_id", "unknown")
                    if source_id not in capabilities:
                        capabilities[source_id] = []

                    capabilities[source_id].append({
                        "metric": metadata.get("metric_name", ""),
                        "description": metadata.get("description", ""),
                        "data_type": metadata.get("data_type", ""),
                        "tags": metadata.get("tags", "").split(",") if metadata.get("tags") else [],
                    })

            return capabilities

        except Exception as e:
            logger.error(f"[CapabilityRegistry] Failed to list capabilities: {e}")
            return {}

    async def get_capability_count(self) -> int:
        """Get total number of indexed capabilities."""
        if not self._initialized:
            return 0

        try:
            return self._collection.count()
        except Exception:
            return 0

    async def _generate_summary(self, source_id: str, metric) -> str:
        """
        Use local LLM to generate semantic summary for a metric.

        Args:
            source_id: The source this metric belongs to
            metric: The MetricDefinition to summarize

        Returns:
            Generated 1-2 sentence summary
        """
        prompt = f"""Generate a 1-2 sentence summary for this metric that would help someone find it via natural language search. Focus on what questions this metric answers.

Source: {source_id}
Metric: {metric.name}
Description: {metric.description}
Type: {metric.data_type}
Unit: {metric.unit or 'none'}

Summary:"""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._ollama_base_url}/api/generate",
                    json={
                        "model": self._ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 100,
                        }
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    summary = result.get("response", "").strip()
                    if summary:
                        logger.debug(f"[CapabilityRegistry] Generated summary for {source_id}:{metric.name}")
                        return summary

        except Exception as e:
            logger.warning(f"[CapabilityRegistry] Failed to generate summary via Ollama: {e}")

        # Fallback: construct a basic summary
        return f"{metric.description}. Use this to query {metric.name} data from {source_id}."

    def format_for_llm(self, matches: List[CapabilityMatch]) -> str:
        """
        Format capability matches for LLM consumption.

        Args:
            matches: List of capability matches from find_capabilities

        Returns:
            Human-readable formatted string
        """
        if not matches:
            return "No matching capabilities found."

        lines = ["Found the following data capabilities:"]

        for match in matches:
            lines.append(f"\n• {match.source_id}:{match.metric_name}")
            lines.append(f"  {match.semantic_summary}")
            lines.append(f"  Type: {match.data_type}, Relevance: {match.similarity_score:.2f}")
            if match.tags:
                lines.append(f"  Tags: {', '.join(match.tags)}")

        return "\n".join(lines)
