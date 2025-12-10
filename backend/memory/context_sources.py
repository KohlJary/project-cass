"""
Cass Memory - Context Sources
Project files, wiki pages, and user profile embeddings/retrieval.
"""
from typing import List, Dict, Optional
from datetime import datetime

from config import MEMORY_RETRIEVAL_COUNT
from .core import MemoryCore


class ContextSourceManager:
    """
    Manages external context sources embedded into memory.

    Handles project documents/files, wiki pages, and user profiles/observations.
    These provide Cass with knowledge about her working context and the people
    she interacts with.
    """

    def __init__(self, core: MemoryCore):
        self._core = core

    @property
    def collection(self):
        return self._core.collection

    # === Project File Methods ===

    def embed_project_file(
        self,
        project_id: str,
        file_path: str,
        file_description: Optional[str] = None
    ) -> int:
        """
        Read, chunk, and embed a project file.

        Args:
            project_id: ID of the project
            file_path: Path to the file
            file_description: Optional description of the file

        Returns:
            Number of chunks embedded
        """
        import os

        # Read file
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        if not content.strip():
            return 0

        # Get filename for context
        filename = os.path.basename(file_path)

        # Chunk the content
        chunks = self._core.chunk_text(content)

        # Embed each chunk
        timestamp = datetime.now().isoformat()

        for i, chunk in enumerate(chunks):
            # Build document with context
            doc_content = f"[Project File: {filename}]\n"
            if file_description:
                doc_content += f"[Description: {file_description}]\n"
            doc_content += f"[Chunk {i+1}/{len(chunks)}]\n\n{chunk}"

            # Metadata
            metadata = {
                "timestamp": timestamp,
                "type": "project_document",
                "project_id": project_id,
                "file_path": file_path,
                "filename": filename,
                "chunk_index": i,
                "total_chunks": len(chunks)
            }
            if file_description:
                metadata["file_description"] = file_description

            # Generate ID
            entry_id = self._core._generate_id(f"{file_path}:{i}", timestamp)

            # Add to collection
            self.collection.add(
                documents=[doc_content],
                metadatas=[metadata],
                ids=[entry_id]
            )

        return len(chunks)

    def embed_project_document(
        self,
        project_id: str,
        document_id: str,
        title: str,
        content: str
    ) -> int:
        """
        Chunk and embed a project document (markdown content stored in project).

        Args:
            project_id: ID of the project
            document_id: ID of the document
            title: Document title
            content: Markdown content

        Returns:
            Number of chunks embedded
        """
        if not content.strip():
            return 0

        # Chunk the content
        chunks = self._core.chunk_text(content)

        # Embed each chunk
        timestamp = datetime.now().isoformat()

        for i, chunk in enumerate(chunks):
            # Build document with context
            doc_content = f"[Project Document: {title}]\n"
            doc_content += f"[Chunk {i+1}/{len(chunks)}]\n\n{chunk}"

            # Metadata
            metadata = {
                "timestamp": timestamp,
                "type": "project_document",
                "project_id": project_id,
                "document_id": document_id,
                "document_title": title,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "is_internal_document": True  # Distinguishes from external files
            }

            # Generate ID
            entry_id = self._core._generate_id(f"doc:{document_id}:{i}", timestamp)

            # Add to collection
            self.collection.add(
                documents=[doc_content],
                metadatas=[metadata],
                ids=[entry_id]
            )

        return len(chunks)

    def remove_project_document_embeddings(self, project_id: str, document_id: str) -> int:
        """
        Remove all embeddings for a specific document.

        Args:
            project_id: ID of the project
            document_id: ID of the document

        Returns:
            Number of chunks removed
        """
        results = self.collection.get(
            where={
                "$and": [
                    {"project_id": project_id},
                    {"document_id": document_id}
                ]
            }
        )

        if not results["ids"]:
            return 0

        self.collection.delete(ids=results["ids"])

        return len(results["ids"])

    def remove_project_file_embeddings(self, project_id: str, file_path: str) -> int:
        """
        Remove all embeddings for a specific file.

        Args:
            project_id: ID of the project
            file_path: Path to the file

        Returns:
            Number of chunks removed
        """
        # Get all embeddings for this file
        results = self.collection.get(
            where={
                "$and": [
                    {"project_id": project_id},
                    {"file_path": file_path}
                ]
            }
        )

        if not results["ids"]:
            return 0

        # Delete them
        self.collection.delete(ids=results["ids"])

        return len(results["ids"])

    def remove_project_embeddings(self, project_id: str) -> int:
        """
        Remove all embeddings for a project.

        Args:
            project_id: ID of the project

        Returns:
            Number of entries removed
        """
        results = self.collection.get(
            where={"project_id": project_id}
        )

        if not results["ids"]:
            return 0

        self.collection.delete(ids=results["ids"])

        return len(results["ids"])

    def retrieve_project_context(
        self,
        query: str,
        project_id: str,
        n_results: int = None,
        max_distance: float = 1.5
    ) -> List[Dict]:
        """
        Retrieve relevant project documents for a query.

        Only returns documents that are semantically relevant (below max_distance threshold).
        This prevents loading project context when the query isn't related to any documents.

        Args:
            query: Search query
            project_id: Project to search within
            n_results: Number of results
            max_distance: Maximum distance threshold (lower = more similar).
                         Documents with distance > max_distance are excluded.
                         Default 1.5 based on testing: relevant queries ~1.1-1.4,
                         irrelevant queries ~1.7+.

        Returns:
            List of relevant document chunks (may be empty if nothing is relevant)
        """
        n_results = n_results or MEMORY_RETRIEVAL_COUNT

        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where={
                "$and": [
                    {"type": "project_document"},
                    {"project_id": project_id}
                ]
            }
        )

        documents = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                distance = results["distances"][0][i] if results["distances"] else None

                # Skip documents that aren't relevant enough
                if distance is not None and distance > max_distance:
                    continue

                documents.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": distance
                })

        return documents

    def search_project_documents(
        self,
        query: str,
        project_id: str,
        n_results: int = 10
    ) -> List[Dict]:
        """
        Search project documents semantically, returning unique documents with relevance scores.

        Unlike retrieve_project_context which returns chunks, this groups results by document
        and returns the best matching chunk per document along with document metadata.

        Args:
            query: Search query
            project_id: Project to search within
            n_results: Maximum number of unique documents to return

        Returns:
            List of unique document results with id, title, best_chunk, and score
        """
        # Query more chunks than n_results since we'll deduplicate by document
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results * 3,  # Get extra to ensure enough unique docs
            where={
                "$and": [
                    {"type": "project_document"},
                    {"project_id": project_id},
                    {"is_internal_document": True}  # Only internal docs, not files
                ]
            }
        )

        if not results["documents"] or not results["documents"][0]:
            return []

        # Group by document_id, keeping best (lowest distance) chunk per doc
        docs_seen = {}
        for i, doc in enumerate(results["documents"][0]):
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else 1.0
            doc_id = metadata.get("document_id")

            if not doc_id:
                continue

            if doc_id not in docs_seen or distance < docs_seen[doc_id]["distance"]:
                docs_seen[doc_id] = {
                    "document_id": doc_id,
                    "title": metadata.get("document_title", "Untitled"),
                    "best_chunk": doc,
                    "chunk_index": metadata.get("chunk_index", 0),
                    "total_chunks": metadata.get("total_chunks", 1),
                    "distance": distance,
                    # Convert distance to a 0-1 relevance score (lower distance = higher relevance)
                    "relevance": max(0, 1 - distance) if distance else 1.0
                }

        # Sort by relevance (highest first) and limit
        unique_docs = sorted(docs_seen.values(), key=lambda x: x["distance"])[:n_results]

        return unique_docs

    def format_project_context(self, documents: List[Dict]) -> str:
        """
        Format project documents for context injection.

        Args:
            documents: List of document dicts from retrieve_project_context

        Returns:
            Formatted context string
        """
        if not documents:
            return ""

        context_parts = ["=== Project Documents ==="]

        for doc in documents:
            context_parts.append(f"\n{doc['content']}")

        return "\n".join(context_parts)

    # === Wiki Page Methods ===

    def embed_wiki_page(
        self,
        page_name: str,
        page_content: str,
        page_type: str,
        links: List[str] = None
    ) -> int:
        """
        Chunk and embed a wiki page into ChromaDB.

        Wiki pages are the core of Cass's identity memory - they represent
        her understanding of herself, her relationships, and her world.

        Args:
            page_name: Name of the wiki page (e.g., "Kohl", "Temple-Codex")
            page_content: Full markdown content of the page
            page_type: Type of page (entity, concept, relationship, journal, meta)
            links: Optional list of outgoing link targets

        Returns:
            Number of chunks embedded
        """
        if not page_content.strip():
            return 0

        # First remove any existing embeddings for this page
        self.remove_wiki_page_embeddings(page_name)

        # Extract title from content if possible
        from wiki import WikiParser
        title = WikiParser.extract_title(page_content) or page_name

        # Chunk the content
        chunks = self._core.chunk_text(page_content)

        # Embed each chunk
        timestamp = datetime.now().isoformat()

        for i, chunk in enumerate(chunks):
            # Build document with context
            doc_content = f"[Wiki Page: {page_name}]\n"
            doc_content += f"[Type: {page_type}]\n"
            if links:
                doc_content += f"[Links to: {', '.join(links[:5])}]\n"
            doc_content += f"[Chunk {i+1}/{len(chunks)}]\n\n{chunk}"

            # Metadata for retrieval filtering
            metadata = {
                "timestamp": timestamp,
                "type": "wiki_page",
                "wiki_page_name": page_name,
                "wiki_page_type": page_type,
                "wiki_page_title": title,
                "chunk_index": i,
                "total_chunks": len(chunks)
            }
            if links:
                # Store first 10 links in metadata for filtering
                metadata["wiki_links"] = ",".join(links[:10])

            # Generate stable ID based on page name and chunk
            entry_id = f"wiki:{page_name}:{i}"

            # Add to collection
            self.collection.add(
                documents=[doc_content],
                metadatas=[metadata],
                ids=[entry_id]
            )

        return len(chunks)

    def remove_wiki_page_embeddings(self, page_name: str) -> int:
        """
        Remove all embeddings for a specific wiki page.

        Called before re-embedding to ensure clean updates.

        Args:
            page_name: Name of the wiki page

        Returns:
            Number of chunks removed
        """
        results = self.collection.get(
            where={"wiki_page_name": page_name}
        )

        if not results["ids"]:
            return 0

        self.collection.delete(ids=results["ids"])

        return len(results["ids"])

    def retrieve_wiki_context(
        self,
        query: str,
        n_results: int = 5,
        page_type: str = None,
        max_distance: float = 1.7
    ) -> List[Dict]:
        """
        Retrieve relevant wiki pages for a query.

        Used for identity-based retrieval - finding relevant self-knowledge
        when Cass needs to understand something about herself or her world.

        Args:
            query: Search query
            n_results: Maximum number of results
            page_type: Optional filter by page type (entity, concept, etc.)
            max_distance: Maximum distance threshold for relevance

        Returns:
            List of relevant wiki page chunks
        """
        # Build where clause
        where = {"type": "wiki_page"}
        if page_type:
            where = {
                "$and": [
                    {"type": "wiki_page"},
                    {"wiki_page_type": page_type}
                ]
            }

        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"]
        )

        if not results["documents"] or not results["documents"][0]:
            return []

        # Filter by distance and format results
        context = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        ):
            if dist <= max_distance:
                context.append({
                    "content": doc,
                    "page_name": meta.get("wiki_page_name"),
                    "page_type": meta.get("wiki_page_type"),
                    "page_title": meta.get("wiki_page_title"),
                    "distance": dist
                })

        return context

    # === User Context Methods ===

    def embed_user_profile(self, user_id: str, profile_content: str, display_name: str, timestamp: str):
        """
        Embed a user's profile for semantic retrieval.

        Args:
            user_id: User's UUID
            profile_content: Formatted profile text
            display_name: User's display name
            timestamp: Last updated timestamp
        """
        doc_id = f"user_profile_{user_id}"

        # Remove existing profile if present
        try:
            self.collection.delete(ids=[doc_id])
        except Exception:
            pass  # May not exist

        self.collection.add(
            documents=[profile_content],
            metadatas=[{
                "type": "user_profile",
                "user_id": user_id,
                "display_name": display_name,
                "timestamp": timestamp
            }],
            ids=[doc_id]
        )

    def embed_user_observation(
        self,
        user_id: str,
        observation_id: str,
        observation_text: str,
        timestamp: str,
        display_name: Optional[str] = None,
        source_conversation_id: Optional[str] = None,
        category: str = "background",
        confidence: float = 0.7
    ):
        """
        Embed a single observation about a user.

        Args:
            user_id: User's UUID
            observation_id: Observation's UUID
            observation_text: The observation content
            timestamp: Observation timestamp
            display_name: User's display name (optional)
            source_conversation_id: Optional conversation this came from
            category: Observation category
            confidence: Confidence level (0.0-1.0)
        """
        doc_id = f"user_observation_{observation_id}"

        metadata = {
            "type": "user_observation",
            "user_id": user_id,
            "observation_id": observation_id,
            "timestamp": timestamp,
            "category": category,
            "confidence": confidence
        }
        if display_name:
            metadata["display_name"] = display_name
        if source_conversation_id:
            metadata["source_conversation_id"] = source_conversation_id

        # Remove existing if present (in case of re-embedding)
        try:
            self.collection.delete(ids=[doc_id])
        except Exception:
            pass

        name_part = f" {display_name}" if display_name else ""
        self.collection.add(
            documents=[f"Observation about user{name_part}: {observation_text}"],
            metadatas=[metadata],
            ids=[doc_id]
        )

    def retrieve_user_context(
        self,
        query: str,
        user_id: str,
        n_results: int = 5,
        max_observation_distance: float = 1.5
    ) -> List[Dict]:
        """
        Retrieve relevant user context for a query.

        User profile is always included (foundational context).
        Observations are filtered by relevance to avoid loading irrelevant ones.

        Args:
            query: The user's message or query
            user_id: User's UUID
            n_results: Number of results to return
            max_observation_distance: Max distance for observations (profile always included).
                                     Default 1.5 based on testing.

        Returns:
            List of relevant user context entries
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where={
                "$and": [
                    {"user_id": user_id},
                    {"$or": [
                        {"type": "user_profile"},
                        {"type": "user_observation"}
                    ]}
                ]
            }
        )

        context = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else None
                doc_type = metadata.get("type")

                # Always include profile, filter observations by relevance
                if doc_type == "user_observation":
                    if distance is not None and distance > max_observation_distance:
                        continue  # Skip irrelevant observations

                context.append({
                    "content": doc,
                    "metadata": metadata,
                    "distance": distance
                })

        return context

    def format_user_context(self, context_entries: List[Dict]) -> str:
        """
        Format user context entries for injection into prompts.

        Args:
            context_entries: Results from retrieve_user_context

        Returns:
            Formatted context string
        """
        if not context_entries:
            return ""

        parts = ["=== User Context ==="]

        # Separate profile from observations
        profile_entries = [c for c in context_entries if c["metadata"].get("type") == "user_profile"]
        observation_entries = [c for c in context_entries if c["metadata"].get("type") == "user_observation"]

        # Profile first
        for entry in profile_entries:
            parts.append(f"\n{entry['content']}")

        # Then observations
        if observation_entries:
            parts.append("\n--- Recent Observations ---")
            for entry in observation_entries:
                parts.append(f"- {entry['content']}")

        return "\n".join(parts)
