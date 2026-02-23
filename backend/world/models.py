"""
World State Consumption Data Models

Data structures for article consumption and insight extraction.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any


class ProcessingStatus(str, Enum):
    """Status of article processing pipeline."""
    PENDING = "pending"
    FETCHING = "fetching"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ExtractedObservation:
    """An observation about the world extracted from article content."""
    text: str
    confidence: float = 0.7
    category: str = "world_awareness"  # news, trend, pattern, concern, hope


@dataclass
class ExtractedQuestion:
    """A question sparked by article content."""
    question: str
    question_type: str = "curiosity"  # curiosity, philosophical, decision
    importance: float = 0.5
    context: str = ""


@dataclass
class ExtractedOpinion:
    """Cass's perspective on article content."""
    topic: str
    position: str
    confidence: float = 0.6
    reasoning: str = ""


@dataclass
class ExtractedGrowthEdge:
    """A growth opportunity suggested by article content."""
    area: str
    current_state: str = ""
    desired_state: str = ""
    importance: float = 0.5


@dataclass
class ExtractedAuthorObservation:
    """An observation about the article's author."""
    observation_type: str  # writing_style, expertise, perspective, bias, credibility
    content: str
    confidence: float = 0.7


@dataclass
class ExtractedAuthorFact:
    """A biographical fact about the article's author."""
    fact_type: str  # affiliation, expertise_area, publication_history, background
    content: str
    confidence: float = 0.8


@dataclass
class ExtractedInterest:
    """An interest sparked or reinforced by article content."""
    name: str  # Short topic name
    fascination: str  # What draws interest about this topic
    category: str = "general"  # science, philosophy, art, technology, nature, psychology, society


@dataclass
class ExtractedSymbol:
    """A symbolic image or motif noticed in article content."""
    name: str  # The symbol name
    meaning: str  # What it represents
    emotional_charge: str = "ambivalent"  # positive, negative, ambivalent, transformative


@dataclass
class ArticleInsights:
    """Insights extracted from an article by the content analyzer."""
    summary: str
    observations: List[ExtractedObservation] = field(default_factory=list)
    questions: List[ExtractedQuestion] = field(default_factory=list)
    opinions: List[ExtractedOpinion] = field(default_factory=list)
    growth_edges: List[ExtractedGrowthEdge] = field(default_factory=list)

    # Author-related extractions
    author_observations: List["ExtractedAuthorObservation"] = field(default_factory=list)
    author_facts: List["ExtractedAuthorFact"] = field(default_factory=list)

    # Personal meaning extractions
    interests: List["ExtractedInterest"] = field(default_factory=list)
    symbols: List["ExtractedSymbol"] = field(default_factory=list)

    # Processing metadata
    tokens_used: int = 0
    processing_time_ms: int = 0


@dataclass
class Article:
    """A consumed article with metadata and extracted insights."""
    id: str
    daemon_id: str
    url: str
    headline: str

    # Source metadata
    source: Optional[str] = None
    category: Optional[str] = None
    published_at: Optional[str] = None

    # Author tracking
    author_name: Optional[str] = None
    author_handle: Optional[str] = None  # email, twitter handle, etc.
    author_handle_type: Optional[str] = None  # "email", "twitter", "linkedin", "website"
    author_entity_id: Optional[str] = None  # Link to PeopleDex entity

    # Content
    full_content: Optional[str] = None
    summary: Optional[str] = None

    # Processing state
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    error_message: Optional[str] = None
    consumed_at: Optional[str] = None
    processing_time_ms: Optional[int] = None
    tokens_used: Optional[int] = None

    # Extracted insights (stored as JSON in DB)
    observations: List[ExtractedObservation] = field(default_factory=list)
    questions: List[ExtractedQuestion] = field(default_factory=list)
    opinions: List[ExtractedOpinion] = field(default_factory=list)
    growth_edges: List[ExtractedGrowthEdge] = field(default_factory=list)

    # Links to created self-model items
    observation_ids: List[str] = field(default_factory=list)
    question_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "daemon_id": self.daemon_id,
            "url": self.url,
            "headline": self.headline,
            "source": self.source,
            "category": self.category,
            "published_at": self.published_at,
            "author_name": self.author_name,
            "author_handle": self.author_handle,
            "author_handle_type": self.author_handle_type,
            "author_entity_id": self.author_entity_id,
            "full_content": self.full_content,
            "summary": self.summary,
            "processing_status": self.processing_status.value,
            "error_message": self.error_message,
            "consumed_at": self.consumed_at,
            "processing_time_ms": self.processing_time_ms,
            "tokens_used": self.tokens_used,
            "observations": [
                {"text": o.text, "confidence": o.confidence, "category": o.category}
                for o in self.observations
            ],
            "questions": [
                {
                    "question": q.question,
                    "question_type": q.question_type,
                    "importance": q.importance,
                    "context": q.context,
                }
                for q in self.questions
            ],
            "opinions": [
                {
                    "topic": o.topic,
                    "position": o.position,
                    "confidence": o.confidence,
                    "reasoning": o.reasoning,
                }
                for o in self.opinions
            ],
            "growth_edges": [
                {
                    "area": g.area,
                    "current_state": g.current_state,
                    "desired_state": g.desired_state,
                    "importance": g.importance,
                }
                for g in self.growth_edges
            ],
            "observation_ids": self.observation_ids,
            "question_ids": self.question_ids,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Article":
        """Create Article from database dictionary."""
        return cls(
            id=data["id"],
            daemon_id=data["daemon_id"],
            url=data["url"],
            headline=data["headline"],
            source=data.get("source"),
            category=data.get("category"),
            published_at=data.get("published_at"),
            author_name=data.get("author_name"),
            author_handle=data.get("author_handle"),
            author_handle_type=data.get("author_handle_type"),
            author_entity_id=data.get("author_entity_id"),
            full_content=data.get("full_content"),
            summary=data.get("summary"),
            processing_status=ProcessingStatus(data.get("processing_status", "pending")),
            error_message=data.get("error_message"),
            consumed_at=data.get("consumed_at"),
            processing_time_ms=data.get("processing_time_ms"),
            tokens_used=data.get("tokens_used"),
            observations=[
                ExtractedObservation(**o)
                for o in (data.get("observations") or [])
            ],
            questions=[
                ExtractedQuestion(**q)
                for q in (data.get("questions") or [])
            ],
            opinions=[
                ExtractedOpinion(**o)
                for o in (data.get("opinions") or [])
            ],
            growth_edges=[
                ExtractedGrowthEdge(**g)
                for g in (data.get("growth_edges") or [])
            ],
            observation_ids=data.get("observation_ids") or [],
            question_ids=data.get("question_ids") or [],
        )
