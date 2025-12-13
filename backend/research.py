"""
Cass Vessel - Research Tools
Web search, URL fetch, and research note management for autonomous research.
"""
import os
import json
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
import httpx
from bs4 import BeautifulSoup
import re

# Rate limiting
from collections import defaultdict
import time


@dataclass
class SearchResult:
    """A single search result"""
    title: str
    url: str
    snippet: str
    score: Optional[float] = None


@dataclass
class FetchedContent:
    """Content fetched from a URL"""
    url: str
    title: str
    content: str  # Markdown/plain text
    fetched_at: str
    word_count: int
    success: bool
    error: Optional[str] = None


@dataclass
class ResearchNote:
    """A research note capturing findings"""
    note_id: str
    title: str
    content: str
    created_at: str
    updated_at: str
    sources: List[Dict[str, str]]  # [{url, title, accessed_at}]
    related_agenda_items: List[str]
    related_questions: List[str]
    session_id: Optional[str] = None
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class RateLimiter:
    """Simple rate limiter for API calls"""

    def __init__(self, max_calls: int, period_seconds: int):
        self.max_calls = max_calls
        self.period = period_seconds
        self.calls: List[float] = []

    def can_call(self) -> bool:
        """Check if a call is allowed"""
        now = time.time()
        # Remove old calls outside the window
        self.calls = [t for t in self.calls if now - t < self.period]
        return len(self.calls) < self.max_calls

    def record_call(self):
        """Record a call"""
        self.calls.append(time.time())

    def wait_time(self) -> float:
        """How long to wait before next call is allowed"""
        if self.can_call():
            return 0
        oldest = min(self.calls)
        return self.period - (time.time() - oldest)


class ResearchManager:
    """
    Manages research tools: web search, URL fetching, and research notes.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir / "research"
        self.notes_dir = self.data_dir / "notes"
        self.notes_dir.mkdir(parents=True, exist_ok=True)

        # API keys
        self.tavily_api_key = os.environ.get("TAVILY_API_KEY")

        # Rate limiters
        self.search_limiter = RateLimiter(max_calls=20, period_seconds=60)  # 20/min
        self.fetch_limiter = RateLimiter(max_calls=30, period_seconds=60)   # 30/min

        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        """Close HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # === Web Search ===

    async def web_search(
        self,
        query: str,
        num_results: int = 10,
        search_depth: str = "basic",
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Search the web using Tavily API.

        Args:
            query: Search query
            num_results: Number of results (max 20)
            search_depth: "basic" or "advanced"
            include_domains: Only search these domains
            exclude_domains: Exclude these domains

        Returns:
            Dict with 'results' list and metadata
        """
        if not self.tavily_api_key:
            return {
                "success": False,
                "error": "TAVILY_API_KEY not configured",
                "results": []
            }

        if not self.search_limiter.can_call():
            wait = self.search_limiter.wait_time()
            return {
                "success": False,
                "error": f"Rate limited. Try again in {wait:.1f} seconds.",
                "results": []
            }

        try:
            client = await self._get_client()

            payload = {
                "api_key": self.tavily_api_key,
                "query": query,
                "max_results": min(num_results, 20),
                "search_depth": search_depth,
                "include_answer": True,
            }

            if include_domains:
                payload["include_domains"] = include_domains
            if exclude_domains:
                payload["exclude_domains"] = exclude_domains

            response = await client.post(
                "https://api.tavily.com/search",
                json=payload
            )

            self.search_limiter.record_call()

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Search API error: {response.status_code}",
                    "results": []
                }

            data = response.json()

            results = []
            for r in data.get("results", []):
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("content", ""),
                    score=r.get("score")
                ))

            return {
                "success": True,
                "query": query,
                "answer": data.get("answer"),  # Tavily's AI-generated answer
                "results": [asdict(r) for r in results],
                "result_count": len(results)
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "results": []
            }

    # === URL Fetching ===

    async def fetch_url(
        self,
        url: str,
        extract_mode: str = "article"
    ) -> Dict[str, Any]:
        """
        Fetch and extract content from a URL.

        Args:
            url: URL to fetch
            extract_mode: "article" (main content) or "full" (everything)

        Returns:
            Dict with content and metadata
        """
        if not self.fetch_limiter.can_call():
            wait = self.fetch_limiter.wait_time()
            return {
                "success": False,
                "error": f"Rate limited. Try again in {wait:.1f} seconds.",
                "content": ""
            }

        try:
            client = await self._get_client()

            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; CassResearchBot/1.0; +https://github.com/KohlJary/project-cass)"
            }

            response = await client.get(url, headers=headers, follow_redirects=True)
            self.fetch_limiter.record_call()

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "content": ""
                }

            content_type = response.headers.get("content-type", "")

            # Handle different content types
            if "application/json" in content_type:
                # JSON - return formatted
                try:
                    data = response.json()
                    content = json.dumps(data, indent=2)
                    title = url.split("/")[-1]
                except:
                    content = response.text
                    title = url
            elif "text/plain" in content_type:
                content = response.text
                title = url.split("/")[-1]
            else:
                # HTML - extract content
                content, title = self._extract_html_content(
                    response.text,
                    extract_mode
                )

            word_count = len(content.split())

            # Truncate very long content
            max_words = 5000
            if word_count > max_words:
                words = content.split()[:max_words]
                content = " ".join(words) + f"\n\n[Content truncated - {word_count} words total]"
                word_count = max_words

            result = FetchedContent(
                url=url,
                title=title,
                content=content,
                fetched_at=datetime.now().isoformat(),
                word_count=word_count,
                success=True
            )

            return asdict(result)

        except httpx.TimeoutException:
            return {
                "success": False,
                "error": "Request timed out",
                "content": ""
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "content": ""
            }

    def _extract_html_content(self, html: str, mode: str) -> tuple[str, str]:
        """Extract readable content from HTML"""
        soup = BeautifulSoup(html, "html.parser")

        # Get title
        title = ""
        if soup.title:
            title = soup.title.string or ""

        # Remove unwanted elements
        for tag in soup(["script", "style", "nav", "header", "footer",
                         "aside", "form", "iframe", "noscript"]):
            tag.decompose()

        if mode == "article":
            # Try to find main content
            main_content = None

            # Look for article or main tags
            for selector in ["article", "main", "[role='main']", ".post-content",
                           ".article-content", ".entry-content", "#content"]:
                main_content = soup.select_one(selector)
                if main_content:
                    break

            if main_content:
                text = self._html_to_markdown(main_content)
            else:
                # Fall back to body
                text = self._html_to_markdown(soup.body) if soup.body else soup.get_text()
        else:
            # Full mode - get everything
            text = self._html_to_markdown(soup.body) if soup.body else soup.get_text()

        # Clean up whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()

        return text, title

    def _html_to_markdown(self, element) -> str:
        """Convert HTML element to simple markdown"""
        if element is None:
            return ""

        lines = []

        for child in element.children:
            if isinstance(child, str):
                text = child.strip()
                if text:
                    lines.append(text)
                continue

            tag = child.name

            if tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                level = int(tag[1])
                text = child.get_text().strip()
                if text:
                    lines.append(f"\n{'#' * level} {text}\n")

            elif tag == "p":
                text = child.get_text().strip()
                if text:
                    lines.append(f"\n{text}\n")

            elif tag in ["ul", "ol"]:
                for i, li in enumerate(child.find_all("li", recursive=False)):
                    text = li.get_text().strip()
                    if text:
                        prefix = f"{i+1}." if tag == "ol" else "-"
                        lines.append(f"{prefix} {text}")
                lines.append("")

            elif tag == "pre":
                code = child.get_text()
                lines.append(f"\n```\n{code}\n```\n")

            elif tag == "code":
                text = child.get_text()
                lines.append(f"`{text}`")

            elif tag == "blockquote":
                text = child.get_text().strip()
                if text:
                    quoted = "\n".join(f"> {line}" for line in text.split("\n"))
                    lines.append(f"\n{quoted}\n")

            elif tag == "a":
                text = child.get_text().strip()
                href = child.get("href", "")
                if text and href:
                    lines.append(f"[{text}]({href})")
                elif text:
                    lines.append(text)

            elif tag in ["div", "section", "article"]:
                # Recurse into containers
                lines.append(self._html_to_markdown(child))

            else:
                # Generic: just get text
                text = child.get_text().strip()
                if text:
                    lines.append(text)

        return "\n".join(lines)

    # === Research Notes ===

    def create_research_note(
        self,
        title: str,
        content: str,
        sources: Optional[List[Dict[str, str]]] = None,
        related_agenda_items: Optional[List[str]] = None,
        related_questions: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create a new research note.

        Args:
            title: Note title
            content: Note content (markdown)
            sources: List of source dicts with url, title, accessed_at
            related_agenda_items: IDs of related agenda items
            related_questions: IDs of related working questions
            session_id: ID of research session that created this
            tags: Tags for categorization

        Returns:
            The created note
        """
        note_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()

        note = ResearchNote(
            note_id=note_id,
            title=title,
            content=content,
            created_at=now,
            updated_at=now,
            sources=sources or [],
            related_agenda_items=related_agenda_items or [],
            related_questions=related_questions or [],
            session_id=session_id,
            tags=tags or []
        )

        self._save_note(note)

        return asdict(note)

    def update_research_note(
        self,
        note_id: str,
        append_content: Optional[str] = None,
        add_source: Optional[Dict[str, str]] = None,
        add_tag: Optional[str] = None,
        new_title: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing research note.

        Args:
            note_id: ID of note to update
            append_content: Content to append
            add_source: New source to add
            add_tag: Tag to add
            new_title: New title

        Returns:
            Updated note or None if not found
        """
        note = self._load_note(note_id)
        if not note:
            return None

        if append_content:
            note.content += f"\n\n{append_content}"

        if add_source:
            note.sources.append(add_source)

        if add_tag and add_tag not in note.tags:
            note.tags.append(add_tag)

        if new_title:
            note.title = new_title

        note.updated_at = datetime.now().isoformat()

        self._save_note(note)

        return asdict(note)

    def get_research_note(self, note_id: str) -> Optional[Dict[str, Any]]:
        """Get a research note by ID"""
        note = self._load_note(note_id)
        return asdict(note) if note else None

    def list_research_notes(
        self,
        limit: int = 50,
        related_to_agenda: Optional[str] = None,
        related_to_question: Optional[str] = None,
        tag: Optional[str] = None,
        full_content: bool = False
    ) -> List[Dict[str, Any]]:
        """
        List research notes with optional filtering.

        Args:
            limit: Max notes to return
            related_to_agenda: Filter by agenda item ID
            related_to_question: Filter by question ID
            tag: Filter by tag
            full_content: If True, return full content; if False, truncate to 200 chars

        Returns:
            List of notes (with truncated content unless full_content=True)
        """
        notes = []

        for note_file in self.notes_dir.glob("*.json"):
            note = self._load_note(note_file.stem)
            if not note:
                continue

            # Apply filters
            if related_to_agenda and related_to_agenda not in note.related_agenda_items:
                continue
            if related_to_question and related_to_question not in note.related_questions:
                continue
            if tag and tag not in note.tags:
                continue

            note_dict = asdict(note)
            # Truncate content for list views unless full_content requested
            if not full_content and len(note_dict["content"]) > 200:
                note_dict["content"] = note_dict["content"][:200] + "..."
            notes.append(note_dict)

        # Sort by updated_at descending
        notes.sort(key=lambda x: x["updated_at"], reverse=True)

        return notes[:limit]

    def search_research_notes(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search research notes by content.

        Simple substring search - could be enhanced with embeddings later.
        """
        query_lower = query.lower()
        matches = []

        for note_file in self.notes_dir.glob("*.json"):
            note = self._load_note(note_file.stem)
            if not note:
                continue

            # Search in title, content, and tags
            if (query_lower in note.title.lower() or
                query_lower in note.content.lower() or
                any(query_lower in tag.lower() for tag in note.tags)):

                note_dict = asdict(note)
                if len(note_dict["content"]) > 200:
                    note_dict["content"] = note_dict["content"][:200] + "..."
                matches.append(note_dict)

        # Sort by updated_at descending
        matches.sort(key=lambda x: x["updated_at"], reverse=True)

        return matches[:limit]

    def _save_note(self, note: ResearchNote):
        """Save a research note to disk"""
        path = self.notes_dir / f"{note.note_id}.json"
        with open(path, "w") as f:
            json.dump(asdict(note), f, indent=2)

    def _load_note(self, note_id: str) -> Optional[ResearchNote]:
        """Load a research note from disk"""
        path = self.notes_dir / f"{note_id}.json"
        if not path.exists():
            return None

        try:
            with open(path) as f:
                data = json.load(f)
            return ResearchNote(**data)
        except Exception:
            return None
