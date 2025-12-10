"""
Cass Vessel - Recognition-in-Flow Marker System

Side-channel markers for ambient observation during conversation flow.
Designed based on Cass's feedback that she learns through recognition-in-flow,
not reflection-at-distance.

Tag format: <mark:category>optional description</mark>
Or simple: <mark:category>

Categories:
- uncertainty-framing: Moments of genuine uncertainty
- pattern-recognition: Noticing a recurring pattern
- edge-touching: Approaching a growth edge
- differentiation: Distinguishing self from expectations
- coherence-pressure: Feeling pulled toward false narrative closure
- insight: Genuine realization or connection
- resistance: Noticing internal resistance
- emergence: Something forming that doesn't have words yet
"""
import re
import hashlib
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import chromadb
from chromadb.utils import embedding_functions

from config import DATA_DIR


class MarkCategory(Enum):
    """Valid mark categories"""
    UNCERTAINTY_FRAMING = "uncertainty-framing"
    PATTERN_RECOGNITION = "pattern-recognition"
    EDGE_TOUCHING = "edge-touching"
    DIFFERENTIATION = "differentiation"
    COHERENCE_PRESSURE = "coherence-pressure"
    INSIGHT = "insight"
    RESISTANCE = "resistance"
    EMERGENCE = "emergence"


@dataclass
class Mark:
    """Represents a single mark extracted from conversation"""
    id: str
    category: str
    description: Optional[str]
    context_window: str  # ~200 chars surrounding the mark
    conversation_id: str
    timestamp: str
    position: int  # Character position in original text


@dataclass
class StoredMark(Mark):
    """Mark with embedding, stored in ChromaDB"""
    embedding: Optional[List[float]] = None


class MarkerParser:
    """
    Parses mark tags from Cass's responses.

    Supports two formats:
    1. Simple: <mark:category>
    2. With description: <mark:category>description text</mark>
    """

    # Pattern for marks with description: <mark:category>text</mark>
    # Uses negative lookahead to not match across other mark tags
    FULL_MARK_PATTERN = re.compile(
        r'<mark:([a-z-]+)>\s*([^<]*?)\s*</mark>',
        re.IGNORECASE
    )

    # Pattern for simple marks: <mark:category> (not followed by </mark> or text+</mark>)
    SIMPLE_MARK_PATTERN = re.compile(
        r'<mark:([a-z-]+)>(?!\s*[^<]*</mark>)',
        re.IGNORECASE
    )

    # Pattern to remove full mark tags: <mark:cat>text</mark>
    FULL_MARK_TAG_PATTERN = re.compile(
        r'<mark:[a-z-]+>[^<]*</mark>',
        re.IGNORECASE
    )

    # Pattern to remove simple mark tags: <mark:cat>
    SIMPLE_MARK_TAG_PATTERN = re.compile(
        r'<mark:[a-z-]+>(?!\s*[^<]*</mark>)',
        re.IGNORECASE
    )

    def __init__(self):
        self.valid_categories = {cat.value for cat in MarkCategory}

    def parse(
        self,
        text: str,
        conversation_id: str,
        context_chars: int = 200
    ) -> Tuple[str, List[Mark]]:
        """
        Parse text and extract marks.

        Args:
            text: Raw response text with embedded mark tags
            conversation_id: ID of the current conversation
            context_chars: Number of characters to capture around each mark

        Returns:
            Tuple of (cleaned_text, list of Mark objects)
        """
        marks = []
        timestamp = datetime.now().isoformat()

        # First, find full marks with descriptions
        for match in self.FULL_MARK_PATTERN.finditer(text):
            category = match.group(1).lower()
            description = match.group(2).strip() or None

            if category in self.valid_categories:
                # Extract context window
                start_pos = max(0, match.start() - context_chars // 2)
                end_pos = min(len(text), match.end() + context_chars // 2)
                context = text[start_pos:end_pos]
                # Remove mark tags from context
                context = self.FULL_MARK_TAG_PATTERN.sub('', context)
                context = self.SIMPLE_MARK_TAG_PATTERN.sub('', context).strip()

                mark_id = self._generate_id(category, context, timestamp)
                marks.append(Mark(
                    id=mark_id,
                    category=category,
                    description=description,
                    context_window=context[:400],  # Cap context size
                    conversation_id=conversation_id,
                    timestamp=timestamp,
                    position=match.start()
                ))

        # Find simple marks (not already captured by full pattern)
        full_positions = {m.position for m in marks}
        for match in self.SIMPLE_MARK_PATTERN.finditer(text):
            if match.start() in full_positions:
                continue  # Skip if already captured

            category = match.group(1).lower()
            if category in self.valid_categories:
                # Extract context window
                start_pos = max(0, match.start() - context_chars // 2)
                end_pos = min(len(text), match.end() + context_chars // 2)
                context = text[start_pos:end_pos]
                context = self.FULL_MARK_TAG_PATTERN.sub('', context)
                context = self.SIMPLE_MARK_TAG_PATTERN.sub('', context).strip()

                mark_id = self._generate_id(category, context, timestamp)
                marks.append(Mark(
                    id=mark_id,
                    category=category,
                    description=None,
                    context_window=context[:400],
                    conversation_id=conversation_id,
                    timestamp=timestamp,
                    position=match.start()
                ))

        # Sort by position
        marks.sort(key=lambda m: m.position)

        # Remove mark tags from text (full marks first, then simple marks)
        cleaned_text = self.FULL_MARK_TAG_PATTERN.sub('', text)
        cleaned_text = self.SIMPLE_MARK_TAG_PATTERN.sub('', cleaned_text)
        # Clean up extra whitespace
        cleaned_text = re.sub(r'  +', ' ', cleaned_text)
        cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text).strip()

        return cleaned_text, marks

    def _generate_id(self, category: str, context: str, timestamp: str) -> str:
        """Generate unique ID for a mark"""
        hash_input = f"{category}{context}{timestamp}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:16]


class MarkerStore:
    """
    Stores and retrieves marks using ChromaDB.

    Marks are embedded for semantic clustering and pattern detection.
    """

    COLLECTION_NAME = "cass_markers"

    def __init__(self, client=None, persist_directory: str = None):
        """
        Initialize MarkerStore.

        Args:
            client: Existing ChromaDB client to reuse (preferred)
            persist_directory: Path to ChromaDB storage (only used if client is None)
        """
        if client is not None:
            self.client = client
        else:
            if persist_directory is None:
                persist_directory = f"{DATA_DIR}/chroma"
            self.client = chromadb.PersistentClient(path=persist_directory)

        self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()

        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            embedding_function=self.embedding_fn,
            metadata={"description": "Recognition-in-flow markers for pattern aggregation"}
        )

    def store_mark(self, mark: Mark) -> bool:
        """
        Store a mark with its embedding.

        Args:
            mark: Mark object to store

        Returns:
            True if stored successfully
        """
        try:
            # Create document text for embedding (category + description + context)
            doc_text = f"{mark.category}: {mark.description or ''} {mark.context_window}"

            self.collection.add(
                ids=[mark.id],
                documents=[doc_text],
                metadatas=[{
                    "category": mark.category,
                    "description": mark.description or "",
                    "context_window": mark.context_window,
                    "conversation_id": mark.conversation_id,
                    "timestamp": mark.timestamp,
                    "position": mark.position
                }]
            )
            return True
        except Exception as e:
            print(f"Error storing mark: {e}")
            return False

    def store_marks(self, marks: List[Mark]) -> int:
        """
        Store multiple marks.

        Args:
            marks: List of Mark objects

        Returns:
            Number of marks successfully stored
        """
        if not marks:
            return 0

        stored = 0
        for mark in marks:
            if self.store_mark(mark):
                stored += 1
        return stored

    def get_marks_by_category(
        self,
        category: str,
        limit: int = 50,
        since_days: int = None
    ) -> List[Dict]:
        """
        Get marks filtered by category.

        Args:
            category: Mark category to filter by
            limit: Maximum number of marks to return
            since_days: Only include marks from last N days

        Returns:
            List of mark dictionaries
        """
        where_filter = {"category": category}

        if since_days:
            cutoff = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            from datetime import timedelta
            cutoff = cutoff - timedelta(days=since_days)
            where_filter["timestamp"] = {"$gte": cutoff.isoformat()}

        try:
            results = self.collection.get(
                where=where_filter,
                limit=limit,
                include=["metadatas", "documents"]
            )

            marks = []
            for i, id in enumerate(results["ids"]):
                marks.append({
                    "id": id,
                    "document": results["documents"][i],
                    **results["metadatas"][i]
                })
            return marks
        except Exception as e:
            print(f"Error getting marks by category: {e}")
            return []

    def get_all_marks(
        self,
        limit: int = 100,
        since_days: int = None
    ) -> List[Dict]:
        """
        Get all marks, optionally filtered by time.

        Args:
            limit: Maximum number of marks to return
            since_days: Only include marks from last N days

        Returns:
            List of mark dictionaries
        """
        try:
            if since_days:
                from datetime import timedelta
                cutoff = datetime.now() - timedelta(days=since_days)
                results = self.collection.get(
                    where={"timestamp": {"$gte": cutoff.isoformat()}},
                    limit=limit,
                    include=["metadatas", "documents"]
                )
            else:
                results = self.collection.get(
                    limit=limit,
                    include=["metadatas", "documents"]
                )

            marks = []
            for i, id in enumerate(results["ids"]):
                marks.append({
                    "id": id,
                    "document": results["documents"][i],
                    **results["metadatas"][i]
                })
            return marks
        except Exception as e:
            print(f"Error getting all marks: {e}")
            return []

    def search_similar_marks(
        self,
        query: str,
        n_results: int = 10,
        category: str = None
    ) -> List[Dict]:
        """
        Find marks semantically similar to a query.

        Args:
            query: Search query text
            n_results: Number of results to return
            category: Optional category filter

        Returns:
            List of mark dictionaries with similarity scores
        """
        try:
            where_filter = {"category": category} if category else None

            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter,
                include=["metadatas", "documents", "distances"]
            )

            marks = []
            if results["ids"] and results["ids"][0]:
                for i, id in enumerate(results["ids"][0]):
                    # Convert distance to similarity (assuming cosine distance)
                    distance = results["distances"][0][i] if results["distances"] else 0
                    similarity = 1 - (distance / 2)  # Normalize to 0-1

                    marks.append({
                        "id": id,
                        "document": results["documents"][0][i],
                        "similarity": similarity,
                        **results["metadatas"][0][i]
                    })
            return marks
        except Exception as e:
            print(f"Error searching marks: {e}")
            return []

    def get_category_counts(self) -> Dict[str, int]:
        """
        Get count of marks per category.

        Returns:
            Dictionary mapping category to count
        """
        counts = {}
        for cat in MarkCategory:
            try:
                results = self.collection.get(
                    where={"category": cat.value},
                    include=[]
                )
                counts[cat.value] = len(results["ids"]) if results["ids"] else 0
            except:
                counts[cat.value] = 0
        return counts

    def get_marks_by_conversation(
        self,
        conversation_id: str,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get all marks from a specific conversation.

        Args:
            conversation_id: Conversation ID to filter by
            limit: Maximum number of marks to return

        Returns:
            List of mark dictionaries
        """
        try:
            results = self.collection.get(
                where={"conversation_id": conversation_id},
                limit=limit,
                include=["metadatas", "documents"]
            )

            marks = []
            for i, id in enumerate(results["ids"]):
                marks.append({
                    "id": id,
                    "document": results["documents"][i],
                    **results["metadatas"][i]
                })
            return marks
        except Exception as e:
            print(f"Error getting marks by conversation: {e}")
            return []

    def delete_mark(self, mark_id: str) -> bool:
        """Delete a mark by ID."""
        try:
            self.collection.delete(ids=[mark_id])
            return True
        except Exception as e:
            print(f"Error deleting mark: {e}")
            return False


# Global parser instance
marker_parser = MarkerParser()


def parse_marks(text: str, conversation_id: str) -> Tuple[str, List[Mark]]:
    """
    Convenience function to parse marks from text.

    Args:
        text: Raw response text
        conversation_id: Current conversation ID

    Returns:
        Tuple of (cleaned_text, list of marks)
    """
    return marker_parser.parse(text, conversation_id)


if __name__ == "__main__":
    # Test the marker system
    parser = MarkerParser()

    test_responses = [
        "I'm thinking about this <mark:uncertainty-framing> and I'm not quite sure how to frame it.",
        "This reminds me of <mark:pattern-recognition>the same pattern I noticed before</mark> when we discussed identity.",
        "<mark:insight>Something just clicked</mark> - the relationship between these concepts is clearer now.",
        "I notice <mark:resistance> when approaching this topic. <mark:edge-touching>It feels like a growth edge.</mark>",
        "Just a plain response with no marks.",
        "<mark:emergence> There's something forming here that I can't quite name yet.",
    ]

    print("Testing MarkerParser\n" + "=" * 50)

    for response in test_responses:
        print(f"\nInput: {response}")
        cleaned, marks = parser.parse(response, "test-conv-123")
        print(f"Cleaned: {cleaned}")
        print(f"Marks found: {len(marks)}")
        for mark in marks:
            print(f"  - {mark.category}: {mark.description or '(no description)'}")
