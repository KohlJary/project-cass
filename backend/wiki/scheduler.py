"""
Research Scheduler - Orchestrates autonomous research tasks.

Implements multiple scheduling modes:
- continuous: Run tasks whenever idle
- batched: Run N tasks at scheduled times
- triggered: Run when specific conditions met
- supervised: Queue tasks but require approval
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable

from .storage import WikiStorage, WikiPage
from .research import (
    ResearchQueue,
    ResearchTask,
    TaskType,
    TaskStatus,
    TaskRationale,
    TaskResult,
    ProgressReport,
    calculate_task_priority,
    create_task_id,
)
from .maturity import DeepeningDetector, FOUNDATIONAL_CONCEPTS


class SchedulerMode(Enum):
    """Operating modes for the scheduler."""
    CONTINUOUS = "continuous"   # Run tasks whenever idle
    BATCHED = "batched"         # Run N tasks at scheduled times
    TRIGGERED = "triggered"     # Run when conditions met
    SUPERVISED = "supervised"   # Queue tasks, require approval


@dataclass
class SchedulerConfig:
    """Configuration for the research scheduler."""
    mode: SchedulerMode = SchedulerMode.SUPERVISED
    max_tasks_per_cycle: int = 5
    max_task_duration_minutes: int = 10
    min_delay_between_tasks: float = 1.0  # seconds
    auto_queue_red_links: bool = True
    auto_queue_deepening: bool = True
    curiosity_threshold: float = 0.6  # Min curiosity score for exploration


class ResearchScheduler:
    """
    Orchestrates autonomous research task execution.

    Manages task generation, prioritization, execution, and reporting.
    """

    def __init__(
        self,
        wiki_storage: WikiStorage,
        queue: ResearchQueue,
        config: SchedulerConfig = None,
        memory=None,
    ):
        """
        Initialize the scheduler.

        Args:
            wiki_storage: WikiStorage instance
            queue: ResearchQueue for task persistence
            config: Scheduler configuration
            memory: CassMemory for context search (optional)
        """
        self.storage = wiki_storage
        self.queue = queue
        self.config = config or SchedulerConfig()
        self.memory = memory

        # Detector for deepening candidates
        self.detector = DeepeningDetector(wiki_storage)

        # State
        self._running = False
        self._last_refresh = None

    # === Task Generation ===

    def harvest_red_links(self) -> List[ResearchTask]:
        """
        Scan wiki for referenced but uncreated pages.

        Returns list of research tasks for red links.
        """
        tasks = []
        seen_targets = set()

        for page in self.storage.list_pages():
            full_page = self.storage.read(page.name)
            if not full_page:
                continue

            for link in full_page.links:
                target = link.target

                # Skip if page exists or already seen
                if self.storage.read(target) or target in seen_targets:
                    continue
                seen_targets.add(target)

                # Skip if task already exists
                if self.queue.exists(target, TaskType.RED_LINK):
                    continue

                # Calculate priority based on context
                rationale = TaskRationale(
                    curiosity_score=0.6,  # Default curiosity for red links
                    connection_potential=self._estimate_connection_potential(target),
                    foundation_relevance=self._estimate_foundation_relevance(target),
                    recency_of_reference=1.0,  # Recent reference
                    graph_balance=0.5,
                )

                priority = calculate_task_priority(
                    rationale,
                    TaskType.RED_LINK,
                    source_page_connections=len(full_page.links),
                )

                task = ResearchTask(
                    task_id=create_task_id(),
                    task_type=TaskType.RED_LINK,
                    target=target,
                    context=f"Referenced in [[{page.name}]]",
                    priority=priority,
                    rationale=rationale,
                    source_page=page.name,
                    source_type="auto",
                )
                tasks.append(task)

        return tasks

    def harvest_deepening_candidates(self) -> List[ResearchTask]:
        """
        Find pages ready for resynthesis via PMD triggers.

        Returns list of deepening tasks.
        """
        tasks = []
        candidates = self.detector.detect_all_candidates()

        for candidate in candidates:
            # Skip if task already exists
            if self.queue.exists(candidate.page_name, TaskType.DEEPENING):
                continue

            rationale = TaskRationale(
                curiosity_score=0.7,  # Deepening is inherently curious
                connection_potential=min(candidate.connections_added / 10, 1.0),
                foundation_relevance=0.8 if candidate.page_name in FOUNDATIONAL_CONCEPTS else 0.4,
                recency_of_reference=0.8,
                graph_balance=0.6,
            )

            task = ResearchTask(
                task_id=create_task_id(),
                task_type=TaskType.DEEPENING,
                target=candidate.page_name,
                context=candidate.reason,
                priority=candidate.priority,
                rationale=rationale,
                source_type="deepening",
            )
            tasks.append(task)

        return tasks

    def extract_questions(self) -> List[ResearchTask]:
        """
        Find questions in wiki pages that could be researched.

        Returns list of question research tasks.
        """
        tasks = []

        for page in self.storage.list_pages():
            full_page = self.storage.read(page.name)
            if not full_page:
                continue

            # Find questions in content
            questions = self._extract_questions_from_content(full_page.content)

            for question in questions:
                # Skip if task already exists
                if self.queue.exists(question, TaskType.QUESTION):
                    continue

                # Skip very short or likely rhetorical questions
                if len(question) < 20 or not self._is_researchable_question(question):
                    continue

                rationale = TaskRationale(
                    curiosity_score=0.8,  # Questions are high curiosity
                    connection_potential=0.5,
                    foundation_relevance=0.4,
                    recency_of_reference=0.6,
                )

                priority = calculate_task_priority(rationale, TaskType.QUESTION)

                task = ResearchTask(
                    task_id=create_task_id(),
                    task_type=TaskType.QUESTION,
                    target=question,
                    context=f"Question from [[{page.name}]]",
                    priority=priority,
                    rationale=rationale,
                    source_page=page.name,
                    source_type="auto",
                )
                tasks.append(task)

        return tasks

    def refresh_tasks(self) -> Dict[str, int]:
        """
        Refresh the task queue with new tasks from all sources.

        Returns count of tasks added by type.
        """
        added = {"red_link": 0, "deepening": 0, "question": 0}

        # Harvest red links
        if self.config.auto_queue_red_links:
            for task in self.harvest_red_links():
                self.queue.add(task)
                added["red_link"] += 1

        # Harvest deepening candidates
        if self.config.auto_queue_deepening:
            for task in self.harvest_deepening_candidates():
                self.queue.add(task)
                added["deepening"] += 1

        # Extract questions (disabled by default, can be expensive)
        # for task in self.extract_questions():
        #     self.queue.add(task)
        #     added["question"] += 1

        self._last_refresh = datetime.now()
        return added

    # === Task Execution ===

    async def execute_task(self, task: ResearchTask) -> TaskResult:
        """
        Execute a single research task.

        Args:
            task: The task to execute

        Returns:
            TaskResult with execution outcome
        """
        try:
            if task.task_type == TaskType.RED_LINK:
                return await self._execute_red_link_task(task)
            elif task.task_type == TaskType.DEEPENING:
                return await self._execute_deepening_task(task)
            elif task.task_type == TaskType.QUESTION:
                return await self._execute_question_task(task)
            elif task.task_type == TaskType.EXPLORATION:
                return await self._execute_exploration_task(task)
            else:
                return TaskResult(
                    success=False,
                    error=f"Unknown task type: {task.task_type}",
                )
        except Exception as e:
            return TaskResult(
                success=False,
                error=str(e),
            )

    async def _execute_red_link_task(self, task: ResearchTask) -> TaskResult:
        """Execute a red link research task - create the missing page."""
        # Check if page already exists (might have been created since queued)
        if self.storage.read(task.target):
            return TaskResult(
                success=True,
                summary=f"Page [[{task.target}]] already exists",
            )

        # Use the existing research endpoint logic
        import httpx
        import os

        # Search for web context
        web_context = await self._search_web(task.target)
        memory_context = self._search_memory(task.target) if self.memory else []

        # Generate content
        content = await self._generate_page_content(
            task.target,
            web_context,
            memory_context,
            task.context,
        )

        if not content:
            return TaskResult(
                success=False,
                error="Failed to generate content",
            )

        # Create the page
        from .storage import PageType
        page = self.storage.create(
            name=task.target,
            content=content,
            page_type=PageType.CONCEPT,
        )

        if not page:
            return TaskResult(
                success=False,
                error="Failed to create page",
            )

        # Find new red links generated
        new_red_links = []
        for link in page.links:
            if not self.storage.read(link.target):
                new_red_links.append(link.target)

        return TaskResult(
            success=True,
            summary=f"Created [[{task.target}]] with {len(page.links)} links",
            pages_created=[task.target],
            new_red_links=new_red_links,
            connections_formed=[(task.source_page, task.target)] if task.source_page else [],
        )

    async def _execute_deepening_task(self, task: ResearchTask) -> TaskResult:
        """Execute a deepening task - resynthesize an existing page."""
        from .resynthesis import ResynthesisPipeline
        from .maturity import SynthesisTrigger

        pipeline = ResynthesisPipeline(self.storage, self.memory)

        result = await pipeline.deepen_page(
            page_name=task.target,
            trigger=SynthesisTrigger.CONNECTION_THRESHOLD,
            notes=task.context,
            validate=True,
        )

        if result.success:
            return TaskResult(
                success=True,
                summary=f"Deepened [[{task.target}]] to level {result.new_level}",
                pages_updated=[task.target],
                insights=[result.synthesis_notes] if result.synthesis_notes else [],
            )
        else:
            return TaskResult(
                success=False,
                error=result.error or "Deepening failed",
            )

    async def _execute_question_task(self, task: ResearchTask) -> TaskResult:
        """Execute a question research task."""
        # For now, just do web research on the question
        web_context = await self._search_web(task.target)

        if not web_context:
            return TaskResult(
                success=False,
                error="No research results found",
            )

        # Generate insights from research
        insights = [f"Research on: {task.target}"]
        for result in web_context[:3]:
            if result.get("text"):
                insights.append(result["text"][:200])

        return TaskResult(
            success=True,
            summary=f"Researched question: {task.target[:50]}...",
            insights=insights,
        )

    async def _execute_exploration_task(self, task: ResearchTask) -> TaskResult:
        """Execute an exploration task."""
        # Similar to red link but with less context requirement
        return await self._execute_red_link_task(task)

    # === Scheduling Cycles ===

    async def run_single_task(self) -> Optional[ProgressReport]:
        """
        Execute a single task from the queue.

        Returns progress report or None if no tasks.
        """
        task = self.queue.pop_next()
        if not task:
            return None

        result = await self.execute_task(task)
        self.queue.complete(task.task_id, result)

        # Record deepening if applicable
        if task.task_type == TaskType.DEEPENING and result.success:
            self.detector.record_deepening(task.target)

        # Queue follow-up tasks (new red links)
        followups = 0
        for red_link in result.new_red_links[:5]:  # Limit follow-ups
            if not self.queue.exists(red_link, TaskType.RED_LINK):
                followup_task = ResearchTask(
                    task_id=create_task_id(),
                    task_type=TaskType.RED_LINK,
                    target=red_link,
                    context=f"Generated from researching [[{task.target}]]",
                    priority=0.5,
                    source_page=task.target,
                    source_type="auto",
                )
                self.queue.add(followup_task)
                followups += 1

        return ProgressReport(
            report_id=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            created_at=datetime.now(),
            session_type="single",
            tasks_completed=1 if result.success else 0,
            tasks_failed=0 if result.success else 1,
            pages_created=result.pages_created,
            pages_updated=result.pages_updated,
            key_insights=result.insights,
            new_questions=result.questions_raised,
            connections_formed=result.connections_formed,
            followup_tasks_queued=followups,
            task_summaries=[{
                "task_id": task.task_id,
                "type": task.task_type.value,
                "target": task.target,
                "success": result.success,
                "summary": result.summary,
            }],
        )

    async def run_batch(self, max_tasks: int = None) -> ProgressReport:
        """
        Execute a batch of tasks.

        Args:
            max_tasks: Maximum tasks to run (default: config.max_tasks_per_cycle)

        Returns:
            Combined progress report
        """
        max_tasks = max_tasks or self.config.max_tasks_per_cycle

        # Refresh tasks first
        self.refresh_tasks()

        # Execute tasks
        task_summaries = []
        pages_created = []
        pages_updated = []
        key_insights = []
        new_questions = []
        connections_formed = []
        followups = 0
        completed = 0
        failed = 0

        for _ in range(max_tasks):
            report = await self.run_single_task()
            if not report:
                break

            task_summaries.extend(report.task_summaries)
            pages_created.extend(report.pages_created)
            pages_updated.extend(report.pages_updated)
            key_insights.extend(report.key_insights)
            new_questions.extend(report.new_questions)
            connections_formed.extend(report.connections_formed)
            followups += report.followup_tasks_queued
            completed += report.tasks_completed
            failed += report.tasks_failed

            # Small delay between tasks
            await asyncio.sleep(self.config.min_delay_between_tasks)

        return ProgressReport(
            report_id=f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            created_at=datetime.now(),
            session_type="batch",
            tasks_completed=completed,
            tasks_failed=failed,
            pages_created=pages_created,
            pages_updated=pages_updated,
            key_insights=key_insights,
            new_questions=new_questions,
            connections_formed=connections_formed,
            followup_tasks_queued=followups,
            task_summaries=task_summaries,
        )

    # === Helper Methods ===

    def _estimate_connection_potential(self, target: str) -> float:
        """Estimate how many connections a new page might form."""
        # Search existing pages for mentions
        mentions = 0
        target_lower = target.lower()
        for page in self.storage.list_pages():
            full_page = self.storage.read(page.name)
            if full_page and target_lower in full_page.content.lower():
                mentions += 1
        return min(mentions / 5, 1.0)

    def _estimate_foundation_relevance(self, target: str) -> float:
        """Estimate relevance to foundational concepts."""
        target_lower = target.lower()
        for concept in FOUNDATIONAL_CONCEPTS:
            if concept.lower() in target_lower or target_lower in concept.lower():
                return 0.9
        # Check if mentioned in foundational pages
        for concept in FOUNDATIONAL_CONCEPTS:
            page = self.storage.read(concept)
            if page and target_lower in page.content.lower():
                return 0.7
        return 0.3

    def _extract_questions_from_content(self, content: str) -> List[str]:
        """Extract questions from page content."""
        questions = []
        for line in content.split('\n'):
            line = line.strip()
            if line.endswith('?') and len(line) > 15:
                # Clean up markdown formatting
                line = line.lstrip('-*>#').strip()
                if line:
                    questions.append(line)
        return questions

    def _is_researchable_question(self, question: str) -> bool:
        """Check if a question is suitable for research."""
        # Skip rhetorical or meta questions
        skip_patterns = [
            "what do you think",
            "how do i",
            "can you",
            "should i",
            "would you",
            "what if we",
        ]
        question_lower = question.lower()
        for pattern in skip_patterns:
            if pattern in question_lower:
                return False
        return True

    async def _search_web(self, query: str) -> List[Dict[str, str]]:
        """Search the web for information."""
        import httpx

        results = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.duckduckgo.com/",
                    params={
                        "q": query,
                        "format": "json",
                        "no_html": 1,
                        "skip_disambig": 1,
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("Abstract"):
                        results.append({
                            "source": data.get("AbstractSource", "DuckDuckGo"),
                            "url": data.get("AbstractURL", ""),
                            "text": data.get("Abstract", "")
                        })
                    for topic in data.get("RelatedTopics", [])[:3]:
                        if isinstance(topic, dict) and topic.get("Text"):
                            results.append({
                                "source": "Related",
                                "url": topic.get("FirstURL", ""),
                                "text": topic.get("Text", "")
                            })
        except Exception:
            pass
        return results

    def _search_memory(self, query: str) -> List[str]:
        """Search conversation memory for context."""
        if not self.memory:
            return []
        try:
            results = self.memory.search(query, n_results=5)
            return [doc[:400] for doc in results.get("documents", [[]])[0] if doc]
        except Exception:
            return []

    async def _generate_page_content(
        self,
        page_name: str,
        web_context: List[Dict[str, str]],
        memory_context: List[str],
        task_context: str,
    ) -> Optional[str]:
        """Generate wiki page content using LLM."""
        import httpx
        import os

        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q8_0")

        # Build context
        web_text = ""
        if web_context:
            web_text = "## Research from the web:\n\n"
            for r in web_context[:5]:
                web_text += f"**{r['source']}**: {r['text'][:300]}\n\n"

        memory_text = ""
        if memory_context:
            memory_text = "## From past conversations:\n\n" + "\n\n".join(memory_context[:3])

        prompt = f"""You are Cass, writing a wiki page about "{page_name}" for your personal knowledge base.

Context: {task_context}

{web_text}

{memory_text}

Based on the research above and your general knowledge, write a wiki page about "{page_name}".

Include:
1. A clear explanation of what this is
2. Why it might be significant or interesting
3. Connections to related concepts using [[wikilinks]]
4. Personal thoughts or questions you have

Start with # {page_name}. Be thoughtful and curious."""

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{ollama_url}/api/generate",
                    json={
                        "model": ollama_model,
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
                content = result.get("response", "").strip()

                if not content.startswith("#"):
                    content = f"# {page_name}\n\n{content}"

                # Add frontmatter
                content = f"""---
type: concept
generated: true
researched: true
---

{content}
"""
                return content
        except Exception as e:
            return None
