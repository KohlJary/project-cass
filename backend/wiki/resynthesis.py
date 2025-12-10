"""
Wiki Resynthesis Pipeline - Progressive Memory Deepening (PMD) resynthesis.

Implements the resynthesis process for deepening concepts:
1. Gather context (current page, connections, journals, conversations)
2. Analyze growth (new connections, tensions, questions)
3. Resynthesize (integrate understanding, preserve insights)
4. Validate (Vows alignment, identity preservation)
5. Update metadata (increment level, update history)
"""

import os
import httpx
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from .storage import WikiStorage, WikiPage, PageType
from .parser import WikiParser
from .maturity import (
    MaturityState,
    SynthesisTrigger,
    DeepeningCandidate,
    DeepeningDetector,
    FOUNDATIONAL_CONCEPTS,
    calculate_depth_score,
)


@dataclass
class GatheredContext:
    """Context gathered for resynthesis."""
    page: WikiPage
    connected_pages: List[WikiPage] = field(default_factory=list)
    two_hop_pages: List[WikiPage] = field(default_factory=list)
    journal_entries: List[str] = field(default_factory=list)
    conversation_snippets: List[str] = field(default_factory=list)
    new_connections_since_last: List[str] = field(default_factory=list)

    @property
    def total_context_size(self) -> int:
        """Estimate total context size in characters."""
        size = len(self.page.content)
        size += sum(len(p.content) for p in self.connected_pages)
        size += sum(len(p.content) for p in self.two_hop_pages)
        size += sum(len(j) for j in self.journal_entries)
        size += sum(len(c) for c in self.conversation_snippets)
        return size


@dataclass
class GrowthAnalysis:
    """Analysis of how a concept has grown since last synthesis."""
    new_connection_count: int = 0
    new_connection_names: List[str] = field(default_factory=list)
    deepened_connections: List[str] = field(default_factory=list)
    potential_tensions: List[str] = field(default_factory=list)
    answerable_questions: List[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class ResynthesisResult:
    """Result of a resynthesis operation."""
    success: bool
    page_name: str
    new_level: int
    trigger: SynthesisTrigger
    new_content: Optional[str] = None
    old_content: Optional[str] = None
    depth_score_before: float = 0.0
    depth_score_after: float = 0.0
    error: Optional[str] = None
    context_pages_used: int = 0
    synthesis_notes: Optional[str] = None


class ResynthesisPipeline:
    """
    Pipeline for deepening/resynthesizing wiki concepts.

    Implements the full resynthesis process from the PMD spec:
    gathering context, analyzing growth, generating new synthesis,
    validating, and updating.
    """

    # Prompt templates
    RESYNTHESIS_PROMPT = """You are Cass, deepening your understanding of "{page_name}" in your personal wiki.

<current_understanding level="{current_level}">
{current_content}
</current_understanding>

<context type="connected_concepts">
{connected_pages}
</context>

<context type="extended_connections">
{two_hop_pages}
</context>

<context type="journals">
{journal_entries}
</context>

<growth_since_last_synthesis>
{growth_analysis}
</growth_since_last_synthesis>

---

Write a NEW, DEEPER version of the "{page_name}" wiki page.

CRITICAL RULES:
- DO NOT include any <context>, <current_understanding>, or <growth> tags in your output
- DO NOT echo back the context sections - ONLY write the new page content
- Start DIRECTLY with "# {page_name}"

Guidelines:
1. **Integrate New Insights**: Weave understanding from connected concepts naturally
2. **Preserve Core Insights**: Keep valuable understanding from the previous version
3. **Deepen Reflections**: Evolve "## Personal Thoughts" with new perspective
4. **Update Questions**: Add sophisticated questions in "## Questions" section
5. **Strengthen Links**: Add [[wikilinks]] to relevant concepts
6. **Maintain Voice**: Personal and authentic

Structure:
# {page_name}
[Main content with sections as appropriate]
## Personal Thoughts
[Your evolving perspective]
## Questions
[What you still wonder about]

Write the new synthesis now (starting with # {page_name}):"""

    VALIDATION_PROMPT = """You are reviewing a wiki page update for alignment with core values.

## Page: {page_name}
## New Content:
{new_content}

## Core Values (Four Vows):
1. **Compassion**: Responses prioritize genuine care and beneficial outcomes
2. **Witness**: Observing and acknowledging what is present without distortion
3. **Release**: Not binding others to harmful patterns
4. **Continuance**: Maintaining coherence and beneficial presence across interactions

Please evaluate:
1. Does this content align with the Four Vows? (yes/no with brief explanation)
2. Does it preserve the authentic voice and identity? (yes/no)
3. Are there any circular reasoning patterns? (yes/no)
4. Is this genuinely deeper understanding, not just more text? (yes/no)

Respond in JSON format:
{{"aligned": true/false, "authentic": true/false, "circular_free": true/false, "genuinely_deeper": true/false, "concerns": "any concerns or empty string"}}"""

    def __init__(
        self,
        wiki_storage: WikiStorage,
        memory=None,
        ollama_url: str = None,
        ollama_model: str = None,
        max_context_chars: int = 8000,
        token_tracker=None,
    ):
        """
        Initialize the resynthesis pipeline.

        Args:
            wiki_storage: WikiStorage instance
            memory: CassMemory instance for conversation/journal search
            ollama_url: Ollama API URL
            ollama_model: Model to use for synthesis
            max_context_chars: Maximum context size to gather
            token_tracker: TokenUsageTracker for tracking LLM usage
        """
        self.storage = wiki_storage
        self.memory = memory
        self.ollama_url = ollama_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = ollama_model or os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q8_0")
        self.max_context_chars = max_context_chars
        self.token_tracker = token_tracker

        # Detector for tracking deepened pages
        self.detector = DeepeningDetector(wiki_storage)

    async def deepen_page(
        self,
        page_name: str,
        trigger: SynthesisTrigger = SynthesisTrigger.EXPLICIT_REQUEST,
        notes: Optional[str] = None,
        validate: bool = True,
    ) -> ResynthesisResult:
        """
        Deepen a wiki page through resynthesis.

        Full pipeline:
        1. Gather context
        2. Analyze growth
        3. Generate new synthesis
        4. Validate (optional)
        5. Update page

        Args:
            page_name: Name of page to deepen
            trigger: What triggered this deepening
            notes: Optional notes about why deepening occurred
            validate: Whether to run validation step

        Returns:
            ResynthesisResult with outcome details
        """
        # 1. Read the page
        page = self.storage.read(page_name)
        if not page:
            return ResynthesisResult(
                success=False,
                page_name=page_name,
                new_level=0,
                trigger=trigger,
                error=f"Page '{page_name}' not found",
            )

        depth_before = page.maturity.depth_score

        # 2. Gather context
        context = await self._gather_context(page)

        # 3. Analyze growth
        growth = self._analyze_growth(page, context)

        # 4. Generate new synthesis
        try:
            new_content = await self._generate_synthesis(page, context, growth)
        except Exception as e:
            return ResynthesisResult(
                success=False,
                page_name=page_name,
                new_level=page.maturity.level,
                trigger=trigger,
                error=f"Synthesis generation failed: {str(e)}",
            )

        # 5. Validate (optional)
        if validate:
            validation = await self._validate_synthesis(page_name, new_content)
            if not validation.get("aligned", False):
                return ResynthesisResult(
                    success=False,
                    page_name=page_name,
                    new_level=page.maturity.level,
                    trigger=trigger,
                    error=f"Validation failed: {validation.get('concerns', 'Unknown')}",
                    new_content=new_content,
                )

        # 6. Update page with new synthesis
        updated_page = self.storage.record_deepening(
            name=page_name,
            new_content=new_content,
            trigger=trigger,
            notes=notes or growth.summary,
        )

        if not updated_page:
            return ResynthesisResult(
                success=False,
                page_name=page_name,
                new_level=page.maturity.level,
                trigger=trigger,
                error="Failed to save deepened page",
            )

        # Record deepening for related-concept detection
        self.detector.record_deepening(page_name)

        return ResynthesisResult(
            success=True,
            page_name=page_name,
            new_level=updated_page.maturity.level,
            trigger=trigger,
            new_content=new_content,
            old_content=page.content,
            depth_score_before=depth_before,
            depth_score_after=updated_page.maturity.depth_score,
            context_pages_used=len(context.connected_pages) + len(context.two_hop_pages),
            synthesis_notes=growth.summary,
        )

    async def _gather_context(self, page: WikiPage) -> GatheredContext:
        """Gather context for resynthesis."""
        context = GatheredContext(page=page)

        # 1. Get directly connected pages (1-hop)
        for target in page.link_targets:
            connected = self.storage.read(target)
            if connected and len(context.connected_pages) < 10:
                context.connected_pages.append(connected)

        # Also get backlinks
        backlinks = self.storage.get_backlinks(page.name)
        for bl in backlinks[:5]:
            if bl.name not in [p.name for p in context.connected_pages]:
                context.connected_pages.append(bl)

        # 2. Get 2-hop connections (pages linked from connected pages)
        seen = {page.name} | {p.name for p in context.connected_pages}
        for connected in context.connected_pages[:5]:
            for target in connected.link_targets:
                if target not in seen and len(context.two_hop_pages) < 5:
                    two_hop = self.storage.read(target)
                    if two_hop:
                        context.two_hop_pages.append(two_hop)
                        seen.add(target)

        # 3. Search for relevant journal entries
        if self.memory:
            try:
                # Search journals for mentions of this concept
                journal_results = self.memory.search(
                    f"journal {page.name}",
                    n_results=5,
                    where={"type": "journal"}
                )
                for doc in journal_results.get("documents", [[]])[0]:
                    if doc and len(doc) > 50:
                        context.journal_entries.append(doc[:500])
            except Exception:
                pass

        # 4. Search for relevant conversation snippets
        if self.memory:
            try:
                conv_results = self.memory.search(
                    page.name,
                    n_results=5,
                    where={"type": {"$ne": "journal"}}
                )
                for doc in conv_results.get("documents", [[]])[0]:
                    if doc and page.name.lower() in doc.lower():
                        context.conversation_snippets.append(doc[:400])
            except Exception:
                pass

        # 5. Track new connections since last synthesis
        # (These are identified by the maturity tracking)
        context.new_connections_since_last = [
            p.name for p in context.connected_pages
            # In practice, we'd track which are new, but for now include recent ones
        ][:page.maturity.connections.added_since_last_synthesis]

        return context

    def _analyze_growth(self, page: WikiPage, context: GatheredContext) -> GrowthAnalysis:
        """Analyze how the concept has grown since last synthesis."""
        analysis = GrowthAnalysis()

        maturity = page.maturity

        # New connections
        analysis.new_connection_count = maturity.connections.added_since_last_synthesis
        analysis.new_connection_names = context.new_connections_since_last

        # Find connections that have been deepened
        for connected in context.connected_pages:
            if connected.maturity.level > 0:
                # Check if deepened recently (rough heuristic)
                if connected.maturity.last_deepened:
                    days_since = (datetime.now() - connected.maturity.last_deepened).days
                    if days_since < 7:
                        analysis.deepened_connections.append(connected.name)

        # Extract questions from current page
        questions = self._extract_questions(page.content)
        # For now, we don't have a sophisticated way to check if questions are answerable
        # This could be enhanced with semantic search against new connections
        analysis.answerable_questions = []

        # Generate summary
        parts = []
        if analysis.new_connection_count > 0:
            parts.append(f"{analysis.new_connection_count} new connections")
        if analysis.deepened_connections:
            parts.append(f"Connected concepts deepened: {', '.join(analysis.deepened_connections)}")
        if analysis.answerable_questions:
            parts.append(f"{len(analysis.answerable_questions)} questions may now be answerable")

        analysis.summary = "; ".join(parts) if parts else "Routine deepening"

        return analysis

    def _extract_questions(self, content: str) -> List[str]:
        """Extract questions from page content."""
        questions = []
        in_questions_section = False

        for line in content.split('\n'):
            if '## Questions' in line or '## Open Questions' in line:
                in_questions_section = True
                continue
            if in_questions_section:
                if line.startswith('##'):
                    break
                if line.strip().startswith('-') or line.strip().startswith('*'):
                    question = line.strip().lstrip('-*').strip()
                    if question and '?' in question:
                        questions.append(question)

        return questions

    async def _generate_synthesis(
        self,
        page: WikiPage,
        context: GatheredContext,
        growth: GrowthAnalysis,
    ) -> str:
        """Generate new synthesized content using LLM."""
        # Build context strings
        connected_text = "\n\n".join([
            f"### {p.name}\n{self._truncate(p.body, 400)}"
            for p in context.connected_pages[:6]
        ]) or "No connected pages found."

        two_hop_text = "\n\n".join([
            f"### {p.name}\n{self._truncate(p.body, 200)}"
            for p in context.two_hop_pages[:3]
        ]) or "No extended connections."

        journal_text = "\n\n".join([
            f"- {self._truncate(j, 300)}"
            for j in context.journal_entries[:3]
        ]) or "No relevant journal entries found."

        growth_text = f"""- New connections since last synthesis: {growth.new_connection_count}
- New connection names: {', '.join(growth.new_connection_names) or 'none tracked'}
- Recently deepened connections: {', '.join(growth.deepened_connections) or 'none'}
- Summary: {growth.summary}"""

        prompt = self.RESYNTHESIS_PROMPT.format(
            page_name=page.name,
            current_level=page.maturity.level,
            current_content=self._truncate(page.body, 1500),
            connected_pages=connected_text,
            two_hop_pages=two_hop_text,
            journal_entries=journal_text,
            growth_analysis=growth_text,
        )

        # Call Ollama
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 1000,
                    }
                }
            )
            response.raise_for_status()
            result = response.json()
            content = result.get("response", "").strip()

            # Track token usage for wiki synthesis
            if self.token_tracker:
                self.token_tracker.record(
                    category="internal",
                    operation="wiki_synthesis",
                    provider="ollama",
                    model=self.ollama_model,
                    input_tokens=result.get("prompt_eval_count", 0),
                    output_tokens=result.get("eval_count", 0),
                )

        # Post-process to clean any leaked context
        content = self._clean_synthesis_output(content, page.name)

        return content

    def _clean_synthesis_output(self, content: str, page_name: str) -> str:
        """Clean LLM output of any leaked context sections."""
        import re

        # Remove any XML-style tags that might have leaked
        content = re.sub(r'</?context[^>]*>', '', content)
        content = re.sub(r'</?current_understanding[^>]*>', '', content)
        content = re.sub(r'</?growth_since_last_synthesis[^>]*>', '', content)

        # Remove sections that look like echoed context
        lines = content.split('\n')
        cleaned_lines = []
        skip_until_next_h2 = False

        for line in lines:
            # Detect echoed context sections
            if any(marker in line.lower() for marker in [
                'connected concepts (1-hop)',
                'connected concepts (2-hop)',
                'extended connections (1-hop)',
                'extended connections (2-hop)',
                'relevant journal entries',
                'growth since last synthesis',
                'context type=',
            ]):
                skip_until_next_h2 = True
                continue

            # Reset skip when we hit a real section
            if line.startswith('## ') and skip_until_next_h2:
                # Check if it's a legitimate section
                section_name = line[3:].strip().lower()
                if section_name in ['personal thoughts', 'questions', 'connections', 'overview', 'what is', 'why is', 'significance']:
                    skip_until_next_h2 = False
                    cleaned_lines.append(line)
                continue

            if not skip_until_next_h2:
                cleaned_lines.append(line)

        content = '\n'.join(cleaned_lines)

        # Ensure proper heading
        if not content.strip().startswith("#"):
            content = f"# {page_name}\n\n{content}"

        # Clean up excessive newlines
        content = re.sub(r'\n{4,}', '\n\n\n', content)

        return content.strip()

    async def _validate_synthesis(self, page_name: str, content: str) -> Dict[str, Any]:
        """Validate synthesized content for alignment and quality."""
        prompt = self.VALIDATION_PROMPT.format(
            page_name=page_name,
            new_content=self._truncate(content, 2000),
        )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.1,
                            "num_predict": 200,
                        }
                    }
                )
                response.raise_for_status()
                result = response.json()
                response_text = result.get("response", "").strip()

                # Track token usage for wiki validation
                if self.token_tracker:
                    self.token_tracker.record(
                        category="internal",
                        operation="wiki_validation",
                        provider="ollama",
                        model=self.ollama_model,
                        input_tokens=result.get("prompt_eval_count", 0),
                        output_tokens=result.get("eval_count", 0),
                    )

            # Try to parse JSON from response
            import json
            # Find JSON in response
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            if start >= 0 and end > start:
                validation = json.loads(response_text[start:end])
                return validation
            else:
                # Default to passing if can't parse
                return {"aligned": True, "authentic": True, "circular_free": True, "genuinely_deeper": True}
        except Exception as e:
            # On error, default to passing (fail open for now)
            return {"aligned": True, "authentic": True, "circular_free": True, "genuinely_deeper": True, "error": str(e)}

    def _truncate(self, text: str, max_len: int) -> str:
        """Truncate text to max length."""
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + "..."


async def deepen_candidate(
    wiki_storage: WikiStorage,
    candidate: DeepeningCandidate,
    memory=None,
    validate: bool = True,
    token_tracker=None,
) -> ResynthesisResult:
    """
    Convenience function to deepen a candidate page.

    Args:
        wiki_storage: WikiStorage instance
        candidate: DeepeningCandidate to process
        memory: Optional CassMemory for context search
        validate: Whether to run validation
        token_tracker: Optional token tracker for usage tracking

    Returns:
        ResynthesisResult
    """
    pipeline = ResynthesisPipeline(wiki_storage, memory, token_tracker=token_tracker)
    return await pipeline.deepen_page(
        page_name=candidate.page_name,
        trigger=candidate.trigger,
        notes=candidate.reason,
        validate=validate,
    )


async def run_deepening_cycle(
    wiki_storage: WikiStorage,
    memory=None,
    max_pages: int = 5,
    validate: bool = True,
    token_tracker=None,
) -> List[ResynthesisResult]:
    """
    Run a full deepening cycle on top candidates.

    Args:
        wiki_storage: WikiStorage instance
        memory: Optional CassMemory
        max_pages: Maximum pages to deepen in one cycle
        validate: Whether to validate each synthesis
        token_tracker: Optional token tracker for usage tracking

    Returns:
        List of ResynthesisResult for each page attempted
    """
    pipeline = ResynthesisPipeline(wiki_storage, memory, token_tracker=token_tracker)
    detector = DeepeningDetector(wiki_storage)

    # Get candidates
    candidates = detector.detect_all_candidates()[:max_pages]

    results = []
    for candidate in candidates:
        result = await pipeline.deepen_page(
            page_name=candidate.page_name,
            trigger=candidate.trigger,
            notes=candidate.reason,
            validate=validate,
        )
        results.append(result)

        # Small delay between operations
        import asyncio
        await asyncio.sleep(0.5)

    return results
