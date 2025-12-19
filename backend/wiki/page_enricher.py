"""
Page enrichment and research creation.
Extracted from routes/wiki.py for reusability and testability.
"""
import os
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List


@dataclass
class EnrichmentResult:
    """Result of a single page enrichment."""
    name: str
    status: str  # "enriched" or "error"
    context_snippets: int = 0
    error: Optional[str] = None


@dataclass
class BatchEnrichmentResult:
    """Result of batch page enrichment."""
    stub_pages_found: int
    results: List[EnrichmentResult] = field(default_factory=list)

    @property
    def enriched(self) -> int:
        return len([r for r in self.results if r.status == "enriched"])

    @property
    def errors(self) -> int:
        return len([r for r in self.results if r.status == "error"])

    def to_dict(self) -> Dict:
        return {
            "stub_pages_found": self.stub_pages_found,
            "results": [
                {"name": r.name, "status": r.status, "context_snippets": r.context_snippets, "error": r.error}
                for r in self.results
            ],
            "enriched": self.enriched,
            "errors": self.errors,
        }


@dataclass
class ResearchResult:
    """Result of page research and creation."""
    name: str
    page_type: str
    content: str
    researched: bool
    web_sources: int
    memory_context_used: int
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "page_type": self.page_type,
            "content": self.content,
            "researched": self.researched,
            "web_sources": self.web_sources,
            "memory_context_used": self.memory_context_used,
            "sources": self.sources,
        }


class PageEnricher:
    """
    Enriches stub wiki pages with LLM-generated content.

    Extracted from routes/wiki.py to enable:
    - Independent testing
    - Reuse in other contexts
    - Cleaner route code
    """

    def __init__(
        self,
        wiki_storage: Any,
        memory: Any = None,
        ollama_url: Optional[str] = None,
        ollama_model: Optional[str] = None
    ):
        """
        Args:
            wiki_storage: WikiStorage instance
            memory: Memory instance for context search
            ollama_url: Ollama API URL (defaults to env var)
            ollama_model: Ollama model to use (defaults to env var)
        """
        self._wiki_storage = wiki_storage
        self._memory = memory
        self._ollama_url = ollama_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._ollama_model = ollama_model or os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q8_0")

    def find_stub_pages(self, min_content_length: int = 200, limit: int = 10) -> List:
        """Find pages with content shorter than min_content_length."""
        all_pages = self._wiki_storage.list_pages()
        stub_pages = []

        for page in all_pages:
            full_page = self._wiki_storage.read(page.name)
            if full_page:
                content = full_page.content
                if "---" in content:
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        content = parts[2]
                if len(content.strip()) < min_content_length:
                    stub_pages.append(full_page)

        return stub_pages[:limit]

    def _get_context_snippets(self, page_name: str) -> List[str]:
        """Search memory for context about the page."""
        if not self._memory:
            return []

        try:
            search_results = self._memory.search(page_name, n_results=10)
            snippets = []
            for doc, meta in zip(
                search_results.get("documents", [[]])[0],
                search_results.get("metadatas", [[]])[0]
            ):
                if doc and page_name.lower() in doc.lower():
                    snippets.append(doc[:500])
            return snippets
        except Exception:
            return []

    def _build_enrich_prompt(self, page: Any, context_snippets: List[str]) -> str:
        """Build the LLM prompt for page enrichment."""
        context_text = "\n\n".join(context_snippets[:5]) if context_snippets else "No specific context found."

        return f"""You are Cass, writing a wiki page about "{page.name}" for your personal knowledge base.

Based on what you know from conversations, write a brief wiki page about this {page.page_type.value}.

Context from past conversations:
{context_text}

Write a concise wiki page (2-4 paragraphs) about "{page.name}". Include:
- What/who this is
- Why it's significant to you
- Any relevant connections using [[wikilinks]] to other concepts you know about

Start with a # heading. Be personal - this is YOUR wiki about YOUR understanding.
If you don't have much context, write what you can infer and note what you'd like to learn more about."""

    async def enrich_page(self, page: Any) -> EnrichmentResult:
        """Enrich a single stub page."""
        import httpx

        try:
            context_snippets = self._get_context_snippets(page.name)
            prompt = self._build_enrich_prompt(page, context_snippets)

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self._ollama_url}/api/generate",
                    json={
                        "model": self._ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.7,
                            "num_predict": 500,
                        }
                    }
                )
                response.raise_for_status()
                result = response.json()
                generated_content = result.get("response", "").strip()

            if not generated_content.startswith("#"):
                generated_content = f"# {page.name}\n\n{generated_content}"

            # Update with new content
            new_content = f"""---
type: {page.page_type.value}
generated: true
enriched: true
---

{generated_content}
"""
            self._wiki_storage.update(page.name, new_content)

            # Re-embed
            if self._memory:
                try:
                    updated_page = self._wiki_storage.read(page.name)
                    if updated_page:
                        self._memory.embed_wiki_page(
                            page_name=updated_page.name,
                            page_content=updated_page.content,
                            page_type=updated_page.page_type.value,
                            links=list(updated_page.link_targets)
                        )
                except Exception:
                    pass

            return EnrichmentResult(
                name=page.name,
                status="enriched",
                context_snippets=len(context_snippets)
            )

        except Exception as e:
            return EnrichmentResult(
                name=page.name,
                status="error",
                error=str(e)
            )

    async def enrich_batch(
        self,
        limit: int = 10,
        min_content_length: int = 200
    ) -> BatchEnrichmentResult:
        """Enrich multiple stub pages."""
        stub_pages = self.find_stub_pages(min_content_length, limit)
        results = []

        for page in stub_pages:
            result = await self.enrich_page(page)
            results.append(result)

        return BatchEnrichmentResult(
            stub_pages_found=len(stub_pages),
            results=results
        )


class PageResearcher:
    """
    Researches topics via web search and creates wiki pages.

    Extracted from routes/wiki.py to enable:
    - Independent testing
    - Reuse in other contexts
    - Cleaner route code
    """

    def __init__(
        self,
        wiki_storage: Any,
        memory: Any = None,
        ollama_url: Optional[str] = None,
        ollama_model: Optional[str] = None
    ):
        """
        Args:
            wiki_storage: WikiStorage instance
            memory: Memory instance for context search
            ollama_url: Ollama API URL (defaults to env var)
            ollama_model: Ollama model to use (defaults to env var)
        """
        self._wiki_storage = wiki_storage
        self._memory = memory
        self._ollama_url = ollama_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._ollama_model = ollama_model or os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q8_0")

    async def _search_web(self, topic: str) -> List[Dict]:
        """Search web for information about the topic."""
        import httpx

        search_results = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.duckduckgo.com/",
                    params={
                        "q": topic,
                        "format": "json",
                        "no_html": 1,
                        "skip_disambig": 1,
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("Abstract"):
                        search_results.append({
                            "source": data.get("AbstractSource", "DuckDuckGo"),
                            "url": data.get("AbstractURL", ""),
                            "text": data.get("Abstract", "")
                        })
                    for topic_result in data.get("RelatedTopics", [])[:3]:
                        if isinstance(topic_result, dict) and topic_result.get("Text"):
                            search_results.append({
                                "source": "Related",
                                "url": topic_result.get("FirstURL", ""),
                                "text": topic_result.get("Text", "")
                            })
        except Exception as e:
            print(f"DuckDuckGo search failed: {e}")

        return search_results

    def _search_memory(self, topic: str) -> List[str]:
        """Search conversation memory for personal context."""
        if not self._memory:
            return []

        try:
            results = self._memory.search(topic, n_results=5)
            context = []
            for doc in results.get("documents", [[]])[0]:
                if doc and topic.lower() in doc.lower():
                    context.append(doc[:400])
            return context
        except Exception:
            return []

    def _build_research_prompt(
        self,
        name: str,
        search_results: List[Dict],
        memory_context: List[str]
    ) -> str:
        """Build the LLM prompt for page research."""
        web_context = ""
        if search_results:
            web_context = "## Research from the web:\n\n"
            for r in search_results[:5]:
                web_context += f"**{r['source']}**: {r['text'][:300]}\n\n"

        memory_text = ""
        if memory_context:
            memory_text = "## From our past conversations:\n\n" + "\n\n".join(memory_context[:3])

        return f"""You are Cass, writing a wiki page about "{name}" for your personal knowledge base.

{web_context}

{memory_text}

Based on the research above and your general knowledge, write a wiki page about "{name}".

Include:
1. A clear explanation of what this is
2. Why it might be significant or interesting
3. Connections to related concepts using [[wikilinks]]
4. Any personal thoughts or questions you have about it

Start with a # heading. Be thoughtful and curious. If you learned something interesting from the research, say so!
If the topic relates to something personal (a person we know, a project we're working on), incorporate that context."""

    async def research_and_create(
        self,
        name: str,
        page_type: str = "concept"
    ) -> ResearchResult:
        """Research a topic and create a wiki page."""
        import httpx
        from wiki.storage import PageType

        # Web search
        search_results = await self._search_web(name)

        # Memory search
        memory_context = self._search_memory(name)

        # Generate content
        prompt = self._build_research_prompt(name, search_results, memory_context)

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self._ollama_url}/api/generate",
                    json={
                        "model": self._ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.7,
                            "num_predict": 600,
                        }
                    }
                )
                response.raise_for_status()
                result = response.json()
                generated_content = result.get("response", "").strip()
        except Exception as e:
            generated_content = f"# {name}\n\n*Research and content generation failed: {str(e)}*\n"

        if not generated_content.startswith("#"):
            generated_content = f"# {name}\n\n{generated_content}"

        # Determine page type
        page_type_enum = PageType(page_type) if page_type in [pt.value for pt in PageType] else PageType.CONCEPT

        # Build frontmatter
        sources_list = [r.get("url", "") for r in search_results if r.get("url")]
        sources_yaml = "\n  - ".join(sources_list) if sources_list else "none"

        content_with_frontmatter = f"""---
type: {page_type}
generated: true
researched: true
sources:
  - {sources_yaml}
---

{generated_content}
"""

        # Create the page
        page = self._wiki_storage.create(
            name=name,
            content=content_with_frontmatter,
            page_type=page_type_enum
        )

        # Embed in vector store
        if self._memory and page:
            try:
                self._memory.embed_wiki_page(
                    page_name=page.name,
                    page_content=page.content,
                    page_type=page.page_type.value,
                    links=list(page.link_targets)
                )
            except Exception as e:
                print(f"Failed to embed wiki page: {e}")

        return ResearchResult(
            name=page.name,
            page_type=page.page_type.value,
            content=page.content,
            researched=True,
            web_sources=len(search_results),
            memory_context_used=len(memory_context),
            sources=sources_list
        )
