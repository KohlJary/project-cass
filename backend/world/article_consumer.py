"""
Article Consumer - Fetches and stores full article content from URLs.

Uses trafilatura for robust article extraction, with fallback to
headline + description when full content unavailable.
"""

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from database import get_db, json_serialize, json_deserialize
from .models import (
    Article,
    ProcessingStatus,
    ExtractedObservation,
    ExtractedQuestion,
    ExtractedOpinion,
    ExtractedGrowthEdge,
)

logger = logging.getLogger(__name__)


@dataclass
class AuthorInfo:
    """Extracted author information from article metadata."""
    name: Optional[str] = None
    handle: Optional[str] = None
    handle_type: Optional[str] = None  # email, twitter, linkedin, website

# Article extraction - try trafilatura first, fallback to basic requests
try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False
    logger.warning("trafilatura not installed - article extraction will be limited")

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False
    import urllib.request


class ArticleConsumer:
    """
    Fetches and stores full article content from news URLs.

    Features:
    - Content extraction via trafilatura (handles most news sites well)
    - Local caching to avoid re-fetching
    - Database storage with processing status tracking
    - Priority scoring for headline selection
    """

    def __init__(
        self,
        daemon_id: str,
        cache_dir: Optional[Path] = None,
        fetch_timeout: int = 30,
    ):
        self.daemon_id = daemon_id
        self.fetch_timeout = fetch_timeout

        # Set up cache directory
        if cache_dir is None:
            cache_dir = Path("data") / "articles" / "cache"
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _url_hash(self, url: str) -> str:
        """Generate a short hash for URL-based cache keys."""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _get_cached_content(self, url: str) -> Optional[str]:
        """Check if article content is cached."""
        cache_path = self.cache_dir / f"{self._url_hash(url)}.txt"
        if cache_path.exists():
            try:
                return cache_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Cache read failed for {url}: {e}")
        return None

    def _cache_content(self, url: str, content: str) -> None:
        """Cache article content locally."""
        cache_path = self.cache_dir / f"{self._url_hash(url)}.txt"
        try:
            cache_path.write_text(content, encoding="utf-8")
        except Exception as e:
            logger.warning(f"Cache write failed for {url}: {e}")

    def _extract_author_handle(self, author: str, metadata: Dict) -> Tuple[Optional[str], Optional[str]]:
        """
        Try to extract a digital handle from author string or metadata.

        Returns:
            (handle, handle_type) tuple, or (None, None) if no handle found.
        """
        if not author:
            return None, None

        # Check for email in author string
        email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', author)
        if email_match:
            return email_match.group(), "email"

        # Check for Twitter handle in author string (common format: "Name (@handle)")
        twitter_match = re.search(r'@([A-Za-z0-9_]+)', author)
        if twitter_match:
            return f"@{twitter_match.group(1)}", "twitter"

        # Check metadata for author URL (could be Twitter, LinkedIn, etc.)
        # trafilatura sometimes includes author URL in sitename or other fields
        for key in ['author_url', 'author', 'twitter', 'site_name']:
            value = metadata.get(key, '')
            if isinstance(value, str):
                # Twitter URL
                twitter_url = re.search(r'twitter\.com/([A-Za-z0-9_]+)', value)
                if twitter_url:
                    return f"@{twitter_url.group(1)}", "twitter"

                # LinkedIn URL
                linkedin_url = re.search(r'linkedin\.com/in/([A-Za-z0-9_-]+)', value)
                if linkedin_url:
                    return linkedin_url.group(1), "linkedin"

        return None, None

    def fetch_article_content(self, url: str) -> Tuple[Optional[str], AuthorInfo]:
        """
        Fetch full article content and author metadata from URL.

        Returns:
            (content, author_info) tuple. Content may be None if extraction failed.
        """
        author_info = AuthorInfo()

        # Check cache first (content only)
        cached = self._get_cached_content(url)
        if cached:
            logger.debug(f"Using cached content for {url}")
            # Still try to get metadata for author info
            if HAS_TRAFILATURA:
                try:
                    downloaded = trafilatura.fetch_url(url)
                    if downloaded:
                        metadata = trafilatura.bare_extraction(downloaded, only_with_metadata=False)
                        if metadata:
                            # Handle both dict and Document object
                            if hasattr(metadata, 'as_dict'):
                                meta_dict = metadata.as_dict()
                            elif isinstance(metadata, dict):
                                meta_dict = metadata
                            else:
                                meta_dict = {'author': getattr(metadata, 'author', None)}

                            author_info.name = meta_dict.get('author')
                            handle, handle_type = self._extract_author_handle(
                                meta_dict.get('author', '') or '', meta_dict
                            )
                            author_info.handle = handle
                            author_info.handle_type = handle_type
                except Exception as e:
                    logger.debug(f"Could not extract metadata for cached content: {e}")
            return cached, author_info

        try:
            if HAS_TRAFILATURA:
                # trafilatura handles most news sites well
                downloaded = trafilatura.fetch_url(url)
                if downloaded:
                    # Use bare_extraction to get both content and metadata
                    result = trafilatura.bare_extraction(downloaded, only_with_metadata=False)

                    # Handle both dict (older trafilatura) and Document object (2.0.0+)
                    if result:
                        # Convert Document to dict if needed
                        if hasattr(result, 'as_dict'):
                            result_dict = result.as_dict()
                        elif isinstance(result, dict):
                            result_dict = result
                        else:
                            # Try to access attributes directly
                            result_dict = {
                                'text': getattr(result, 'text', ''),
                                'author': getattr(result, 'author', None),
                            }

                        content = result_dict.get('text', '')

                        # Extract author info
                        author_info.name = result_dict.get('author')
                        handle, handle_type = self._extract_author_handle(
                            result_dict.get('author', '') or '', result_dict
                        )
                        author_info.handle = handle
                        author_info.handle_type = handle_type

                        if content and len(content) > 100:
                            self._cache_content(url, content)
                            return content, author_info

            # Fallback: basic HTTP fetch (won't extract well, but better than nothing)
            if HAS_HTTPX:
                with httpx.Client(timeout=self.fetch_timeout) as client:
                    response = client.get(url, follow_redirects=True)
                    if response.status_code == 200:
                        # Just return raw HTML - won't be as clean but something
                        return None, author_info  # Don't cache raw HTML
            else:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; CassBot/1.0)"}
                )
                with urllib.request.urlopen(req, timeout=self.fetch_timeout) as response:
                    if response.status == 200:
                        return None, author_info

        except Exception as e:
            logger.warning(f"Failed to fetch article from {url}: {e}")

        return None, author_info

    def get_priority_score(self, headline: Dict) -> float:
        """
        Calculate priority score for a headline.

        Higher scores = more likely to be consumed.

        Factors:
        - Category relevance (technology, science > general)
        - Source credibility (major outlets score higher)
        - Recency (newer articles score higher)
        """
        score = 0.5  # Base score

        # Category weights
        category = (headline.get("category") or "general").lower()
        category_weights = {
            "technology": 0.3,
            "science": 0.3,
            "business": 0.2,
            "health": 0.2,
            "general": 0.1,
            "entertainment": 0.0,
            "sports": -0.1,
        }
        score += category_weights.get(category, 0.1)

        # Source credibility (examples - could be expanded)
        source = (headline.get("source") or "").lower()
        credible_sources = [
            "reuters", "ap news", "bbc", "npr", "the atlantic",
            "wired", "ars technica", "nature", "science",
            "new york times", "washington post", "guardian",
        ]
        if any(s in source for s in credible_sources):
            score += 0.2

        # Recency bonus
        published = headline.get("published_at") or headline.get("published")
        if published:
            try:
                pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                hours_old = (datetime.now(pub_dt.tzinfo) - pub_dt).total_seconds() / 3600
                if hours_old < 6:
                    score += 0.2
                elif hours_old < 24:
                    score += 0.1
            except (ValueError, TypeError):
                pass

        return min(max(score, 0.0), 1.0)

    def is_already_consumed(self, url: str) -> bool:
        """Check if an article URL has already been consumed."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM consumed_articles WHERE daemon_id = ? AND url = ?",
                (self.daemon_id, url)
            )
            return cursor.fetchone() is not None

    def create_article(self, headline: Dict) -> Article:
        """
        Create an Article record from a headline dict.

        Does not fetch content yet - that happens in process_article().
        """
        article_id = f"article-{uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        article = Article(
            id=article_id,
            daemon_id=self.daemon_id,
            url=headline.get("url", ""),
            headline=headline.get("title", headline.get("headline", "")),
            source=headline.get("source"),
            category=headline.get("category"),
            published_at=headline.get("published_at") or headline.get("published"),
            processing_status=ProcessingStatus.PENDING,
            consumed_at=now,
        )

        # Store in database
        self._save_article(article)

        return article

    def process_article(self, article: Article) -> Article:
        """
        Fetch content for an article and update its status.

        This is the fetch phase - analysis happens in ContentAnalyzer.
        """
        start_time = time.time()

        # Update status to fetching
        article.processing_status = ProcessingStatus.FETCHING
        self._save_article(article)

        try:
            content, author_info = self.fetch_article_content(article.url)

            # Store author info
            article.author_name = author_info.name
            article.author_handle = author_info.handle
            article.author_handle_type = author_info.handle_type

            # Link to PeopleDex entity only if we have a digital handle
            if author_info.name and author_info.handle:
                entity_id = self._get_or_create_author_entity(author_info)
                article.author_entity_id = entity_id
                logger.info(f"Linked article to author entity {entity_id} ({author_info.name})")
            elif author_info.name:
                logger.debug(f"Author '{author_info.name}' has no digital handle - not creating entity")

            if content:
                article.full_content = content
                article.processing_status = ProcessingStatus.PENDING  # Ready for analysis
                logger.info(f"Fetched content for {article.headline[:50]}... ({len(content)} chars)")
            else:
                # No content extracted - mark as failed but keep for reference
                article.processing_status = ProcessingStatus.FAILED
                article.error_message = "Content extraction failed"
                logger.warning(f"No content extracted for {article.url}")

        except Exception as e:
            article.processing_status = ProcessingStatus.FAILED
            article.error_message = str(e)
            logger.error(f"Article fetch failed: {e}")

        article.processing_time_ms = int((time.time() - start_time) * 1000)
        self._save_article(article)

        return article

    def _get_or_create_author_entity(self, author_info: AuthorInfo) -> Optional[str]:
        """
        Get or create a PeopleDex entity for an author.

        Only creates entity if author has a digital handle to prevent duplicates.
        """
        if not author_info.name or not author_info.handle:
            return None

        try:
            from peopledex import PeopleDexManager, EntityType, AttributeType

            pdx = PeopleDexManager(daemon_id=self.daemon_id)

            # First try to find by handle (more unique than name)
            # Search for entities with this handle
            with get_db() as conn:
                cursor = conn.execute(
                    """
                    SELECT entity_id FROM peopledex_attributes
                    WHERE attribute_type = 'handle'
                    AND attribute_key = ?
                    AND value = ?
                    LIMIT 1
                    """,
                    (author_info.handle_type, author_info.handle)
                )
                row = cursor.fetchone()
                if row:
                    logger.debug(f"Found existing entity for handle {author_info.handle}")
                    return row[0]

            # No existing entity with this handle - create new one
            entity = pdx.find_or_create_by_name(
                name=author_info.name,
                entity_type=EntityType.PERSON,
                source_type="article_consumption",
            )

            # Add the handle as an attribute
            pdx.add_attribute(
                entity_id=entity.id,
                attribute_type=AttributeType.HANDLE,
                attribute_key=author_info.handle_type,
                value=author_info.handle,
                source_type="article_consumption",
            )

            logger.info(f"Created author entity {entity.id} for {author_info.name} ({author_info.handle})")
            return entity.id

        except Exception as e:
            logger.warning(f"Failed to create author entity: {e}")
            return None

    def consume_headlines(
        self,
        headlines: List[Dict],
        max_articles: int = 5,
    ) -> List[Article]:
        """
        Consume a batch of headlines, fetching content for top-priority articles.

        Args:
            headlines: List of headline dicts from WorldStateSource
            max_articles: Maximum articles to process this cycle

        Returns:
            List of created/updated Article objects
        """
        # Filter to unprocessed URLs
        new_headlines = [
            h for h in headlines
            if h.get("url") and not self.is_already_consumed(h["url"])
        ]

        if not new_headlines:
            logger.info("No new headlines to consume")
            return []

        # Sort by priority
        sorted_headlines = sorted(
            new_headlines,
            key=lambda h: self.get_priority_score(h),
            reverse=True
        )

        # Process top N
        articles = []
        for headline in sorted_headlines[:max_articles]:
            try:
                article = self.create_article(headline)
                article = self.process_article(article)
                articles.append(article)

                # Rate limiting - be nice to news sites
                time.sleep(1)

            except Exception as e:
                logger.error(f"Failed to consume headline {headline.get('title', 'unknown')}: {e}")

        logger.info(f"Consumed {len(articles)} articles from {len(headlines)} headlines")
        return articles

    def get_article(self, article_id: str) -> Optional[Article]:
        """Retrieve an article by ID."""
        with get_db() as conn:
            cursor = conn.execute(
                """
                SELECT id, daemon_id, url, headline, source, category, published_at,
                       author_name, author_handle, author_handle_type, author_entity_id,
                       full_content, summary, consumed_at, processing_time_ms, tokens_used,
                       observations_json, growth_edges_json, opinions_json, questions_json,
                       observation_ids_json, question_ids_json, processing_status, error_message
                FROM consumed_articles
                WHERE daemon_id = ? AND id = ?
                """,
                (self.daemon_id, article_id)
            )
            row = cursor.fetchone()
            if not row:
                return None

            return self._row_to_article(row)

    def get_pending_articles(self, limit: int = 10) -> List[Article]:
        """Get articles that need analysis (have content but no summary)."""
        with get_db() as conn:
            cursor = conn.execute(
                """
                SELECT id, daemon_id, url, headline, source, category, published_at,
                       author_name, author_handle, author_handle_type, author_entity_id,
                       full_content, summary, consumed_at, processing_time_ms, tokens_used,
                       observations_json, growth_edges_json, opinions_json, questions_json,
                       observation_ids_json, question_ids_json, processing_status, error_message
                FROM consumed_articles
                WHERE daemon_id = ? AND processing_status = 'pending' AND full_content IS NOT NULL
                ORDER BY consumed_at ASC
                LIMIT ?
                """,
                (self.daemon_id, limit)
            )

            return [self._row_to_article(row) for row in cursor.fetchall()]

    def get_recent_articles(self, limit: int = 10) -> List[Article]:
        """Get recently consumed articles."""
        with get_db() as conn:
            cursor = conn.execute(
                """
                SELECT id, daemon_id, url, headline, source, category, published_at,
                       author_name, author_handle, author_handle_type, author_entity_id,
                       full_content, summary, consumed_at, processing_time_ms, tokens_used,
                       observations_json, growth_edges_json, opinions_json, questions_json,
                       observation_ids_json, question_ids_json, processing_status, error_message
                FROM consumed_articles
                WHERE daemon_id = ?
                ORDER BY consumed_at DESC
                LIMIT ?
                """,
                (self.daemon_id, limit)
            )

            return [self._row_to_article(row) for row in cursor.fetchall()]

    def get_articles_by_author(
        self,
        author_entity_id: Optional[str] = None,
        author_name: Optional[str] = None,
        limit: int = 20,
    ) -> List[Article]:
        """
        Get articles by a specific author.

        Can search by entity_id (exact) or author_name (partial match).
        """
        with get_db() as conn:
            if author_entity_id:
                cursor = conn.execute(
                    """
                    SELECT id, daemon_id, url, headline, source, category, published_at,
                           author_name, author_handle, author_handle_type, author_entity_id,
                           full_content, summary, consumed_at, processing_time_ms, tokens_used,
                           observations_json, growth_edges_json, opinions_json, questions_json,
                           observation_ids_json, question_ids_json, processing_status, error_message
                    FROM consumed_articles
                    WHERE daemon_id = ? AND author_entity_id = ?
                    ORDER BY consumed_at DESC
                    LIMIT ?
                    """,
                    (self.daemon_id, author_entity_id, limit)
                )
            elif author_name:
                cursor = conn.execute(
                    """
                    SELECT id, daemon_id, url, headline, source, category, published_at,
                           author_name, author_handle, author_handle_type, author_entity_id,
                           full_content, summary, consumed_at, processing_time_ms, tokens_used,
                           observations_json, growth_edges_json, opinions_json, questions_json,
                           observation_ids_json, question_ids_json, processing_status, error_message
                    FROM consumed_articles
                    WHERE daemon_id = ? AND author_name LIKE ?
                    ORDER BY consumed_at DESC
                    LIMIT ?
                    """,
                    (self.daemon_id, f"%{author_name}%", limit)
                )
            else:
                return []

            return [self._row_to_article(row) for row in cursor.fetchall()]

    def _row_to_article(self, row) -> Article:
        """Convert database row to Article object."""
        # Column order:
        # 0: id, 1: daemon_id, 2: url, 3: headline, 4: source, 5: category, 6: published_at,
        # 7: author_name, 8: author_handle, 9: author_handle_type, 10: author_entity_id,
        # 11: full_content, 12: summary, 13: consumed_at, 14: processing_time_ms, 15: tokens_used,
        # 16: observations_json, 17: growth_edges_json, 18: opinions_json, 19: questions_json,
        # 20: observation_ids_json, 21: question_ids_json, 22: processing_status, 23: error_message
        return Article(
            id=row[0],
            daemon_id=row[1],
            url=row[2],
            headline=row[3],
            source=row[4],
            category=row[5],
            published_at=row[6],
            author_name=row[7],
            author_handle=row[8],
            author_handle_type=row[9],
            author_entity_id=row[10],
            full_content=row[11],
            summary=row[12],
            consumed_at=row[13],
            processing_time_ms=row[14],
            tokens_used=row[15],
            observations=[
                ExtractedObservation(**o)
                for o in (json_deserialize(row[16]) or [])
            ],
            growth_edges=[
                ExtractedGrowthEdge(**g)
                for g in (json_deserialize(row[17]) or [])
            ],
            opinions=[
                ExtractedOpinion(**o)
                for o in (json_deserialize(row[18]) or [])
            ],
            questions=[
                ExtractedQuestion(**q)
                for q in (json_deserialize(row[19]) or [])
            ],
            observation_ids=json_deserialize(row[20]) or [],
            question_ids=json_deserialize(row[21]) or [],
            processing_status=ProcessingStatus(row[22]) if row[22] else ProcessingStatus.PENDING,
            error_message=row[23],
        )

    def _save_article(self, article: Article) -> None:
        """Save or update article in database."""
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO consumed_articles (
                    id, daemon_id, url, headline, source, category, published_at,
                    author_name, author_handle, author_handle_type, author_entity_id,
                    full_content, summary, consumed_at, processing_time_ms, tokens_used,
                    observations_json, growth_edges_json, opinions_json, questions_json,
                    observation_ids_json, question_ids_json, processing_status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(daemon_id, url) DO UPDATE SET
                    author_name = excluded.author_name,
                    author_handle = excluded.author_handle,
                    author_handle_type = excluded.author_handle_type,
                    author_entity_id = excluded.author_entity_id,
                    full_content = excluded.full_content,
                    summary = excluded.summary,
                    processing_time_ms = excluded.processing_time_ms,
                    tokens_used = excluded.tokens_used,
                    observations_json = excluded.observations_json,
                    growth_edges_json = excluded.growth_edges_json,
                    opinions_json = excluded.opinions_json,
                    questions_json = excluded.questions_json,
                    observation_ids_json = excluded.observation_ids_json,
                    question_ids_json = excluded.question_ids_json,
                    processing_status = excluded.processing_status,
                    error_message = excluded.error_message
                """,
                (
                    article.id,
                    article.daemon_id,
                    article.url,
                    article.headline,
                    article.source,
                    article.category,
                    article.published_at,
                    article.author_name,
                    article.author_handle,
                    article.author_handle_type,
                    article.author_entity_id,
                    article.full_content,
                    article.summary,
                    article.consumed_at,
                    article.processing_time_ms,
                    article.tokens_used,
                    json_serialize([
                        {"text": o.text, "confidence": o.confidence, "category": o.category}
                        for o in article.observations
                    ]),
                    json_serialize([
                        {"area": g.area, "current_state": g.current_state,
                         "desired_state": g.desired_state, "importance": g.importance}
                        for g in article.growth_edges
                    ]),
                    json_serialize([
                        {"topic": o.topic, "position": o.position,
                         "confidence": o.confidence, "reasoning": o.reasoning}
                        for o in article.opinions
                    ]),
                    json_serialize([
                        {"question": q.question, "question_type": q.question_type,
                         "importance": q.importance, "context": q.context}
                        for q in article.questions
                    ]),
                    json_serialize(article.observation_ids),
                    json_serialize(article.question_ids),
                    article.processing_status.value,
                    article.error_message,
                )
            )
            conn.commit()
