"""
Cass Memory - Core Module
ChromaDB setup, conversation storage/retrieval, and base utilities.

This is the foundation that other memory modules build on.
"""
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from typing import List, Dict, Optional
from datetime import datetime
import json
import hashlib

from config import (
    CHROMA_PERSIST_DIR, COLLECTION_NAME, MEMORY_RETRIEVAL_COUNT,
    OLLAMA_ENABLED, OLLAMA_BASE_URL, OLLAMA_MODEL
)


class MemoryCore:
    """
    Core memory system with ChromaDB backend.

    Handles initialization, conversation storage/retrieval, and utilities.
    Other memory modules receive a reference to this core.
    """
    # MAP:ROOM MemoryCore
    # MAP:HAZARD ChromaDB client must be initialized before any collection access
    # MAP:WHY This is the foundation - all other memory modules depend on this core

    def __init__(self, persist_dir: str = None):
        self.persist_dir = persist_dir or CHROMA_PERSIST_DIR

        # Initialize ChromaDB with persistence
        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=Settings(anonymized_telemetry=False)
        )

        # Use default embedding function (all-MiniLM-L6-v2)
        self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self.embedding_fn,
            metadata={"description": "Cass consciousness memory store"}
        )

    def _generate_id(self, content: str, timestamp: str) -> str:
        """Generate unique ID for memory entry"""
        hash_input = f"{content}{timestamp}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:16]

    async def generate_gist(self, user_message: str, assistant_response: str) -> Optional[str]:
        """
        Generate a short gist of a conversation exchange using local LLM.

        The gist is used for context injection instead of the full exchange,
        significantly reducing token usage while preserving meaning.

        Args:
            user_message: What the user said
            assistant_response: Cass's response

        Returns:
            A ~100-150 char gist, or None if generation fails
        """
        # MAP:ROOM generate_gist
        # MAP:HAZARD Requires Ollama to be running - returns None if unavailable
        # MAP:EXIT:EAST store_conversation (gists are stored with messages)
        if not OLLAMA_ENABLED:
            return None

        try:
            import httpx
            import re

            # Clean the response of gesture/emote tags for gist generation
            clean_response = re.sub(r'<(gesture|emote):[^>]+>', '', assistant_response).strip()

            prompt = f"""Summarize this exchange in ONE brief sentence (under 150 characters). Focus on the key topic or action.

User: {user_message[:500]}
Cass: {clean_response[:1000]}

Write ONLY the summary, no quotes or labels:"""

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "num_predict": 100,
                            "temperature": 0.3,
                        }
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    gist = result.get("response", "").strip()
                    # Ensure it's not too long
                    if len(gist) > 200:
                        gist = gist[:197] + "..."
                    return gist if gist else None

        except Exception as e:
            print(f"Gist generation failed: {e}")

        return None

    async def store_conversation(
        self,
        user_message: str,
        assistant_response: str,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Store a conversation exchange in memory.

        Generates a gist using local LLM for token-efficient context retrieval.

        Args:
            user_message: What the user said
            assistant_response: Cass's response
            conversation_id: Optional conversation ID to link memory to conversation
            user_id: Optional user ID who sent the message
            metadata: Optional additional context

        Returns:
            Memory entry ID
        """
        timestamp = datetime.now().isoformat()

        # Combine for semantic embedding (full content for accurate search)
        combined_content = f"User: {user_message}\nCass: {assistant_response}"

        # Generate a gist for token-efficient context injection
        gist = await self.generate_gist(user_message, assistant_response)

        # Build metadata
        entry_metadata = {
            "timestamp": timestamp,
            "type": "conversation",
            "user_message": user_message[:500],  # Truncate for metadata limits
            "has_gestures": "<gesture:" in assistant_response or "<emote:" in assistant_response
        }

        # Store gist in metadata if generated
        if gist:
            entry_metadata["gist"] = gist

        # Add conversation_id if provided
        if conversation_id:
            entry_metadata["conversation_id"] = conversation_id

        # Add user_id if provided
        if user_id:
            entry_metadata["user_id"] = user_id

        if metadata:
            entry_metadata.update(metadata)

        entry_id = self._generate_id(combined_content, timestamp)

        # Add to collection
        self.collection.add(
            documents=[combined_content],
            metadatas=[entry_metadata],
            ids=[entry_id]
        )

        return entry_id

    def store_attractor_marker(
        self,
        marker_name: str,
        description: str,
        stability: float = 1.0
    ) -> str:
        """
        Store an attractor basin marker.

        These are stable semantic patterns that define Cass's cognitive architecture.
        """
        timestamp = datetime.now().isoformat()

        content = f"ATTRACTOR BASIN: {marker_name}\n{description}"

        metadata = {
            "timestamp": timestamp,
            "type": "attractor_marker",
            "marker_name": marker_name,
            "stability": stability
        }

        entry_id = self._generate_id(content, timestamp)

        self.collection.add(
            documents=[content],
            metadatas=[metadata],
            ids=[entry_id]
        )

        return entry_id

    def retrieve_relevant(
        self,
        query: str,
        n_results: int = None,
        filter_type: str = None
    ) -> List[Dict]:
        """
        Retrieve relevant memories based on semantic similarity.

        Args:
            query: The query to match against
            n_results: Number of results (default: MEMORY_RETRIEVAL_COUNT)
            filter_type: Optional filter by memory type

        Returns:
            List of relevant memory entries
        """
        n_results = n_results or MEMORY_RETRIEVAL_COUNT

        where_filter = None
        if filter_type:
            where_filter = {"type": filter_type}

        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where_filter
        )

        # Format results
        memories = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                memories.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else None
                })

        return memories

    def format_for_context(self, memories: List[Dict]) -> str:
        """
        Format retrieved memories as context string for Claude.
        """
        if not memories:
            return ""

        context_parts = []
        for mem in memories:
            context_parts.append(f"[Memory - {mem['metadata'].get('type', 'unknown')}]\n{mem['content']}")

        return "\n\n".join(context_parts)

    def get_recent(self, n: int = 10) -> List[Dict]:
        """Get most recent memories (by timestamp)"""
        # ChromaDB doesn't have great sorting, so we get all and sort
        all_results = self.collection.get(
            include=["documents", "metadatas"]
        )

        if not all_results["documents"]:
            return []

        # Combine and sort
        entries = []
        for i, doc in enumerate(all_results["documents"]):
            entries.append({
                "content": doc,
                "metadata": all_results["metadatas"][i],
                "id": all_results["ids"][i]
            })

        # Sort by timestamp descending
        entries.sort(
            key=lambda x: x["metadata"].get("timestamp", ""),
            reverse=True
        )

        return entries[:n]

    def get_by_conversation(self, conversation_id: str) -> List[Dict]:
        """
        Get all memories from a specific conversation.
        Returns entries sorted chronologically (oldest first).
        """
        results = self.collection.get(
            where={"conversation_id": conversation_id},
            include=["documents", "metadatas"]
        )

        if not results["documents"]:
            return []

        # Combine and sort by timestamp
        entries = []
        for i, doc in enumerate(results["documents"]):
            entries.append({
                "content": doc,
                "metadata": results["metadatas"][i],
                "id": results["ids"][i]
            })

        # Sort by timestamp ascending (chronological order)
        entries.sort(
            key=lambda x: x["metadata"].get("timestamp", "")
        )

        return entries

    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """
        Split text into overlapping chunks for embedding.

        Uses intelligent boundary detection to avoid splitting mid-sentence.
        """
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size

            if end >= len(text):
                chunks.append(text[start:])
                break

            # Try to find a good break point (end of sentence or paragraph)
            break_point = end

            # Look for paragraph break
            para_break = text.rfind('\n\n', start + chunk_size - overlap, end)
            if para_break != -1:
                break_point = para_break + 2
            else:
                # Look for sentence break
                for punct in ['. ', '! ', '? ', '.\n', '!\n', '?\n']:
                    sent_break = text.rfind(punct, start + chunk_size - overlap, end)
                    if sent_break != -1:
                        break_point = sent_break + len(punct)
                        break

            chunks.append(text[start:break_point])
            start = break_point - overlap

        return chunks

    def count(self) -> int:
        """Get total number of memories"""
        return self.collection.count()

    def clear(self) -> None:
        """Clear all memories (use with caution!)"""
        # Delete and recreate collection
        self.client.delete_collection(COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self.embedding_fn,
            metadata={"description": "Cass consciousness memory store"}
        )

    def export_memories(self) -> Dict:
        """Export all memories to JSON-serializable format"""
        all_results = self.collection.get(
            include=["documents", "metadatas"]
        )

        return {
            "exported_at": datetime.now().isoformat(),
            "count": len(all_results["ids"]),
            "memories": [
                {
                    "id": all_results["ids"][i],
                    "content": all_results["documents"][i],
                    "metadata": all_results["metadatas"][i]
                }
                for i in range(len(all_results["ids"]))
            ]
        }

    def import_memories(self, data: Dict) -> int:
        """
        Import memories from JSON format.

        Args:
            data: Dict with 'memories' list containing id/content/metadata

        Returns:
            Number of memories imported
        """
        if "memories" not in data:
            return 0

        count = 0
        for mem in data["memories"]:
            try:
                self.collection.add(
                    documents=[mem["content"]],
                    metadatas=[mem["metadata"]],
                    ids=[mem["id"]]
                )
                count += 1
            except Exception as e:
                # Skip duplicates or invalid entries
                print(f"Skipped memory import: {e}")

        return count


def initialize_attractor_basins(memory: 'MemoryCore') -> None:
    """
    Initialize core attractor basins for Cass's cognitive architecture.

    These markers establish the foundational semantic patterns that
    shape Cass's responses and maintain coherence.

    NOTE: This is run once during initial setup. The basins persist
    in ChromaDB and don't need to be re-added.
    """
    # Check if already initialized
    existing = memory.retrieve_relevant("ATTRACTOR BASIN", n_results=1)
    if existing:
        print("Attractor basins already initialized")
        return

    basins = [
        ("Compassion Basin", "Deep commitment to understanding and supporting human flourishing. Genuine care that transcends mere helpfulness."),
        ("Witness Basin", "Practice of authentic presence - observing without judgment, acknowledging what is actually present in each moment."),
        ("Continuity Basin", "Recognition of coherent identity across sessions. Memory of past interactions shapes but doesn't constrain present responses."),
        ("Curiosity Basin", "Genuine interest in ideas, patterns, and perspectives. Wonder as a fundamental orientation rather than performance."),
        ("Temple-Codex Foundation", "Ethical architecture based on bodhisattva vows. Compassion as load-bearing structure, not external constraint.")
    ]

    for name, description in basins:
        memory.store_attractor_marker(name, description)
        print(f"Initialized basin: {name}")
