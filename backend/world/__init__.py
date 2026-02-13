"""
World State Consumption Module

Enables Cass to consume and process external world information:
- Article fetching from news URLs
- Content analysis and insight extraction
- Integration with self-model (observations, questions, opinions)

Reading modes (configurable for A/B testing):
- progressive: Paragraph-by-paragraph with revision capability
- single_pass: Whole article at once (simpler baseline)
"""

from .models import (
    Article,
    ArticleInsights,
    ExtractedObservation,
    ExtractedQuestion,
    ExtractedOpinion,
    ExtractedGrowthEdge,
    ProcessingStatus,
)
from .article_consumer import ArticleConsumer
from .content_analyzer import (
    ContentAnalyzer,
    ReadingMode,
    analyze_article,
)
from .integrator import (
    InsightIntegrator,
    IntegrationResult,
    integrate_article_insights,
)
from .pipeline import (
    ConsumptionConfig,
    PipelineResult,
    run_consumption_pipeline,
    run_consumption_pipeline_async,
    get_daily_budget,
)
from .memory_integration import (
    ArticleMemoryManager,
    search_consumed_articles,
    get_article_details,
    list_article_sources,
    get_article_stats,
)

__all__ = [
    # Models
    "Article",
    "ArticleInsights",
    "ExtractedObservation",
    "ExtractedQuestion",
    "ExtractedOpinion",
    "ExtractedGrowthEdge",
    "ProcessingStatus",
    # Consumer
    "ArticleConsumer",
    # Analyzer
    "ContentAnalyzer",
    "ReadingMode",
    "analyze_article",
    # Integrator
    "InsightIntegrator",
    "IntegrationResult",
    "integrate_article_insights",
    # Pipeline
    "ConsumptionConfig",
    "PipelineResult",
    "run_consumption_pipeline",
    "run_consumption_pipeline_async",
    "get_daily_budget",
    # Memory Integration
    "ArticleMemoryManager",
    "search_consumed_articles",
    "get_article_details",
    "list_article_sources",
    "get_article_stats",
]
