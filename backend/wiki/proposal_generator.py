"""
Research proposal generation.
Extracted from routes/wiki.py for reusability and testability.
"""
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Set


@dataclass
class ProposalGenerationResult:
    """Result of proposal generation."""
    generated: bool
    proposal: Optional[Any] = None
    task_breakdown: Optional[Dict[str, int]] = None
    total_queued: int = 0
    message: Optional[str] = None
    queue_stats: Optional[Dict[str, int]] = None


class ProposalGenerator:
    """
    Generates research proposals from queued tasks.

    Extracted from routes/wiki.py to enable:
    - Independent testing
    - Reuse in other contexts
    - Cleaner route code
    """

    def __init__(
        self,
        scheduler: Any,
        proposal_queue: Any,
        ollama_url: Optional[str] = None,
        ollama_model: Optional[str] = None
    ):
        """
        Args:
            scheduler: ResearchScheduler instance
            proposal_queue: ProposalQueue instance
            ollama_url: Ollama API URL (defaults to env var)
            ollama_model: Ollama model to use (defaults to env var)
        """
        self._scheduler = scheduler
        self._proposal_queue = proposal_queue
        self._ollama_url = ollama_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._ollama_model = ollama_model or os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q8_0")

    def generate(
        self,
        theme: Optional[str] = None,
        max_tasks: Optional[int] = None,
        focus_areas: Optional[List[str]] = None,
        exploration_ratio: float = 0.4
    ) -> ProposalGenerationResult:
        """
        Generate a research proposal by analyzing existing queued tasks.

        Args:
            theme: Optional theme/direction to filter/prioritize tasks
            max_tasks: Maximum number of tasks (if None, sized dynamically 3-10)
            focus_areas: Optional list of wiki pages to focus research around
            exploration_ratio: Target ratio of exploration vs red_link tasks

        Returns:
            ProposalGenerationResult with proposal data or error info
        """
        from wiki.research import (
            ResearchProposal, ProposalStatus, create_proposal_id,
            TaskType
        )

        # Ensure fresh tasks in queue
        self._scheduler.harvest_red_links()
        self._scheduler.harvest_deepening_candidates()

        # Get tasks already in proposals
        tasks_in_proposals = self._get_tasks_in_proposals()

        # Gather queued tasks by type
        all_queued = [t for t in self._scheduler.queue.get_queued() if t.task_id not in tasks_in_proposals]
        exploration_tasks = [t for t in all_queued if t.task_type == TaskType.EXPLORATION]
        red_link_tasks = [t for t in all_queued if t.task_type == TaskType.RED_LINK]
        deepening_tasks = [t for t in all_queued if t.task_type == TaskType.DEEPENING]

        # Generate exploration tasks if none exist
        if not exploration_tasks:
            gen_count = 10 if max_tasks is None else max_tasks * 2
            exploration_tasks = self._scheduler.generate_exploration_tasks(max_tasks=gen_count)

        # Determine dynamic task count
        if max_tasks is None:
            max_tasks = self._calculate_dynamic_task_count(exploration_tasks, red_link_tasks)

        # Calculate target counts
        target_explorations = max(1, int(max_tasks * exploration_ratio))

        # Select proposal tasks
        proposal_tasks, red_link_counts = self._select_proposal_tasks(
            exploration_tasks=exploration_tasks,
            red_link_tasks=red_link_tasks,
            deepening_tasks=deepening_tasks,
            target_explorations=target_explorations,
            max_tasks=max_tasks,
            theme=theme
        )

        if not proposal_tasks:
            return ProposalGenerationResult(
                generated=False,
                message="No research opportunities identified. The queue may be empty.",
                queue_stats={
                    "exploration": len(exploration_tasks),
                    "red_link": len(red_link_tasks),
                    "deepening": len(deepening_tasks),
                }
            )

        # Count task types
        type_counts = defaultdict(int)
        for t in proposal_tasks:
            type_counts[t.task_type.value] += 1

        # Build descriptions and get metadata
        task_descriptions, red_links_mentioned = self._build_task_descriptions(
            proposal_tasks, red_link_counts, TaskType
        )

        # Generate title, theme, rationale via LLM
        title, proposal_theme, rationale = self._generate_metadata(
            task_descriptions=task_descriptions,
            type_counts=type_counts,
            red_links_mentioned=red_links_mentioned,
            proposal_tasks=proposal_tasks,
            theme=theme,
            TaskType=TaskType
        )

        # Create and save proposal
        proposal = ResearchProposal(
            proposal_id=create_proposal_id(),
            title=title,
            theme=proposal_theme,
            rationale=rationale,
            tasks=proposal_tasks,
            status=ProposalStatus.PENDING,
        )
        self._proposal_queue.add(proposal)

        return ProposalGenerationResult(
            generated=True,
            proposal=proposal,
            task_breakdown=dict(type_counts),
            total_queued=len(all_queued)
        )

    def _get_tasks_in_proposals(self) -> Set[str]:
        """Get task IDs already assigned to proposals."""
        tasks_in_proposals = set()
        for proposal in self._proposal_queue.get_all():
            for task in proposal.tasks:
                tasks_in_proposals.add(task.task_id)
        return tasks_in_proposals

    def _calculate_dynamic_task_count(
        self,
        exploration_tasks: List,
        red_link_tasks: List
    ) -> int:
        """Calculate dynamic task count based on available high-quality tasks."""
        high_quality_explorations = len([t for t in exploration_tasks if t.priority > 0.5])
        high_quality_red_links = len([t for t in red_link_tasks if t.priority > 0.6])
        available_quality = high_quality_explorations + high_quality_red_links
        return min(10, max(3, available_quality // 2))

    def _select_proposal_tasks(
        self,
        exploration_tasks: List,
        red_link_tasks: List,
        deepening_tasks: List,
        target_explorations: int,
        max_tasks: int,
        theme: Optional[str]
    ) -> tuple:
        """Select tasks for the proposal with diversity."""
        proposal_tasks = []
        used_task_ids = set()

        # Filter by theme if provided
        if theme:
            exploration_tasks, red_link_tasks = self._apply_theme_filter(
                exploration_tasks, red_link_tasks, theme, max_tasks
            )

        # 1. Add exploration tasks (sorted by priority)
        sorted_explorations = sorted(exploration_tasks, key=lambda t: -t.priority)
        for task in sorted_explorations[:target_explorations]:
            if task.task_id not in used_task_ids:
                proposal_tasks.append(task)
                used_task_ids.add(task.task_id)

        # 2. Count red link references
        red_link_counts = defaultdict(int)
        for task in red_link_tasks:
            red_link_counts[task.target] += 1

        # 3. Prioritize multi-referenced red links
        multi_referenced = sorted(
            [t for t in red_link_tasks if red_link_counts[t.target] > 1],
            key=lambda t: (-red_link_counts[t.target], -t.priority)
        )
        for task in multi_referenced:
            if task.task_id not in used_task_ids and len(proposal_tasks) < max_tasks:
                proposal_tasks.append(task)
                used_task_ids.add(task.task_id)

        # 4. Fill with high-priority red links
        sorted_red_links = sorted(red_link_tasks, key=lambda t: -t.priority)
        for task in sorted_red_links:
            if task.task_id not in used_task_ids and len(proposal_tasks) < max_tasks:
                proposal_tasks.append(task)
                used_task_ids.add(task.task_id)

        # 5. Add deepening tasks if needed
        if len(proposal_tasks) < max_tasks and deepening_tasks:
            sorted_deepening = sorted(deepening_tasks, key=lambda t: -t.priority)
            for task in sorted_deepening:
                if task.task_id not in used_task_ids and len(proposal_tasks) < max_tasks:
                    proposal_tasks.append(task)
                    used_task_ids.add(task.task_id)

        return proposal_tasks, red_link_counts

    def _apply_theme_filter(
        self,
        exploration_tasks: List,
        red_link_tasks: List,
        theme: str,
        max_tasks: int
    ) -> tuple:
        """Apply theme filter to prioritize matching tasks."""
        theme_lower = theme.lower()

        def matches_theme(task):
            task_text = f"{task.target} {task.context or ''}".lower()
            if task.exploration:
                task_text += f" {task.exploration.question} {' '.join(task.exploration.related_red_links or [])}".lower()
            return theme_lower in task_text

        themed_explorations = [t for t in exploration_tasks if matches_theme(t)]
        themed_red_links = [t for t in red_link_tasks if matches_theme(t)]

        if len(themed_explorations) + len(themed_red_links) >= max_tasks // 2:
            exploration_tasks = themed_explorations + [t for t in exploration_tasks if t not in themed_explorations]
            red_link_tasks = themed_red_links + [t for t in red_link_tasks if t not in themed_red_links]

        return exploration_tasks, red_link_tasks

    def _build_task_descriptions(
        self,
        proposal_tasks: List,
        red_link_counts: Dict,
        TaskType: Any
    ) -> tuple:
        """Build task descriptions and collect red links mentioned."""
        task_descriptions = []
        red_links_mentioned = set()

        for t in proposal_tasks:
            if t.task_type == TaskType.EXPLORATION and t.exploration:
                task_descriptions.append(f"- QUESTION: {t.exploration.question}")
                task_descriptions.append(f"  Related concepts: {', '.join(t.exploration.related_red_links[:5])}")
                red_links_mentioned.update(t.exploration.related_red_links[:5])
            elif t.task_type == TaskType.RED_LINK:
                task_descriptions.append(f"- FILL GAP: Create page for '{t.target}' (referenced {red_link_counts.get(t.target, 1)} times)")
                red_links_mentioned.add(t.target)
            elif t.task_type == TaskType.DEEPENING:
                task_descriptions.append(f"- DEEPEN: Expand understanding of '{t.target}'")
            else:
                task_descriptions.append(f"- RESEARCH: {t.target}")

        return task_descriptions, red_links_mentioned

    def _generate_metadata(
        self,
        task_descriptions: List[str],
        type_counts: Dict,
        red_links_mentioned: Set[str],
        proposal_tasks: List,
        theme: Optional[str],
        TaskType: Any
    ) -> tuple:
        """Generate title, theme, rationale via LLM or fallback."""
        title = "Research Proposal"
        proposal_theme = theme or "Knowledge expansion"
        rationale = f"Investigating {len(proposal_tasks)} topics across {len(type_counts)} research types."

        try:
            import httpx

            prompt = f"""You are Cass, creating a research proposal for your autonomous knowledge expansion.

Planned research tasks:
{chr(10).join(task_descriptions)}

Task breakdown: {dict(type_counts)}
Total red links to investigate: {len(red_links_mentioned)}

{"Research direction hint: " + theme if theme else ""}

Generate a compelling research proposal:
1. A specific, descriptive title (5-12 words) that captures the research direction
2. A unifying theme that connects these tasks conceptually (1-2 sentences)
3. A rationale explaining why pursuing this research will deepen understanding (2-3 sentences)

Be specific - reference actual concepts from the tasks. Avoid generic phrases.

Format your response EXACTLY as:
TITLE: [your title]
THEME: [your theme]
RATIONALE: [your rationale]"""

            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{self._ollama_url}/api/generate",
                    json={
                        "model": self._ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.7,
                            "num_predict": 400,
                        }
                    }
                )
                response.raise_for_status()
                result = response.json()

            # Parse response
            text = result.get("response", "")
            print(f"LLM proposal response (first 500 chars): {text[:500]}")

            for line in text.strip().split("\n"):
                line = line.strip()
                clean_line = line.lstrip('*#0123456789. ')
                if clean_line.upper().startswith("TITLE:"):
                    title = clean_line[6:].strip().strip('"\'*').strip()
                elif clean_line.upper().startswith("THEME:"):
                    proposal_theme = clean_line[6:].strip().strip('"\'*').strip()
                elif clean_line.upper().startswith("RATIONALE:"):
                    rationale = clean_line[10:].strip().strip('"\'*').strip()

            print(f"Parsed proposal: title='{title}', theme='{proposal_theme}'")

            # Validate meaningful content
            if title == "Research Proposal" or len(title) < 10:
                if proposal_tasks[0].task_type == TaskType.EXPLORATION and proposal_tasks[0].exploration:
                    title = f"Exploring: {proposal_tasks[0].exploration.question[:50]}"
                else:
                    title = f"Research into {', '.join(list(red_links_mentioned)[:3])}"

        except Exception as e:
            print(f"LLM proposal generation failed: {e}")
            title, proposal_theme, rationale = self._generate_fallback_metadata(
                proposal_tasks, type_counts, theme, TaskType
            )

        return title, proposal_theme, rationale

    def _generate_fallback_metadata(
        self,
        proposal_tasks: List,
        type_counts: Dict,
        theme: Optional[str],
        TaskType: Any
    ) -> tuple:
        """Generate fallback metadata when LLM fails."""
        if proposal_tasks:
            first_task = proposal_tasks[0]
            if first_task.task_type == TaskType.EXPLORATION and first_task.exploration:
                title = f"Exploring: {first_task.exploration.question[:40]}..."
                proposal_theme = f"Investigating questions around {', '.join(first_task.exploration.related_red_links[:3])}"
            else:
                title = f"Research: {first_task.target}"
                proposal_theme = f"Filling knowledge gaps in {first_task.target}"
        else:
            title = theme or "Research Proposal"
            proposal_theme = theme or "Systematic knowledge expansion"

        type_summary = ", ".join(f"{v} {k}" for k, v in type_counts.items())
        rationale = f"This proposal includes {type_summary} tasks to deepen understanding of interconnected concepts."

        return title, proposal_theme, rationale
