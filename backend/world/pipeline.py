"""
World State Consumption Pipeline - Full end-to-end processing.

Orchestrates: fetch headlines -> consume articles -> analyze -> integrate
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from database import get_db, json_serialize

from .models import Article, ArticleInsights, ProcessingStatus
from .article_consumer import ArticleConsumer
from .content_analyzer import ContentAnalyzer, ReadingMode
from .integrator import InsightIntegrator, IntegrationResult

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class ConsumptionConfig:
    """Configuration for world state consumption."""
    # Reading mode - toggle for A/B testing
    reading_mode: ReadingMode = ReadingMode.SINGLE_PASS

    # Budget controls
    max_articles_per_cycle: int = 5
    max_articles_per_day: int = 10
    max_tokens_per_day: int = 50000

    # Quality thresholds
    min_confidence: float = 0.5
    min_importance_for_growth_edge: float = 0.6

    # Model selection
    analysis_model: str = "claude-haiku-4-5-20251001"

    # Progressive reading settings
    max_paragraphs_per_turn: int = 2

    @classmethod
    def from_env(cls) -> "ConsumptionConfig":
        """Load config from environment variables."""
        return cls(
            reading_mode=ReadingMode(
                os.getenv("WORLD_CONSUMPTION_READING_MODE", "progressive")
            ),
            max_articles_per_cycle=int(
                os.getenv("WORLD_CONSUMPTION_ARTICLES_PER_CYCLE", "5")
            ),
            max_articles_per_day=int(
                os.getenv("WORLD_CONSUMPTION_ARTICLES_PER_DAY", "10")
            ),
            max_tokens_per_day=int(
                os.getenv("WORLD_CONSUMPTION_TOKENS_PER_DAY", "50000")
            ),
            min_confidence=float(
                os.getenv("WORLD_CONSUMPTION_MIN_CONFIDENCE", "0.5")
            ),
            analysis_model=os.getenv(
                "WORLD_CONSUMPTION_MODEL", "claude-haiku-4-5-20251001"
            ),
        )


# =============================================================================
# BUDGET TRACKING
# =============================================================================

@dataclass
class DailyBudget:
    """Track daily consumption budget."""
    date: str
    articles_consumed: int = 0
    tokens_used: int = 0

    def can_consume(self, config: ConsumptionConfig) -> bool:
        """Check if budget allows more consumption today."""
        return (
            self.articles_consumed < config.max_articles_per_day and
            self.tokens_used < config.max_tokens_per_day
        )

    def remaining_articles(self, config: ConsumptionConfig) -> int:
        """How many more articles can be consumed today."""
        return max(0, config.max_articles_per_day - self.articles_consumed)


def get_daily_budget(daemon_id: str) -> DailyBudget:
    """Get today's consumption budget status."""
    today = datetime.now().strftime("%Y-%m-%d")

    with get_db() as conn:
        cursor = conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(tokens_used), 0)
            FROM consumed_articles
            WHERE daemon_id = ?
            AND DATE(consumed_at) = ?
            AND processing_status = 'completed'
            """,
            (daemon_id, today)
        )
        row = cursor.fetchone()

    return DailyBudget(
        date=today,
        articles_consumed=row[0] if row else 0,
        tokens_used=row[1] if row else 0,
    )


# =============================================================================
# PIPELINE
# =============================================================================

@dataclass
class PipelineResult:
    """Result of a consumption pipeline run."""
    articles_fetched: int = 0
    articles_analyzed: int = 0
    articles_failed: int = 0
    total_tokens_used: int = 0
    insights_integrated: int = 0
    details: List[Dict] = field(default_factory=list)


def run_consumption_pipeline(
    daemon_id: str,
    headlines: List[Dict],
    self_manager=None,
    memory_core=None,
    config: Optional[ConsumptionConfig] = None,
) -> PipelineResult:
    """
    Run the full consumption pipeline on a batch of headlines.

    Args:
        daemon_id: Daemon ID
        headlines: List of headline dicts from WorldStateSource
        self_manager: Optional SelfManager for context and integration
        memory_core: Optional MemoryCore for ChromaDB article storage
        config: Consumption configuration (defaults from env)

    Returns:
        PipelineResult with stats and details
    """
    if config is None:
        config = ConsumptionConfig.from_env()

    result = PipelineResult()

    # Check budget
    budget = get_daily_budget(daemon_id)
    if not budget.can_consume(config):
        logger.info(f"Daily budget exhausted: {budget.articles_consumed} articles, {budget.tokens_used} tokens")
        return result

    remaining = min(
        config.max_articles_per_cycle,
        budget.remaining_articles(config)
    )

    if remaining <= 0:
        return result

    # Initialize components
    consumer = ArticleConsumer(daemon_id)
    analyzer = ContentAnalyzer(
        daemon_id=daemon_id,
        reading_mode=config.reading_mode,
        model=config.analysis_model,
        max_paragraphs_per_turn=config.max_paragraphs_per_turn,
    )
    integrator = InsightIntegrator(daemon_id, config.min_confidence, memory_core)

    # Consume headlines
    articles = consumer.consume_headlines(headlines, max_articles=remaining)
    result.articles_fetched = len(articles)

    # Analyze and integrate each article
    for article in articles:
        if article.processing_status == ProcessingStatus.FAILED:
            result.articles_failed += 1
            continue

        if not article.full_content:
            result.articles_failed += 1
            continue

        try:
            # Update status
            article.processing_status = ProcessingStatus.ANALYZING
            consumer._save_article(article)

            # Analyze
            insights = analyzer.analyze(article, self_manager)

            # Update article with results
            article.summary = insights.summary
            article.observations = insights.observations
            article.questions = insights.questions
            article.opinions = insights.opinions
            article.growth_edges = insights.growth_edges
            article.tokens_used = insights.tokens_used
            article.processing_time_ms = insights.processing_time_ms

            # Integrate into self-model
            integration = integrator.integrate(article, insights, self_manager)

            # Track created IDs
            article.observation_ids = integration.observations_added
            article.question_ids = integration.questions_added
            article.processing_status = ProcessingStatus.COMPLETED

            consumer._save_article(article)

            result.articles_analyzed += 1
            result.total_tokens_used += insights.tokens_used
            result.insights_integrated += integration.total_items_added

            result.details.append({
                "article_id": article.id,
                "headline": article.headline[:80],
                "status": "completed",
                "observations": len(insights.observations),
                "questions": len(insights.questions),
                "opinions": len(insights.opinions),
                "growth_edges": len(insights.growth_edges),
                "tokens": insights.tokens_used,
                "reading_mode": config.reading_mode.value,
            })

            logger.info(
                f"Processed article '{article.headline[:50]}...': "
                f"{len(insights.observations)} obs, {len(insights.questions)} questions"
            )

        except Exception as e:
            logger.error(f"Pipeline failed for article {article.id}: {e}")
            article.processing_status = ProcessingStatus.FAILED
            article.error_message = str(e)
            consumer._save_article(article)
            result.articles_failed += 1
            result.details.append({
                "article_id": article.id,
                "headline": article.headline[:80],
                "status": "failed",
                "error": str(e),
            })

    logger.info(
        f"Pipeline complete: {result.articles_analyzed}/{result.articles_fetched} analyzed, "
        f"{result.insights_integrated} insights integrated, {result.total_tokens_used} tokens"
    )

    return result


async def run_consumption_pipeline_async(
    daemon_id: str,
    headlines: List[Dict],
    self_manager=None,
    memory_core=None,
    config: Optional[ConsumptionConfig] = None,
) -> PipelineResult:
    """
    Async wrapper for consumption pipeline.

    Note: The actual LLM calls are synchronous (Anthropic client),
    but this allows the scheduler to await the pipeline.
    """
    import asyncio
    return await asyncio.to_thread(
        run_consumption_pipeline,
        daemon_id,
        headlines,
        self_manager,
        memory_core,
        config,
    )
