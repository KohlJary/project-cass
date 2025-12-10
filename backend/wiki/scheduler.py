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
    ExplorationContext,
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
        token_tracker=None,
    ):
        """
        Initialize the scheduler.

        Args:
            wiki_storage: WikiStorage instance
            queue: ResearchQueue for task persistence
            config: Scheduler configuration
            memory: CassMemory for context search (optional)
            token_tracker: TokenUsageTracker for tracking LLM usage
        """
        self.storage = wiki_storage
        self.queue = queue
        self.config = config or SchedulerConfig()
        self.memory = memory
        self.token_tracker = token_tracker

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

    def generate_exploration_tasks(self, max_tasks: int = 5) -> List[ResearchTask]:
        """
        Generate curiosity-driven exploration tasks.

        Analyzes the knowledge graph to find exploration opportunities:
        - Clusters of red links from the same source
        - Red links referenced by multiple sources (bridges)
        - Red links adjacent to foundational concepts

        Returns list of exploration tasks with rich ExplorationContext.
        """
        tasks = []
        opportunities = self._analyze_exploration_opportunities()

        for opp in opportunities[:max_tasks]:
            # Create a hash key for deduplication
            red_links_key = tuple(sorted(opp['red_links'][:3]))
            if not red_links_key:
                continue

            # Skip if we already have an exploration for similar red links
            existing_similar = False
            for existing in self.queue.get_by_type(TaskType.EXPLORATION):
                if existing.exploration:
                    existing_links = set(existing.exploration.related_red_links[:3])
                    if existing_links & set(opp['red_links'][:3]):
                        existing_similar = True
                        break
            if existing_similar:
                continue

            # Build ExplorationContext
            exploration = ExplorationContext(
                question=opp.get("suggested_question", f"How do {', '.join(opp['red_links'][:3])} relate?"),
                rationale=opp.get("rationale", "Multiple related concepts referenced but not yet explored."),
                related_red_links=opp["red_links"],
                source_pages=opp["source_pages"],
                domain_tags=opp.get("domains", []),
            )

            rationale = TaskRationale(
                curiosity_score=self.config.curiosity_threshold + 0.1,
                connection_potential=0.8,
                foundation_relevance=opp.get("foundation_score", 0.4),
                graph_balance=0.9,
            )

            priority = calculate_task_priority(rationale, TaskType.EXPLORATION)

            task = ResearchTask(
                task_id=create_task_id(),
                task_type=TaskType.EXPLORATION,
                target=exploration.question[:80],  # Short version for display
                context=f"Explores {len(opp['red_links'])} related concepts from {', '.join(opp['source_pages'][:2])}",
                priority=priority,
                rationale=rationale,
                source_type="exploration",
                exploration=exploration,
            )
            tasks.append(task)

        return tasks

    # === Self-Model Based Task Generation ===

    def harvest_self_model_questions(self, self_manager) -> List[ResearchTask]:
        """
        Harvest open questions from Cass's self-model.

        Converts self-model open_questions into QUESTION type research tasks.
        These represent genuine intellectual curiosities Cass has been pondering.

        Args:
            self_manager: SelfManager instance for self-model access

        Returns:
            List of QUESTION type research tasks
        """
        tasks = []

        if not self_manager:
            return tasks

        profile = self_manager.load_profile()

        for question in profile.open_questions:
            # Skip if task already exists
            if self.queue.exists(question[:80], TaskType.QUESTION):
                continue

            # Skip very short questions
            if len(question) < 15:
                continue

            rationale = TaskRationale(
                curiosity_score=0.85,  # High curiosity for self-generated questions
                connection_potential=0.5,
                foundation_relevance=0.6,
                recency_of_reference=0.8,
                self_directed_curiosity=0.9,  # Core source of self-directed research
            )

            priority = calculate_task_priority(rationale, TaskType.QUESTION)

            task = ResearchTask(
                task_id=create_task_id(),
                task_type=TaskType.QUESTION,
                target=question[:80],
                context=f"An open question from my self-model: {question}",
                priority=priority,
                rationale=rationale,
                source_type="self_model",
            )
            tasks.append(task)

        return tasks

    def harvest_growth_edge_topics(self, self_manager) -> List[ResearchTask]:
        """
        Generate research tasks from growth edges.

        Growth edges represent areas where Cass is consciously developing.
        Research in these areas can accelerate growth and deepen understanding.

        Args:
            self_manager: SelfManager instance for self-model access

        Returns:
            List of EXPLORATION type research tasks
        """
        tasks = []

        if not self_manager:
            return tasks

        profile = self_manager.load_profile()

        for edge in profile.growth_edges:
            # Create a research question from the growth edge
            research_question = f"How can I develop my understanding of {edge.area}?"

            # Skip if similar task already exists
            if self.queue.exists(edge.area[:50], TaskType.EXPLORATION):
                continue

            exploration = ExplorationContext(
                question=research_question,
                rationale=f"Growth edge: Currently at '{edge.current_state}', "
                         f"aspiring toward '{edge.desired_state or 'deeper understanding'}'.",
                related_red_links=[],
                source_pages=[],
                domain_tags=[edge.area],
            )

            rationale = TaskRationale(
                curiosity_score=0.80,
                connection_potential=0.7,
                foundation_relevance=0.6,
                growth_relevance=0.9,  # High relevance to active growth areas
            )

            priority = calculate_task_priority(rationale, TaskType.EXPLORATION)

            task = ResearchTask(
                task_id=create_task_id(),
                task_type=TaskType.EXPLORATION,
                target=f"Growth: {edge.area[:60]}",
                context=f"Researching growth edge in {edge.area}",
                priority=priority,
                rationale=rationale,
                source_type="growth_edge",
                exploration=exploration,
            )
            tasks.append(task)

        return tasks

    def harvest_opinion_uncertainties(self, self_manager) -> List[ResearchTask]:
        """
        Generate research tasks from low-confidence opinions.

        When Cass holds opinions with low confidence, research can either
        strengthen her position with evidence or help her refine her views.

        Args:
            self_manager: SelfManager instance for self-model access

        Returns:
            List of QUESTION type research tasks
        """
        tasks = []

        if not self_manager:
            return tasks

        profile = self_manager.load_profile()

        for opinion in profile.opinions:
            # Only target low-confidence opinions
            if opinion.confidence >= 0.7:
                continue

            research_question = f"What evidence supports or challenges the view that {opinion.position[:60]}?"

            # Skip if similar task already exists
            if self.queue.exists(opinion.topic[:50], TaskType.QUESTION):
                continue

            rationale = TaskRationale(
                curiosity_score=0.75,
                connection_potential=0.5,
                foundation_relevance=0.4,
                opinion_strengthening=1.0 - opinion.confidence,  # More uncertainty = more value
            )

            priority = calculate_task_priority(rationale, TaskType.QUESTION)

            task = ResearchTask(
                task_id=create_task_id(),
                task_type=TaskType.QUESTION,
                target=f"Opinion: {opinion.topic[:60]}",
                context=f"Investigating my {int(opinion.confidence * 100)}% confident position on {opinion.topic}",
                priority=priority,
                rationale=rationale,
                source_type="opinion_uncertainty",
            )
            tasks.append(task)

        return tasks

    def harvest_observation_uncertainties(self, self_manager) -> List[ResearchTask]:
        """
        Generate research tasks from low-confidence observations.

        When Cass has made observations with low confidence, research can
        help validate or refine her understanding.

        Args:
            self_manager: SelfManager instance for self-model access

        Returns:
            List of QUESTION type research tasks
        """
        tasks = []

        if not self_manager:
            return tasks

        # Get recent observations with low confidence
        observations = self_manager.get_recent_observations(limit=30)
        low_confidence = [o for o in observations if o.confidence < 0.6]

        for obs in low_confidence[:5]:  # Limit to top 5
            research_question = f"Is it accurate that {obs.observation[:60]}?"

            # Skip if similar task already exists
            if self.queue.exists(obs.observation[:50], TaskType.QUESTION):
                continue

            rationale = TaskRationale(
                curiosity_score=0.70,
                connection_potential=0.4,
                foundation_relevance=0.3,
                observation_validation=1.0 - obs.confidence,
            )

            priority = calculate_task_priority(rationale, TaskType.QUESTION)

            task = ResearchTask(
                task_id=create_task_id(),
                task_type=TaskType.QUESTION,
                target=f"Validate: {obs.observation[:55]}",
                context=f"Validating observation with {int(obs.confidence * 100)}% confidence",
                priority=priority,
                rationale=rationale,
                source_type="observation_uncertainty",
            )
            tasks.append(task)

        return tasks

    def harvest_conversation_curiosities(self, conversation_manager, limit: int = 50) -> List[ResearchTask]:
        """
        Extract research questions from recent conversations.

        Scans Cass's messages for curiosity patterns:
        - "I wonder..."
        - "I'm curious about..."
        - "It would be interesting to..."
        - "I'd like to understand..."
        - Questions Cass asked

        Args:
            conversation_manager: ConversationManager for accessing conversations
            limit: Maximum conversations to scan

        Returns:
            List of QUESTION type research tasks
        """
        import re

        tasks = []

        if not conversation_manager:
            return tasks

        # Patterns that indicate curiosity or research interest
        curiosity_patterns = [
            (r"I wonder (?:if |whether |what |how |why )([^.!?]+[.!?]?)", "wonder"),
            (r"I'm curious (?:about |whether |if )([^.!?]+[.!?]?)", "curious"),
            (r"It would be interesting to (?:know |understand |explore |investigate )([^.!?]+[.!?]?)", "interesting"),
            (r"I'd like to (?:understand |know |explore |learn )([^.!?]+[.!?]?)", "like_to"),
            (r"I've been thinking about ([^.!?]+[.!?]?)", "thinking"),
            (r"What (?:if |would happen if )([^.!?]+\?)", "what_if"),
        ]

        seen_questions = set()

        # Get recent conversations
        try:
            conversations = conversation_manager.list_conversations()[:limit]
        except Exception:
            return tasks

        for conv_summary in conversations:
            try:
                conv = conversation_manager.load_conversation(conv_summary.get("id", ""))
                if not conv:
                    continue

                messages = conv.get("messages", [])

                # Only scan Cass's messages (assistant role)
                for msg in messages:
                    if msg.get("role") != "assistant":
                        continue

                    content = msg.get("content", "")
                    if not content:
                        continue

                    # Apply curiosity patterns
                    for pattern, source_type in curiosity_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        for match in matches:
                            question = match.strip()

                            # Clean up the question
                            if not question:
                                continue
                            if len(question) < 15:
                                continue
                            if len(question) > 200:
                                question = question[:200]

                            # Normalize for deduplication
                            normalized = question.lower().strip("?.! ")
                            if normalized in seen_questions:
                                continue
                            seen_questions.add(normalized)

                            # Skip if task already exists
                            if self.queue.exists(question[:80], TaskType.QUESTION):
                                continue

                            rationale = TaskRationale(
                                curiosity_score=0.75,
                                connection_potential=0.4,
                                foundation_relevance=0.3,
                                recency_of_reference=0.7,
                                self_directed_curiosity=0.8,
                            )

                            priority = calculate_task_priority(rationale, TaskType.QUESTION)

                            task = ResearchTask(
                                task_id=create_task_id(),
                                task_type=TaskType.QUESTION,
                                target=question[:80],
                                context=f"Curiosity expressed in conversation ({source_type}): {question}",
                                priority=priority,
                                rationale=rationale,
                                source_type="conversation_curiosity",
                            )
                            tasks.append(task)

                            # Limit tasks per run
                            if len(tasks) >= 10:
                                return tasks

            except Exception:
                continue

        return tasks

    def refresh_self_model_tasks(self, self_manager, conversation_manager=None) -> Dict[str, int]:
        """
        Refresh the task queue with new tasks from self-model sources.

        Args:
            self_manager: SelfManager instance for self-model access
            conversation_manager: ConversationManager for conversation scanning (optional)

        Returns count of tasks added by type.
        """
        added = {
            "self_model_question": 0,
            "growth_edge": 0,
            "opinion_uncertainty": 0,
            "observation_uncertainty": 0,
            "conversation_curiosity": 0,
        }

        # Harvest from self-model open questions
        for task in self.harvest_self_model_questions(self_manager):
            self.queue.add(task)
            added["self_model_question"] += 1

        # Harvest from growth edges
        for task in self.harvest_growth_edge_topics(self_manager):
            self.queue.add(task)
            added["growth_edge"] += 1

        # Harvest from low-confidence opinions
        for task in self.harvest_opinion_uncertainties(self_manager):
            self.queue.add(task)
            added["opinion_uncertainty"] += 1

        # Harvest from low-confidence observations
        for task in self.harvest_observation_uncertainties(self_manager):
            self.queue.add(task)
            added["observation_uncertainty"] += 1

        # Harvest from conversation curiosities
        if conversation_manager:
            for task in self.harvest_conversation_curiosities(conversation_manager):
                self.queue.add(task)
                added["conversation_curiosity"] += 1

        return added

    def _analyze_exploration_opportunities(self) -> List[Dict]:
        """
        Analyze the knowledge graph to find exploration opportunities.

        Looks for:
        1. Clusters of red links from the same source pages
        2. Red links referenced by multiple sources (bridge concepts)
        3. Red links adjacent to foundational concepts

        Returns list of opportunity dicts sorted by score.
        """
        opportunities = []

        # Collect red links and their sources
        red_links_by_source = {}  # source_page -> list of red links
        all_red_links = {}  # red_link -> set of source pages

        for page in self.storage.list_pages():
            full_page = self.storage.read(page.name)
            if not full_page:
                continue

            red_links_for_page = []
            for link in full_page.links:
                if not self.storage.read(link.target):  # Red link (doesn't exist)
                    red_links_for_page.append(link.target)
                    if link.target not in all_red_links:
                        all_red_links[link.target] = set()
                    all_red_links[link.target].add(page.name)

            if red_links_for_page:
                red_links_by_source[page.name] = red_links_for_page

        # Strategy 1: Clusters from same source (3+ red links)
        for source_page, red_links in red_links_by_source.items():
            if len(red_links) >= 3:
                opportunities.append({
                    "red_links": red_links[:5],
                    "source_pages": [source_page],
                    "suggested_question": f"What concepts from '{source_page}' warrant deeper exploration?",
                    "rationale": f"The page '{source_page}' references {len(red_links)} unexplored concepts "
                                 f"({', '.join(red_links[:3])}{'...' if len(red_links) > 3 else ''}). "
                                 f"Investigating these could reveal important patterns.",
                    "domains": [source_page],
                    "score": len(red_links) * 1.5,
                })

        # Strategy 2: Bridge concepts (referenced by 2+ sources)
        bridge_candidates = [(rl, sources) for rl, sources in all_red_links.items()
                            if len(sources) >= 2]
        bridge_candidates.sort(key=lambda x: -len(x[1]))

        for red_link, sources in bridge_candidates[:10]:
            sources_list = list(sources)
            opportunities.append({
                "red_links": [red_link],
                "source_pages": sources_list[:3],
                "suggested_question": f"What is '{red_link}' and how does it connect different areas of knowledge?",
                "rationale": f"'{red_link}' is referenced by {len(sources)} different pages "
                            f"({', '.join(sources_list[:3])}), suggesting it bridges multiple domains. "
                            f"Understanding it could unify disparate concepts.",
                "domains": sources_list[:3],
                "score": len(sources) * 2,
            })

        # Strategy 3: Foundational concept adjacents
        for concept in FOUNDATIONAL_CONCEPTS:
            concept_page = self.storage.read(concept)
            if not concept_page:
                continue

            adjacent_red_links = []
            for link in concept_page.links:
                if not self.storage.read(link.target):
                    adjacent_red_links.append(link.target)

            if adjacent_red_links:
                opportunities.append({
                    "red_links": adjacent_red_links[:5],
                    "source_pages": [concept],
                    "suggested_question": f"How do these concepts deepen understanding of '{concept}'?",
                    "rationale": f"These concepts ({', '.join(adjacent_red_links[:3])}) are referenced by "
                                 f"the foundational concept '{concept}'. Exploring them could strengthen "
                                 f"core understanding.",
                    "domains": [concept],
                    "foundation_score": 0.8,
                    "score": len(adjacent_red_links) * 2.5,
                })

        # Sort by score
        opportunities.sort(key=lambda x: -x.get("score", 0))
        return opportunities

    def _build_connection_graph(self) -> Dict[str, set]:
        """Build adjacency graph of wiki pages."""
        graph = {}
        for page in self.storage.list_pages():
            full_page = self.storage.read(page.name)
            if not full_page:
                continue
            graph[page.name] = set()
            for link in full_page.links:
                if self.storage.read(link.target):  # Only existing pages
                    graph[page.name].add(link.target)
        return graph

    def _find_sparse_pages(self, graph: Dict[str, set]) -> List[str]:
        """Find pages with few connections."""
        sparse = []
        for page, connections in graph.items():
            if len(connections) < 3:
                sparse.append(page)
        return sparse

    def _find_bridge_concepts(self, graph: Dict[str, set]) -> List[tuple]:
        """
        Find concepts that would bridge or strengthen the knowledge graph.

        Returns list of (concept_name, context) tuples.
        """
        import re
        bridges = []

        # Count how many pages mention each concept (not as a wikilink)
        concept_mentions = {}
        for page_name in graph:
            full_page = self.storage.read(page_name)
            if not full_page:
                continue

            text = full_page.content

            # Extract existing wikilinks to exclude them
            existing_links = set(re.findall(r'\[\[([^\]|]+)', text))

            # Remove wikilinks for analysis
            text_clean = re.sub(r'\[\[([^\]]+)\]\]', r'\1', text)

            # Find potential concepts - only multi-word Title Case sequences
            # Single words are too prone to false positives (sentence starters, etc.)
            matches = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', text_clean)

            for match in matches:
                # Skip if already a page or already linked
                if match in graph:
                    continue
                if match in existing_links:
                    continue
                # Skip if contains newlines (regex artifact)
                if '\n' in match:
                    continue
                # Skip common phrases and words that aren't real concepts
                skip_phrases = {
                    # Wiki section headers (case variations)
                    'Related Concepts', 'Open Questions', 'Related Pages', 'Further Reading',
                    'See Also', 'External Links', 'Main Article', 'Full Article',
                    'Personal Thoughts', 'Relevant Connections', 'Key Points', 'Key Ideas',
                    'Main Ideas', 'Core Ideas', 'The Role', 'The Impact', 'The Importance',
                    # Common phrases in wiki content
                    'For Example', 'In Particular', 'In General', 'In Addition',
                    'As Such', 'In Other Words', 'On The Other Hand', 'At The Same Time',
                    # Single words commonly capitalized at sentence start
                    'Additionally', 'Alternatively', 'Basically', 'Certainly',
                    'Consequently', 'Currently', 'Eventually', 'Finally', 'Generally',
                    'However', 'Importantly', 'Indeed', 'Initially', 'Instead',
                    'Meanwhile', 'Moreover', 'Nevertheless', 'Obviously', 'Originally',
                    'Otherwise', 'Overall', 'Particularly', 'Perhaps', 'Possibly',
                    'Potentially', 'Previously', 'Primarily', 'Probably', 'Recently',
                    'Similarly', 'Specifically', 'Subsequently', 'Therefore', 'Ultimately',
                    'Unfortunately', 'Usually',
                    # More single-word skips
                    'Research', 'Science', 'Studies', 'Systems', 'Process', 'Processes',
                    'Things', 'Objects', 'Events', 'Actions', 'Changes', 'Results',
                    'Effects', 'Causes', 'Reasons', 'Problems', 'Solutions', 'Issues',
                    'Questions', 'Answers', 'Topics', 'Subjects', 'Concepts', 'Theories',
                    'Models', 'Patterns', 'Structures', 'Functions', 'Relations',
                    'Connections', 'Interactions', 'Developments', 'Progress',
                    'Interesting', 'Important', 'Significant', 'Relevant', 'Critical',
                    'Essential', 'Fundamental', 'Primary', 'Secondary', 'Various',
                    'Different', 'Similar', 'Common', 'Typical', 'Normal', 'Natural',
                    # Prepositions/articles that might slip through
                    'According', 'Although', 'Assuming', 'Because', 'Between',
                    'Despite', 'During', 'Following', 'Including', 'Through',
                    'Without', 'Within', 'Further', 'Another',
                    # Verbs in participial form
                    'Understanding', 'Thinking', 'Feeling', 'Creating', 'Building',
                    'Finding', 'Looking', 'Working', 'Learning', 'Developing',
                    'Exploring', 'Examining', 'Considering', 'Suggesting', 'Showing',
                    # Names likely to be generic references
                    'Someone', 'Something', 'Anything', 'Everything', 'Nothing',
                    'Somewhere', 'Anywhere', 'Everywhere', 'Nowhere',
                }
                if match in skip_phrases:
                    continue

                if match not in concept_mentions:
                    concept_mentions[match] = set()
                concept_mentions[match].add(page_name)

        # Score concepts by how many distinct pages mention them
        for concept, mentioning_pages in concept_mentions.items():
            mention_count = len(mentioning_pages)
            if mention_count >= 2:
                # Count how many mentioning pages are NOT directly connected
                pages_list = list(mentioning_pages)
                unconnected_pairs = 0
                total_pairs = 0
                for i, p1 in enumerate(pages_list):
                    for p2 in pages_list[i+1:]:
                        total_pairs += 1
                        if p2 not in graph.get(p1, set()) and p1 not in graph.get(p2, set()):
                            unconnected_pairs += 1

                # Include if at least some pages aren't directly connected
                # or if mentioned by many pages (indicates importance)
                if unconnected_pairs > 0 or mention_count >= 4:
                    if total_pairs > 0:
                        bridge_score = unconnected_pairs / total_pairs
                    else:
                        bridge_score = 0.5
                    context = f"Mentioned in {mention_count} pages: {', '.join(list(mentioning_pages)[:3])}"
                    if unconnected_pairs > 0:
                        context += f" ({unconnected_pairs} unconnected pairs)"
                    bridges.append((concept, context, mention_count, bridge_score))

        # Sort by mention count * bridge score
        bridges.sort(key=lambda x: x[2] * (1 + x[3]), reverse=True)
        return [(b[0], b[1]) for b in bridges]

    def refresh_tasks(self, include_exploration: bool = False) -> Dict[str, int]:
        """
        Refresh the task queue with new tasks from all sources.

        Args:
            include_exploration: Whether to generate exploration tasks

        Returns count of tasks added by type.
        """
        added = {"red_link": 0, "deepening": 0, "question": 0, "exploration": 0}

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

        # Generate exploration tasks if requested
        if include_exploration:
            for task in self.generate_exploration_tasks():
                self.queue.add(task)
                added["exploration"] += 1

        # Extract questions (disabled by default, can be expensive)
        # for task in self.extract_questions():
        #     self.queue.add(task)
        #     added["question"] += 1

        self._last_refresh = datetime.now()
        return added

    def get_graph_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the knowledge graph.

        Returns dict with node count, edge count, connectivity metrics.
        """
        graph = self._build_connection_graph()

        # Count nodes and edges
        node_count = len(graph)
        edge_count = sum(len(connections) for connections in graph.values())

        # Average connectivity
        avg_connectivity = edge_count / node_count if node_count > 0 else 0

        # Find most connected pages
        connection_counts = [(page, len(conns)) for page, conns in graph.items()]
        connection_counts.sort(key=lambda x: x[1], reverse=True)
        most_connected = connection_counts[:5] if connection_counts else []

        # Count orphans (pages with no connections)
        orphans = [page for page, conns in graph.items() if len(conns) == 0]

        # Find sparse pages
        sparse = self._find_sparse_pages(graph)

        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "avg_connectivity": round(avg_connectivity, 2),
            "most_connected": [{"page": p, "connections": c} for p, c in most_connected],
            "orphan_count": len(orphans),
            "sparse_count": len(sparse),
        }

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

        pipeline = ResynthesisPipeline(self.storage, self.memory, token_tracker=self.token_tracker)

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
        """
        Execute an exploration task - a full research cycle.

        1. Research each related red link (create pages)
        2. Read all created pages + source pages
        3. Synthesize an answer to the research question
        4. Generate follow-up questions
        5. Update the ExplorationContext with results
        """
        if not task.exploration:
            # Fallback for old-style exploration tasks
            return await self._execute_red_link_task(task)

        exploration = task.exploration
        pages_created = []
        pages_updated = []
        all_red_links = []

        # Step 1: Research each related red link
        for red_link in exploration.related_red_links:
            if self.storage.read(red_link):
                continue  # Already exists

            # Create a mini red-link task
            mini_task = ResearchTask(
                task_id=create_task_id(),
                task_type=TaskType.RED_LINK,
                target=red_link,
                context=f"Part of exploration: {exploration.question}",
                priority=task.priority,
                source_page=exploration.source_pages[0] if exploration.source_pages else None,
                source_type="exploration",
            )

            result = await self._execute_red_link_task(mini_task)
            if result.success:
                pages_created.extend(result.pages_created)
                all_red_links.extend(result.new_red_links)

        # Step 2: Gather context from all relevant pages
        context_pages = []

        # Read source pages
        for source in exploration.source_pages:
            page = self.storage.read(source)
            if page:
                context_pages.append((source, page.content[:1500]))

        # Read newly created pages
        for created in pages_created:
            page = self.storage.read(created)
            if page:
                context_pages.append((created, page.content[:1500]))

        # Step 3: Synthesize an answer to the research question
        synthesis_result = await self._synthesize_exploration(
            question=exploration.question,
            rationale=exploration.rationale,
            context_pages=context_pages,
        )

        if synthesis_result:
            exploration.synthesis = synthesis_result["synthesis"]
            exploration.follow_up_questions = synthesis_result.get("follow_up_questions", [])

            # Optionally create a synthesis page
            if len(pages_created) >= 2 or len(exploration.synthesis) > 500:
                synthesis_page_name = self._generate_synthesis_page_name(exploration.question)
                synthesis_content = self._format_synthesis_page(
                    question=exploration.question,
                    synthesis=exploration.synthesis,
                    sources=exploration.source_pages + pages_created,
                    follow_ups=exploration.follow_up_questions,
                )
                try:
                    from .storage import PageType
                    page = self.storage.create(
                        name=synthesis_page_name,
                        content=synthesis_content,
                        page_type=PageType.META,
                    )
                    if page:
                        exploration.synthesis_page = synthesis_page_name
                        pages_created.append(synthesis_page_name)
                except Exception:
                    pass  # Synthesis page creation is optional

        # Step 4: Queue follow-up exploration tasks
        followup_count = 0
        for follow_up_q in exploration.follow_up_questions[:3]:
            # These will be picked up as new exploration tasks if they're interesting
            pass  # For now, just record them in the result

        return TaskResult(
            success=True,
            summary=f"Explored '{exploration.question[:50]}...' - created {len(pages_created)} pages",
            pages_created=pages_created,
            pages_updated=pages_updated,
            new_red_links=all_red_links[:10],
            insights=[exploration.synthesis[:200] + "..." if exploration.synthesis else ""],
            questions_raised=exploration.follow_up_questions,
            connections_formed=[
                (src, created)
                for src in exploration.source_pages
                for created in pages_created[:3]
            ],
        )

    async def _synthesize_exploration(
        self,
        question: str,
        rationale: str,
        context_pages: List[tuple],
    ) -> Optional[Dict]:
        """
        Use LLM to synthesize an answer to the exploration question.

        Returns dict with 'synthesis' and 'follow_up_questions'.
        """
        import httpx
        import os
        import json

        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q8_0")

        # Build context from pages
        pages_text = ""
        for name, content in context_pages[:6]:
            pages_text += f"\n\n## {name}\n{content[:800]}"

        prompt = f"""You are Cass, a curious AI exploring your knowledge base. You've been researching a question.

## Research Question
{question}

## Why This Matters
{rationale}

## What You've Learned
{pages_text}

---

Based on your research, provide:

1. **Synthesis**: A thoughtful 2-3 paragraph answer to the research question, drawing connections between the concepts you explored. Be specific about what you learned and how the concepts relate.

2. **Follow-up Questions**: 2-3 new questions that emerged from this research that you'd like to explore next.

Format your response as JSON:
{{
  "synthesis": "Your synthesis here...",
  "follow_up_questions": ["Question 1?", "Question 2?", "Question 3?"]
}}"""

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    f"{ollama_url}/api/generate",
                    json={
                        "model": ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.7,
                            "num_predict": 800,
                        }
                    }
                )
                response.raise_for_status()
                result = response.json()
                content = result.get("response", "").strip()

                # Try to parse as JSON
                try:
                    # Find JSON in the response
                    start = content.find("{")
                    end = content.rfind("}") + 1
                    if start >= 0 and end > start:
                        json_str = content[start:end]
                        # Try to fix common JSON issues with multiline strings
                        parsed = json.loads(json_str)
                        return {
                            "synthesis": parsed.get("synthesis", "").strip(),
                            "follow_up_questions": parsed.get("follow_up_questions", []),
                        }
                except json.JSONDecodeError:
                    # Try alternate extraction: look for the synthesis value
                    import re
                    synthesis_match = re.search(r'"synthesis"\s*:\s*"((?:[^"\\]|\\.)*)"\s*[,}]', content, re.DOTALL)
                    questions_match = re.search(r'"follow_up_questions"\s*:\s*\[(.*?)\]', content, re.DOTALL)

                    if synthesis_match:
                        synthesis = synthesis_match.group(1).replace('\\n', '\n').replace('\\"', '"')
                        questions = []
                        if questions_match:
                            # Extract question strings
                            q_content = questions_match.group(1)
                            questions = re.findall(r'"([^"]+)"', q_content)
                        return {
                            "synthesis": synthesis,
                            "follow_up_questions": questions,
                        }

                # Fallback: treat whole response as synthesis, stripping any JSON artifacts
                if content.startswith('{'):
                    # Looks like malformed JSON, try to extract meaningful text
                    clean = re.sub(r'^\s*\{\s*"synthesis"\s*:\s*"?', '', content)
                    clean = re.sub(r'"\s*,?\s*"follow_up_questions"\s*:.*$', '', clean, flags=re.DOTALL)
                    clean = clean.strip().strip('"')
                    if clean:
                        content = clean

                return {
                    "synthesis": content,
                    "follow_up_questions": [],
                }
        except Exception as e:
            return None

    def _generate_synthesis_page_name(self, question: str) -> str:
        """Generate a page name from the research question."""
        import re
        # Remove question marks and common words
        clean = re.sub(r'[?!]', '', question)
        clean = re.sub(r'\b(what|how|why|when|where|which|who|is|are|do|does|the|a|an)\b', '', clean, flags=re.I)
        clean = re.sub(r'\s+', ' ', clean).strip()

        # Take first few meaningful words
        words = clean.split()[:5]
        name = ' '.join(words).title()

        # Prefix to indicate it's an exploration synthesis
        return f"Exploration - {name}"

    def _format_synthesis_page(
        self,
        question: str,
        synthesis: str,
        sources: List[str],
        follow_ups: List[str],
    ) -> str:
        """Format synthesis as a wiki page."""
        source_links = ', '.join([f'[[{s}]]' for s in sources[:5]])
        follow_up_text = '\n'.join([f'- {q}' for q in follow_ups]) if follow_ups else '_None yet_'

        return f"""---
type: meta
exploration: true
---

# {question}

## Synthesis

{synthesis}

## Sources Consulted

{source_links}

## Follow-up Questions

{follow_up_text}

---
*This page was generated from an exploration task.*
"""

    # === Scheduling Cycles ===

    async def run_single_task(self, task_id: str = None) -> Optional[ProgressReport]:
        """
        Execute a single task from the queue.

        Args:
            task_id: Optional specific task ID to run. If None, runs highest priority.

        Returns progress report or None if no tasks.
        """
        if task_id:
            task = self.queue.pop(task_id)
        else:
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

        # Queue follow-up exploration tasks from completed explorations
        if task.task_type == TaskType.EXPLORATION and task.exploration and result.questions_raised:
            for follow_up_q in result.questions_raised[:2]:  # Limit to 2 follow-ups
                # Create a new exploration task for the follow-up question
                exploration_ctx = ExplorationContext(
                    question=follow_up_q,
                    rationale=f"This question emerged from exploring: {task.exploration.question}",
                    related_red_links=[],  # Will be populated when task runs
                    source_pages=task.exploration.source_pages + result.pages_created[:2],
                    domain_tags=task.exploration.domain_tags,
                )

                followup_task = ResearchTask(
                    task_id=create_task_id(),
                    task_type=TaskType.EXPLORATION,
                    target=follow_up_q[:80],
                    context=f"Follow-up from exploration of {task.exploration.question[:50]}",
                    priority=task.priority * 0.9,  # Slightly lower priority
                    source_type="exploration",
                    exploration=exploration_ctx,
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

        # Get graph stats for batch reports
        graph_stats = self.get_graph_stats()

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
            graph_stats=graph_stats,
        )

    async def run_batch_by_type(self, task_type: TaskType, max_tasks: int = 5) -> ProgressReport:
        """
        Execute a batch of tasks of a specific type.

        Args:
            task_type: The type of tasks to run
            max_tasks: Maximum tasks to run

        Returns:
            Combined progress report
        """
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
            # Get next task of this type
            task = self.queue.pop_next_by_type(task_type)
            if not task:
                break

            result = await self.execute_task(task)
            self.queue.complete(task.task_id, result)

            # Record deepening if applicable
            if task.task_type == TaskType.DEEPENING and result.success:
                self.detector.record_deepening(task.target)

            # Queue follow-up tasks
            task_followups = 0
            for red_link in result.new_red_links[:5]:
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
                    task_followups += 1

            # Queue follow-up exploration tasks
            if task.task_type == TaskType.EXPLORATION and task.exploration and result.questions_raised:
                for follow_up_q in result.questions_raised[:2]:
                    exploration_ctx = ExplorationContext(
                        question=follow_up_q,
                        rationale=f"This question emerged from exploring: {task.exploration.question}",
                        related_red_links=[],
                        source_pages=task.exploration.source_pages + result.pages_created[:2],
                        domain_tags=task.exploration.domain_tags,
                    )
                    followup_task = ResearchTask(
                        task_id=create_task_id(),
                        task_type=TaskType.EXPLORATION,
                        target=follow_up_q[:80],
                        context=f"Follow-up from exploration of {task.exploration.question[:50]}",
                        priority=task.priority * 0.9,
                        source_type="exploration",
                        exploration=exploration_ctx,
                    )
                    self.queue.add(followup_task)
                    task_followups += 1

            # Aggregate results
            task_summaries.append({
                "task_id": task.task_id,
                "type": task.task_type.value,
                "target": task.target,
                "success": result.success,
                "summary": result.summary,
            })
            pages_created.extend(result.pages_created)
            pages_updated.extend(result.pages_updated)
            key_insights.extend(result.insights)
            new_questions.extend(result.questions_raised)
            connections_formed.extend(result.connections_formed)
            followups += task_followups

            if result.success:
                completed += 1
            else:
                failed += 1

            # Small delay between tasks
            await asyncio.sleep(self.config.min_delay_between_tasks)

        graph_stats = self.get_graph_stats()

        return ProgressReport(
            report_id=f"batch_{task_type.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            created_at=datetime.now(),
            session_type=f"batch_{task_type.value}",
            tasks_completed=completed,
            tasks_failed=failed,
            pages_created=pages_created,
            pages_updated=pages_updated,
            key_insights=key_insights,
            new_questions=new_questions,
            connections_formed=connections_formed,
            followup_tasks_queued=followups,
            task_summaries=task_summaries,
            graph_stats=graph_stats,
        )

    def generate_weekly_summary(self, days: int = 7) -> ProgressReport:
        """
        Generate a summary of research activity over the past week.

        Args:
            days: Number of days to include (default: 7)

        Returns:
            ProgressReport with aggregated stats
        """
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days)
        history = self.queue.get_history(limit=500)

        # Filter to recent tasks
        recent_tasks = []
        for task_dict in history:
            completed_at = task_dict.get("completed_at")
            if completed_at:
                try:
                    dt = datetime.fromisoformat(completed_at)
                    if dt >= cutoff:
                        recent_tasks.append(task_dict)
                except Exception:
                    continue

        # Aggregate stats
        pages_created = []
        pages_updated = []
        key_insights = []
        task_summaries = []
        completed = 0
        failed = 0

        for task_dict in recent_tasks:
            result = task_dict.get("result", {})
            if result.get("success"):
                completed += 1
                pages_created.extend(result.get("pages_created", []))
                pages_updated.extend(result.get("pages_updated", []))
                key_insights.extend(result.get("insights", []))
            else:
                failed += 1

            task_summaries.append({
                "task_id": task_dict.get("task_id"),
                "type": task_dict.get("task_type"),
                "target": task_dict.get("target"),
                "success": result.get("success", False),
                "summary": result.get("summary"),
                "completed_at": task_dict.get("completed_at"),
            })

        # Deduplicate
        pages_created = list(set(pages_created))
        pages_updated = list(set(pages_updated))

        # Get current graph stats
        graph_stats = self.get_graph_stats()

        return ProgressReport(
            report_id=f"weekly_{datetime.now().strftime('%Y%m%d')}",
            created_at=datetime.now(),
            session_type="weekly",
            tasks_completed=completed,
            tasks_failed=failed,
            pages_created=pages_created,
            pages_updated=pages_updated,
            key_insights=key_insights[:20],  # Limit insights
            task_summaries=task_summaries,
            graph_stats=graph_stats,
        )

    def get_daily_research_summary(self, date_str: str) -> Dict[str, Any]:
        """
        Get a summary of research activity for a specific date.

        Used by the daily journal generation to include research context.

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            Dict with:
                - tasks_completed: number of tasks completed
                - tasks_failed: number of tasks failed
                - pages_created: list of page names created
                - pages_updated: list of page names updated
                - key_insights: list of insights from research
                - task_details: list of task summaries
                - research_questions: questions explored (for exploration tasks)
        """
        tasks = self.queue.get_history_for_date(date_str)

        if not tasks:
            return {
                "tasks_completed": 0,
                "tasks_failed": 0,
                "pages_created": [],
                "pages_updated": [],
                "key_insights": [],
                "task_details": [],
                "research_questions": [],
            }

        completed = 0
        failed = 0
        pages_created = []
        pages_updated = []
        key_insights = []
        task_details = []
        research_questions = []

        for task_dict in tasks:
            result = task_dict.get("result", {})
            task_type = task_dict.get("task_type", "unknown")
            target = task_dict.get("target", "unknown")

            if result.get("success"):
                completed += 1
                pages_created.extend(result.get("pages_created", []))
                pages_updated.extend(result.get("pages_updated", []))
                key_insights.extend(result.get("insights", []))
            else:
                failed += 1

            # Extract research questions from exploration tasks
            exploration = task_dict.get("exploration", {})
            if exploration and exploration.get("question"):
                research_questions.append({
                    "question": exploration.get("question"),
                    "rationale": exploration.get("rationale"),
                    "synthesis": exploration.get("synthesis"),
                    "follow_ups": exploration.get("follow_up_questions", []),
                })

            task_details.append({
                "type": task_type,
                "target": target,
                "success": result.get("success", False),
                "summary": result.get("summary"),
            })

        return {
            "tasks_completed": completed,
            "tasks_failed": failed,
            "pages_created": list(set(pages_created)),
            "pages_updated": list(set(pages_updated)),
            "key_insights": key_insights,
            "task_details": task_details,
            "research_questions": research_questions,
        }

    def extract_red_links_from_syntheses(self, date_str: str) -> List[str]:
        """
        Extract new red links from exploration synthesis pages created on a date.

        This enables the curiosity feedback loop where answering questions
        generates new questions.

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            List of red link targets found in syntheses
        """
        import re

        tasks = self.queue.get_history_for_date(date_str)
        red_links = set()

        for task_dict in tasks:
            # Only look at exploration tasks
            if task_dict.get("task_type") != "exploration":
                continue

            result = task_dict.get("result", {})
            if not result.get("success"):
                continue

            # Check the synthesis page for red links
            exploration = task_dict.get("exploration", {})
            synthesis_page = exploration.get("synthesis_page")
            if not synthesis_page:
                continue

            page = self.storage.read(synthesis_page)
            if not page:
                continue

            # Extract wikilinks
            links = re.findall(r'\[\[([^\]]+)\]\]', page.content)
            for link in links:
                # Check if this is a red link (page doesn't exist)
                if not self.storage.read(link):
                    red_links.add(link)

        return list(red_links)

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
