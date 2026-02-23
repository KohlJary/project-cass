"""
Insight Integrator - Stores extracted insights in Cass's self-model.

Takes ArticleInsights from content analysis and integrates them:
- Summary -> ChromaDB for recent ambient recall
- Observations -> self_observations table (category: world_awareness)
- Questions -> open_questions table
- Opinions -> opinions table
- Growth edges -> growth_edges table (if significant)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from database import get_db, json_serialize

from .models import Article, ArticleInsights
from .memory_integration import ArticleMemoryManager

logger = logging.getLogger(__name__)


@dataclass
class IntegrationResult:
    """Result of integrating article insights into self-model."""
    article_id: str
    observations_added: List[str] = field(default_factory=list)
    questions_added: List[str] = field(default_factory=list)
    opinions_added: int = 0
    growth_edges_added: int = 0
    author_observations_added: int = 0
    author_facts_added: int = 0
    interests_added: int = 0
    symbols_added: int = 0
    memory_id: Optional[str] = None  # ChromaDB entry ID for summary

    @property
    def total_items_added(self) -> int:
        return (
            len(self.observations_added) +
            len(self.questions_added) +
            self.opinions_added +
            self.growth_edges_added +
            self.author_observations_added +
            self.author_facts_added +
            self.interests_added +
            self.symbols_added
        )


class InsightIntegrator:
    """
    Integrates article insights into Cass's self-model.
    """

    def __init__(self, daemon_id: str, min_confidence: float = 0.5, memory_core=None):
        self.daemon_id = daemon_id
        self.min_confidence = min_confidence
        self.memory_manager = ArticleMemoryManager(daemon_id, memory_core) if memory_core else None

    def integrate(
        self,
        article: Article,
        insights: ArticleInsights,
        self_manager=None,
    ) -> IntegrationResult:
        """
        Integrate insights from article analysis into self-model.

        Args:
            article: The source article
            insights: Extracted insights from analysis
            self_manager: Optional SelfManager for growth edge integration

        Returns:
            IntegrationResult with IDs of created items
        """
        result = IntegrationResult(article_id=article.id)
        now = datetime.now().isoformat()

        # 0. Store summary in ChromaDB for ambient retrieval
        if self.memory_manager and insights.summary:
            memory_id = self.memory_manager.store_article_memory(
                article_id=article.id,
                headline=article.headline,
                source=article.source or "Unknown",
                summary=insights.summary,
                url=article.url,
                category=article.category,
                consumed_at=article.consumed_at or now,
            )
            result.memory_id = memory_id

        # 1. Store observations
        for obs in insights.observations:
            if obs.confidence >= self.min_confidence:
                obs_id = self._add_observation(
                    text=obs.text,
                    confidence=obs.confidence,
                    category=f"world_awareness:{obs.category}",
                    source_article_id=article.id,
                    source_url=article.url,
                    created_at=now,
                )
                if obs_id:
                    result.observations_added.append(obs_id)

        # 2. Store questions
        for q in insights.questions:
            if q.importance >= self.min_confidence:
                q_id = self._add_question(
                    question=q.question,
                    question_type=q.question_type,
                    importance=q.importance,
                    context=f"From article: {article.headline}\n\n{q.context}",
                    source_article_id=article.id,
                    created_at=now,
                )
                if q_id:
                    result.questions_added.append(q_id)

        # 3. Store opinions
        for op in insights.opinions:
            if op.confidence >= self.min_confidence:
                success = self._add_opinion(
                    topic=op.topic,
                    position=op.position,
                    confidence=op.confidence,
                    rationale=op.reasoning,
                    source_article_id=article.id,
                    created_at=now,
                )
                if success:
                    result.opinions_added += 1

        # 4. Optionally add growth edges (only if significant)
        for ge in insights.growth_edges:
            if ge.importance >= 0.6:  # Higher threshold for growth edges
                success = self._add_growth_edge(
                    area=ge.area,
                    current_state=ge.current_state,
                    desired_state=ge.desired_state,
                    importance=ge.importance,
                    source_article_id=article.id,
                    self_manager=self_manager,
                )
                if success:
                    result.growth_edges_added += 1

        # 5. Store author observations and facts in PeopleDex
        if article.author_entity_id:
            # Author observations
            for ao in insights.author_observations:
                if ao.confidence >= self.min_confidence:
                    success = self._add_author_observation(
                        entity_id=article.author_entity_id,
                        observation_type=ao.observation_type,
                        content=ao.content,
                        confidence=ao.confidence,
                        source_article_id=article.id,
                    )
                    if success:
                        result.author_observations_added += 1

            # Author facts
            for af in insights.author_facts:
                if af.confidence >= self.min_confidence:
                    success = self._add_author_fact(
                        entity_id=article.author_entity_id,
                        fact_type=af.fact_type,
                        content=af.content,
                        confidence=af.confidence,
                        source_article_id=article.id,
                    )
                    if success:
                        result.author_facts_added += 1

        # 6. Store interests
        for interest in insights.interests:
            success = self._add_interest(
                name=interest.name,
                fascination=interest.fascination,
                category=interest.category,
                source_article_id=article.id,
            )
            if success:
                result.interests_added += 1

        # 7. Store symbols
        for symbol in insights.symbols:
            success = self._add_symbol(
                name=symbol.name,
                meaning=symbol.meaning,
                emotional_charge=symbol.emotional_charge,
                source_article_id=article.id,
            )
            if success:
                result.symbols_added += 1

        logger.info(
            f"Integrated {result.total_items_added} items from article {article.id}: "
            f"{len(result.observations_added)} obs, {len(result.questions_added)} questions, "
            f"{result.opinions_added} opinions, {result.growth_edges_added} edges, "
            f"{result.author_observations_added} author obs, {result.author_facts_added} author facts, "
            f"{result.interests_added} interests, {result.symbols_added} symbols"
        )

        return result

    def _add_observation(
        self,
        text: str,
        confidence: float,
        category: str,
        source_article_id: str,
        source_url: str,
        created_at: str,
    ) -> Optional[str]:
        """Add observation to self_observations table."""
        obs_id = f"obs-{uuid4().hex[:12]}"

        try:
            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO self_observations (
                        id, daemon_id, category, observation, confidence,
                        context_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        obs_id,
                        self.daemon_id,
                        category,
                        text,
                        confidence,
                        json_serialize({
                            "source": "article",
                            "article_id": source_article_id,
                            "url": source_url,
                        }),
                        created_at,
                    )
                )
                conn.commit()
            return obs_id
        except Exception as e:
            logger.error(f"Failed to add observation: {e}")
            return None

    def _add_question(
        self,
        question: str,
        question_type: str,
        importance: float,
        context: str,
        source_article_id: str,
        created_at: str,
    ) -> Optional[str]:
        """Add question to open_questions table."""
        q_id = f"q-{uuid4().hex[:12]}"

        try:
            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO open_questions (
                        id, daemon_id, question, context, question_type,
                        importance, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?)
                    """,
                    (
                        q_id,
                        self.daemon_id,
                        question,
                        f"{context}\n\n[Source: article {source_article_id}]",
                        question_type,
                        importance,
                        created_at,
                    )
                )
                conn.commit()
            return q_id
        except Exception as e:
            logger.error(f"Failed to add question: {e}")
            return None

    def _add_opinion(
        self,
        topic: str,
        position: str,
        confidence: float,
        rationale: str,
        source_article_id: str,
        created_at: str,
    ) -> bool:
        """Add opinion to opinions table."""
        try:
            with get_db() as conn:
                # Check if we already have an opinion on this topic
                cursor = conn.execute(
                    "SELECT id FROM opinions WHERE daemon_id = ? AND topic = ?",
                    (self.daemon_id, topic)
                )
                existing = cursor.fetchone()

                if existing:
                    # Update existing opinion with evolution tracking
                    conn.execute(
                        """
                        UPDATE opinions SET
                            position = ?,
                            confidence = ?,
                            rationale = ?,
                            evolution_json = json_insert(
                                COALESCE(evolution_json, '[]'),
                                '$[#]',
                                json_object(
                                    'date', ?,
                                    'change', 'refined from article',
                                    'source_article', ?
                                )
                            ),
                            last_updated = ?
                        WHERE id = ?
                        """,
                        (
                            position,
                            confidence,
                            rationale,
                            created_at,
                            source_article_id,
                            created_at,
                            existing[0],
                        )
                    )
                else:
                    # Create new opinion
                    conn.execute(
                        """
                        INSERT INTO opinions (
                            daemon_id, topic, position, confidence, rationale,
                            formed_from, date_formed, last_updated
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            self.daemon_id,
                            topic,
                            position,
                            confidence,
                            rationale,
                            f"article:{source_article_id}",
                            created_at,
                            created_at,
                        )
                    )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add opinion: {e}")
            return False

    def _add_growth_edge(
        self,
        area: str,
        current_state: str,
        desired_state: str,
        importance: float,
        source_article_id: str,
        self_manager=None,
    ) -> bool:
        """
        Add growth edge, preferring SelfManager if available.
        """
        if self_manager:
            try:
                self_manager.add_or_update_growth_edge(
                    area=area,
                    current_state=current_state,
                    desired_state=desired_state,
                    importance=importance,
                    observation=f"Sparked by article {source_article_id}",
                    category="world_engagement",
                )
                return True
            except Exception as e:
                logger.warning(f"SelfManager growth edge failed, falling back: {e}")

        # Fallback to direct DB insert
        try:
            edge_id = f"edge-{uuid4().hex[:12]}"
            now = datetime.now().isoformat()

            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO growth_edges (
                        daemon_id, edge_id, area, current_state, desired_state,
                        importance, first_noticed, last_updated, observations_json,
                        category
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.daemon_id,
                        edge_id,
                        area,
                        current_state,
                        desired_state,
                        importance,
                        now,
                        now,
                        json_serialize([f"Sparked by article {source_article_id}"]),
                        "world_engagement",
                    )
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add growth edge: {e}")
            return False

    def _add_author_observation(
        self,
        entity_id: str,
        observation_type: str,
        content: str,
        confidence: float,
        source_article_id: str,
    ) -> bool:
        """Add observation about an author to PeopleDex."""
        try:
            from peopledex import PeopleDexManager
            pdx = PeopleDexManager(daemon_id=self.daemon_id)

            # Use PeopleDex observation API
            obs = pdx.add_observation(
                entity_id=entity_id,
                observation_type=observation_type,  # writing_style, expertise, etc.
                content=content,
                confidence=confidence,
                source_type="article_consumption",
                metadata={"source_article_id": source_article_id},
            )
            return obs is not None
        except Exception as e:
            logger.error(f"Failed to add author observation: {e}")
            return False

    def _add_author_fact(
        self,
        entity_id: str,
        fact_type: str,
        content: str,
        confidence: float,
        source_article_id: str,
    ) -> bool:
        """Add biographical fact about an author to PeopleDex."""
        try:
            from peopledex import PeopleDexManager
            pdx = PeopleDexManager(daemon_id=self.daemon_id)

            # Use PeopleDex fact API
            fact = pdx.add_fact(
                entity_id=entity_id,
                fact_type=fact_type,  # affiliation, expertise_area, etc.
                content=content,
                confidence=confidence,
                source_type="article_consumption",
                metadata={"source_article_id": source_article_id},
            )
            return fact is not None
        except Exception as e:
            logger.error(f"Failed to add author fact: {e}")
            return False

    def _add_interest(
        self,
        name: str,
        fascination: str,
        category: str,
        source_article_id: str,
    ) -> bool:
        """Add or reinforce an interest from article consumption."""
        try:
            from interests import get_interest_manager

            manager = get_interest_manager(self.daemon_id)

            # Check if interest already exists
            existing = manager.get_by_name(name)
            if existing:
                # Record engagement with existing interest
                manager.record_engagement(
                    interest_id=existing.id,
                    source_type="article",
                    source_id=source_article_id,
                    context=f"Article reinforced fascination: {fascination[:100]}"
                )
            else:
                # Create new interest
                manager.add_interest(
                    name=name,
                    fascination=fascination,
                    category=category,
                    intensity="curious",  # Start at curious level
                    source_type="article",
                    description=fascination
                )
            return True
        except Exception as e:
            logger.error(f"Failed to add interest: {e}")
            return False

    def _add_symbol(
        self,
        name: str,
        meaning: str,
        emotional_charge: str,
        source_article_id: str,
    ) -> bool:
        """Add or record appearance of a symbol from article consumption."""
        try:
            from symbols import get_symbol_manager

            manager = get_symbol_manager(self.daemon_id)

            # Check if symbol already exists
            existing = manager.get_by_name(name)
            if existing:
                # Record another appearance
                manager.record_appearance(
                    symbol_id=existing.id,
                    source_type="article",
                    source_id=source_article_id,
                    context=f"Encountered in article",
                    meaning_in_context=meaning
                )
            else:
                # Create new symbol
                manager.add_symbol(
                    name=name,
                    meaning=meaning,
                    source_type="article",
                    source_id=source_article_id,
                    emotional_charge=emotional_charge,
                    description=f"First noticed in article {source_article_id}"
                )
            return True
        except Exception as e:
            logger.error(f"Failed to add symbol: {e}")
            return False


def integrate_article_insights(
    article: Article,
    insights: ArticleInsights,
    daemon_id: str,
    self_manager=None,
    memory_core=None,
    min_confidence: float = 0.5,
) -> IntegrationResult:
    """
    Convenience function to integrate article insights.

    Args:
        article: Source article
        insights: Extracted insights
        daemon_id: Daemon ID
        self_manager: Optional SelfManager
        memory_core: Optional MemoryCore for ChromaDB storage
        min_confidence: Minimum confidence threshold

    Returns:
        IntegrationResult
    """
    integrator = InsightIntegrator(daemon_id, min_confidence, memory_core)
    return integrator.integrate(article, insights, self_manager)
