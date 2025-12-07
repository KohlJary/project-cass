"""
Wiki Retrieval - Recursive context enrichment for wiki-based memory.

Implements the retrieval strategy from the spec:
1. findEntryPoints - Semantic search for starting pages
2. traverseLinks - Follow wikilinks to gather related context
3. synthesizeContext - Combine pages into coherent LLM context

Based on spec/memory/cass_memory_architecture_spec.md
"""

from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple
from datetime import datetime

from .storage import WikiStorage, WikiPage, PageType


@dataclass
class RetrievalResult:
    """Result of a wiki retrieval operation."""
    page: WikiPage
    relevance_score: float  # 0-1, higher is more relevant
    depth: int  # How many hops from entry point
    path: List[str] = field(default_factory=list)  # Path taken to reach this page


@dataclass
class WikiContext:
    """Synthesized context from wiki retrieval."""
    pages: List[RetrievalResult]
    synthesis: str  # Formatted context for LLM
    entry_points: List[str]  # Initial pages found
    total_pages_visited: int
    retrieval_time_ms: float
    stopped_early: bool = False  # Whether traversal stopped due to low novelty
    novelty_scores: List[float] = field(default_factory=list)  # Novelty of each added page


class WikiRetrieval:
    """
    Recursive context enrichment for wiki-based memory.

    Given a query (conversation context), finds relevant wiki pages
    through semantic search and link traversal, then synthesizes
    them into coherent context for the LLM.
    """

    def __init__(self, wiki_storage: WikiStorage, memory=None):
        """
        Initialize retrieval system.

        Args:
            wiki_storage: WikiStorage instance
            memory: CassMemory instance for embeddings (optional)
        """
        self.wiki = wiki_storage
        self.memory = memory

    def find_entry_points(
        self,
        query: str,
        n_results: int = 3,
        page_types: List[PageType] = None,
        max_distance: float = 1.7
    ) -> List[RetrievalResult]:
        """
        Find relevant wiki pages as starting points for traversal.

        Uses semantic search against wiki page embeddings to find
        pages most relevant to the query.

        Args:
            query: Search query (conversation context, user message, etc.)
            n_results: Maximum number of entry points to return
            page_types: Optional filter by page types
            max_distance: Maximum embedding distance for relevance

        Returns:
            List of RetrievalResults ranked by relevance
        """
        if not self.memory:
            # Fallback to text search if no embeddings
            return self._find_entry_points_text(query, n_results)

        # Use semantic search
        page_type_str = None
        if page_types and len(page_types) == 1:
            page_type_str = page_types[0].value

        results = self.memory.retrieve_wiki_context(
            query=query,
            n_results=n_results * 2,  # Get extra for filtering
            page_type=page_type_str,
            max_distance=max_distance
        )

        entry_points = []
        seen_pages = set()

        for r in results:
            page_name = r.get("page_name")
            if not page_name or page_name in seen_pages:
                continue

            # Load full page
            page = self.wiki.read(page_name)
            if not page:
                continue

            # Filter by page types if specified
            if page_types and page.page_type not in page_types:
                continue

            seen_pages.add(page_name)

            # Convert distance to relevance score (0-1)
            # Distance of 0 = perfect match = 1.0
            # Distance of max_distance = threshold = ~0.5
            distance = r.get("distance", max_distance)
            relevance = max(0, 1 - (distance / (max_distance * 2)))

            entry_points.append(RetrievalResult(
                page=page,
                relevance_score=relevance,
                depth=0,
                path=[page_name]
            ))

            if len(entry_points) >= n_results:
                break

        return entry_points

    def _find_entry_points_text(self, query: str, n_results: int) -> List[RetrievalResult]:
        """Fallback text-based entry point finding."""
        results = self.wiki.search(query)[:n_results]
        return [
            RetrievalResult(
                page=page,
                relevance_score=0.5,  # Unknown relevance for text search
                depth=0,
                path=[page.name]
            )
            for page in results
        ]

    def traverse_links(
        self,
        entry_points: List[RetrievalResult],
        query: str,
        max_depth: int = 2,
        max_pages: int = 10,
        relevance_threshold: float = 0.3,
        novelty_threshold: float = 0.3,
        stop_on_low_novelty: bool = True,
        low_novelty_streak: int = 3
    ) -> Tuple[List[RetrievalResult], bool, List[float]]:
        """
        Follow wikilinks from entry points to gather related context.

        Performs breadth-first traversal, assessing both relevance and novelty
        before including each page. Stops early if consecutive pages add little
        novel information.

        Args:
            entry_points: Starting pages from find_entry_points
            query: Original query for relevance assessment
            max_depth: Maximum link hops to follow
            max_pages: Maximum total pages to collect
            relevance_threshold: Minimum relevance to include page
            novelty_threshold: Minimum novelty to include page
            stop_on_low_novelty: Whether to stop when novelty drops
            low_novelty_streak: How many low-novelty pages before stopping

        Returns:
            Tuple of (results, stopped_early, novelty_scores)
        """
        # Track results and visited pages
        all_results: Dict[str, RetrievalResult] = {}
        visited: Set[str] = set()
        context_pool: List[WikiPage] = []  # Pages in context for novelty assessment
        novelty_scores: List[float] = []
        consecutive_low_novelty = 0
        stopped_early = False

        # Initialize with entry points
        for ep in entry_points:
            all_results[ep.page.name] = ep
            visited.add(ep.page.name)
            context_pool.append(ep.page)
            novelty_scores.append(1.0)  # Entry points are fully novel

        # BFS queue: (page_name, current_depth, path)
        queue: List[Tuple[str, int, List[str]]] = [
            (ep.page.name, 0, ep.path) for ep in entry_points
        ]

        while queue and len(all_results) < max_pages:
            page_name, depth, path = queue.pop(0)

            if depth >= max_depth:
                continue

            # Get the page
            page = self.wiki.read(page_name)
            if not page:
                continue

            # Get links from this page
            for link_target in page.link_targets:
                if link_target in visited:
                    continue

                visited.add(link_target)

                # Load the linked page
                linked_page = self.wiki.read(link_target)
                if not linked_page:
                    continue

                # Assess relevance of this linked page
                relevance = self._assess_relevance(linked_page, query, depth + 1)

                if relevance < relevance_threshold:
                    continue

                # Assess novelty - does this page add new information?
                novelty, is_novel = self.assess_novelty(
                    linked_page, context_pool, novelty_threshold
                )
                novelty_scores.append(novelty)

                if not is_novel:
                    consecutive_low_novelty += 1
                    if stop_on_low_novelty and consecutive_low_novelty >= low_novelty_streak:
                        stopped_early = True
                        break
                    continue
                else:
                    consecutive_low_novelty = 0

                # Page passed both relevance and novelty checks
                new_path = path + [link_target]
                result = RetrievalResult(
                    page=linked_page,
                    relevance_score=relevance,
                    depth=depth + 1,
                    path=new_path
                )
                all_results[link_target] = result
                context_pool.append(linked_page)

                # Add to queue for further traversal
                if depth + 1 < max_depth:
                    queue.append((link_target, depth + 1, new_path))

                if len(all_results) >= max_pages:
                    break

            if stopped_early:
                break

        # Sort by relevance (descending) then depth (ascending)
        sorted_results = sorted(
            all_results.values(),
            key=lambda r: (-r.relevance_score, r.depth)
        )

        return sorted_results, stopped_early, novelty_scores

    def _assess_relevance(
        self,
        page: WikiPage,
        query: str,
        depth: int
    ) -> float:
        """
        Assess how relevant a page is to the query.

        Uses embedding similarity if available, falls back to heuristics.

        Args:
            page: The page to assess
            query: The original query
            depth: How many hops from entry point

        Returns:
            Relevance score 0-1
        """
        base_relevance = 0.5

        # Use embeddings if available
        if self.memory:
            results = self.memory.retrieve_wiki_context(
                query=query,
                n_results=20,
                max_distance=2.0
            )

            for r in results:
                if r.get("page_name") == page.name:
                    distance = r.get("distance", 2.0)
                    # Convert distance to relevance
                    base_relevance = max(0, 1 - (distance / 4.0))
                    break

        # Decay relevance with depth
        depth_decay = 0.8 ** depth
        relevance = base_relevance * depth_decay

        # Boost for certain page types that are always relevant
        if page.page_type == PageType.ENTITY:
            relevance *= 1.1
        elif page.page_type == PageType.META:
            relevance *= 0.9  # Meta pages slightly less relevant

        return min(1.0, relevance)

    def assess_novelty(
        self,
        page: WikiPage,
        context_pool: List[WikiPage],
        novelty_threshold: float = 0.4
    ) -> Tuple[float, bool]:
        """
        Assess how much novel information a page adds to existing context.

        Compares the page's content against already-gathered pages using
        embedding similarity. High similarity = low novelty.

        Args:
            page: The candidate page to assess
            context_pool: Pages already in the context
            novelty_threshold: Minimum novelty to consider page valuable

        Returns:
            Tuple of (novelty_score 0-1, should_include boolean)
        """
        if not context_pool:
            # First page is always novel
            return (1.0, True)

        if not self.memory:
            # Without embeddings, use simple heuristic based on link overlap
            return self._assess_novelty_heuristic(page, context_pool, novelty_threshold)

        # Get embedding for candidate page
        candidate_embedding = self._get_page_embedding(page)
        if candidate_embedding is None:
            # Can't assess, assume moderately novel
            return (0.5, True)

        # Compare against each page in context pool
        max_similarity = 0.0
        for pool_page in context_pool:
            pool_embedding = self._get_page_embedding(pool_page)
            if pool_embedding is None:
                continue

            similarity = self._cosine_similarity(candidate_embedding, pool_embedding)
            max_similarity = max(max_similarity, similarity)

        # Novelty is inverse of max similarity
        # High similarity to any existing page = low novelty
        novelty = 1.0 - max_similarity

        return (novelty, novelty >= novelty_threshold)

    def _assess_novelty_heuristic(
        self,
        page: WikiPage,
        context_pool: List[WikiPage],
        novelty_threshold: float
    ) -> Tuple[float, bool]:
        """Fallback novelty assessment using link overlap."""
        candidate_links = page.link_targets

        # Calculate overlap with existing pages
        total_overlap = 0
        for pool_page in context_pool:
            overlap = len(candidate_links & pool_page.link_targets)
            total_overlap += overlap

        # Normalize by total possible links
        max_overlap = len(candidate_links) * len(context_pool)
        if max_overlap == 0:
            return (0.8, True)  # No links to compare

        overlap_ratio = total_overlap / max_overlap
        novelty = 1.0 - overlap_ratio

        return (novelty, novelty >= novelty_threshold)

    def _get_page_embedding(self, page: WikiPage) -> Optional[List[float]]:
        """Get the embedding vector for a wiki page."""
        if not self.memory:
            return None

        # Query for this specific page
        results = self.memory.retrieve_wiki_context(
            query=page.name,
            n_results=1,
            max_distance=0.1  # Very tight match
        )

        for r in results:
            if r.get("page_name") == page.name:
                # ChromaDB returns embeddings in results if requested
                return r.get("embedding")

        return None

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def synthesize_context(
        self,
        results: List[RetrievalResult],
        query: str,
        max_tokens: int = 2000,
        include_relationships: bool = True
    ) -> WikiContext:
        """
        Synthesize gathered pages into coherent LLM context.

        Not just concatenation - builds a narrative that explains
        the relationships between pages and their relevance.

        Args:
            results: Pages gathered from traversal
            query: Original query for context
            max_tokens: Approximate token limit for output
            include_relationships: Whether to describe link relationships

        Returns:
            WikiContext with formatted synthesis
        """
        import time
        start_time = time.time()

        if not results:
            return WikiContext(
                pages=[],
                synthesis="No relevant wiki context found.",
                entry_points=[],
                total_pages_visited=0,
                retrieval_time_ms=0
            )

        # Identify entry points (depth 0)
        entry_points = [r.page.name for r in results if r.depth == 0]

        # Build synthesis
        sections = []

        # Header
        sections.append("## Wiki Context\n")

        # Group by relevance tiers
        high_relevance = [r for r in results if r.relevance_score >= 0.6]
        medium_relevance = [r for r in results if 0.3 <= r.relevance_score < 0.6]

        # Add high relevance pages first
        if high_relevance:
            sections.append("### Core Context\n")
            for result in high_relevance[:5]:  # Limit to top 5
                sections.append(self._format_page_summary(result))

        # Add relationship narrative if requested
        if include_relationships and len(results) > 1:
            sections.append("\n### Connections\n")
            sections.append(self._build_relationship_narrative(results))

        # Add medium relevance as brief references
        if medium_relevance:
            sections.append("\n### Related Pages\n")
            for result in medium_relevance[:3]:
                sections.append(f"- **{result.page.name}** ({result.page.page_type.value})")

        synthesis = "\n".join(sections)

        # Truncate if too long (rough token estimate: 4 chars per token)
        max_chars = max_tokens * 4
        if len(synthesis) > max_chars:
            synthesis = synthesis[:max_chars] + "\n\n[Context truncated...]"

        elapsed_ms = (time.time() - start_time) * 1000

        return WikiContext(
            pages=results,
            synthesis=synthesis,
            entry_points=entry_points,
            total_pages_visited=len(results),
            retrieval_time_ms=elapsed_ms
        )

    def _format_page_summary(self, result: RetrievalResult) -> str:
        """Format a page for inclusion in synthesis."""
        page = result.page
        lines = []

        lines.append(f"#### {page.title}")
        lines.append(f"*Type: {page.page_type.value} | Relevance: {result.relevance_score:.0%}*\n")

        # Get the body without frontmatter
        body = page.body.strip()

        # Take first ~500 chars or first section
        if len(body) > 500:
            # Try to end at a paragraph break
            truncated = body[:500]
            last_para = truncated.rfind("\n\n")
            if last_para > 200:
                truncated = truncated[:last_para]
            body = truncated + "..."

        lines.append(body)
        lines.append("")

        return "\n".join(lines)

    def _build_relationship_narrative(self, results: List[RetrievalResult]) -> str:
        """Build a narrative describing relationships between pages."""
        if len(results) < 2:
            return ""

        lines = []

        # Find pages that link to each other
        page_names = {r.page.name for r in results}

        for result in results[:5]:  # Limit analysis
            outgoing = result.page.link_targets & page_names
            if outgoing:
                links_str = ", ".join(f"[[{n}]]" for n in list(outgoing)[:3])
                lines.append(f"- {result.page.name} connects to {links_str}")

        return "\n".join(lines) if lines else ""

    def retrieve_context(
        self,
        query: str,
        n_entry_points: int = 3,
        max_depth: int = 2,
        max_pages: int = 10,
        max_tokens: int = 2000
    ) -> WikiContext:
        """
        Full retrieval pipeline: find entry points, traverse, synthesize.

        This is the main method to call for getting wiki context.

        Args:
            query: The query/context to find relevant wiki pages for
            n_entry_points: Number of starting pages to find
            max_depth: How deep to follow links
            max_pages: Maximum pages to include
            max_tokens: Token budget for synthesis

        Returns:
            WikiContext with pages and formatted synthesis
        """
        # Step 1: Find entry points
        entry_points = self.find_entry_points(query, n_results=n_entry_points)

        if not entry_points:
            return WikiContext(
                pages=[],
                synthesis="No relevant wiki pages found for this context.",
                entry_points=[],
                total_pages_visited=0,
                retrieval_time_ms=0
            )

        # Step 2: Traverse links with novelty assessment
        all_pages, stopped_early, novelty_scores = self.traverse_links(
            entry_points=entry_points,
            query=query,
            max_depth=max_depth,
            max_pages=max_pages
        )

        # Step 3: Synthesize context
        context = self.synthesize_context(
            results=all_pages,
            query=query,
            max_tokens=max_tokens
        )

        # Add novelty info to context
        context.stopped_early = stopped_early
        context.novelty_scores = novelty_scores

        return context
