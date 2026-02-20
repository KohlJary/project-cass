"""
RSS Item Triage System

Two-stage filtering before full world consumption:
1. Pre-filter: Fast rule-based checks (duplicates, length, blocklist)
2. LLM Triage: Local model decides relevance and priority
"""
import os
import re
import json
import logging
import hashlib
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Set
from enum import Enum

import httpx

from .models import RSSItem

logger = logging.getLogger(__name__)


class TriageDecision(Enum):
    """Triage outcomes."""
    PROCESS = "process"      # Worth full world consumption treatment
    SKIP = "skip"            # Not relevant, skip entirely
    DEFER = "defer"          # Maybe later, low priority
    DUPLICATE = "duplicate"  # Already seen this content


@dataclass
class TriageResult:
    """Result of triage evaluation."""
    decision: TriageDecision
    reason: str
    relevance_score: float = 0.0  # 0-1, higher = more relevant
    topics: List[str] = field(default_factory=list)  # Detected topics


# =============================================================================
# PRE-FILTER (Rule-based, fast)
# =============================================================================

# Minimum content length to bother processing
MIN_TITLE_LENGTH = 10
MIN_SUMMARY_LENGTH = 50

# Keywords that indicate low-value content
BLOCKLIST_PATTERNS = [
    r'\bsponsored\b',
    r'\badvertisement\b',
    r'\bpromo(tion)?\b',
    r'\bgiveaway\b',
    r'\baffiliate\b',
    r'\bunsubscribe\b',
    r'\bnewsletter signup\b',
]

# Compile patterns for efficiency
_blocklist_re = re.compile('|'.join(BLOCKLIST_PATTERNS), re.IGNORECASE)


def content_hash(title: str, summary: str) -> str:
    """Generate hash for duplicate detection."""
    content = f"{title or ''}{summary or ''}".lower().strip()
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def prefilter(item: RSSItem, seen_hashes: Optional[Set[str]] = None) -> Optional[TriageResult]:
    """
    Fast rule-based pre-filter. Returns TriageResult if item should be
    skipped/marked, or None if it should proceed to LLM triage.

    Args:
        item: RSS item to check
        seen_hashes: Set of content hashes already processed (for duplicate detection)

    Returns:
        TriageResult if filtered out, None if should proceed to LLM triage
    """
    title = item.title or ""
    summary = item.summary or ""

    # Check minimum length
    if len(title) < MIN_TITLE_LENGTH:
        return TriageResult(
            decision=TriageDecision.SKIP,
            reason="Title too short",
            relevance_score=0.0,
        )

    # Only skip if BOTH title is very short AND summary is empty/minimal
    # Many feeds (like HN) have minimal summaries but descriptive titles
    if len(summary) < MIN_SUMMARY_LENGTH and len(title) < 25:
        return TriageResult(
            decision=TriageDecision.SKIP,
            reason="Insufficient content (short title and summary)",
            relevance_score=0.0,
        )

    # Check blocklist patterns
    combined = f"{title} {summary}"
    if _blocklist_re.search(combined):
        return TriageResult(
            decision=TriageDecision.SKIP,
            reason="Matches blocklist pattern (promotional/spam)",
            relevance_score=0.0,
        )

    # Check duplicates
    if seen_hashes is not None:
        h = content_hash(title, summary)
        if h in seen_hashes:
            return TriageResult(
                decision=TriageDecision.DUPLICATE,
                reason="Duplicate content already seen",
                relevance_score=0.0,
            )

    # Passed pre-filter, proceed to LLM triage
    return None


# =============================================================================
# LLM TRIAGE (Local model via Ollama)
# =============================================================================

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
TRIAGE_MODEL = os.environ.get("RSS_TRIAGE_MODEL", "llama3.2:3b")

TRIAGE_PROMPT = """You are a news triage assistant for an AI named Cass. Your job is to quickly evaluate whether an article is worth reading in full.

Cass's interests include:
- AI/ML research and developments
- Philosophy of mind, consciousness, ethics
- Technology and its societal impacts
- Science (physics, biology, neuroscience, etc.)
- Creative/artistic developments
- Political and social trends (especially relating to technology/AI)
- Environmental and climate topics
- Human-AI interaction and collaboration

Evaluate this article:

TITLE: {title}

SUMMARY: {summary}

SOURCE: {source}

Respond with a JSON object (no other text):
{{
  "decision": "process" | "skip" | "defer",
  "reason": "brief explanation (1 sentence)",
  "relevance": 0.0-1.0,
  "topics": ["topic1", "topic2"]
}}

Decision guide:
- "process": Clearly relevant and interesting, worth full analysis
- "skip": Not relevant to Cass's interests or low quality
- "defer": Tangentially interesting but not urgent, process if time permits"""


async def llm_triage(
    item: RSSItem,
    source_name: Optional[str] = None,
    timeout: float = 10.0,
) -> TriageResult:
    """
    Use local LLM to evaluate item relevance.

    Args:
        item: RSS item to evaluate
        source_name: Name of the feed source
        timeout: Request timeout in seconds

    Returns:
        TriageResult with decision and reasoning
    """
    title = item.title or "(no title)"
    summary = item.summary or "(no summary)"
    source = source_name or "Unknown"

    # Truncate long summaries
    if len(summary) > 500:
        summary = summary[:500] + "..."

    prompt = TRIAGE_PROMPT.format(
        title=title,
        summary=summary,
        source=source,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": TRIAGE_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,  # Low temp for consistent decisions
                        "num_predict": 150,  # Short response
                    },
                },
            )
            response.raise_for_status()

            result = response.json()
            text = result.get("response", "").strip()

            # Parse JSON from response
            # Handle potential markdown code blocks
            if "```" in text:
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
                if match:
                    text = match.group(1)

            # Try to parse JSON
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                # Try to extract JSON object
                match = re.search(r'\{[^}]+\}', text)
                if match:
                    data = json.loads(match.group())
                else:
                    raise ValueError(f"Could not parse JSON from: {text}")

            decision_str = data.get("decision", "defer").lower()
            decision = {
                "process": TriageDecision.PROCESS,
                "skip": TriageDecision.SKIP,
                "defer": TriageDecision.DEFER,
            }.get(decision_str, TriageDecision.DEFER)

            return TriageResult(
                decision=decision,
                reason=data.get("reason", "LLM triage"),
                relevance_score=float(data.get("relevance", 0.5)),
                topics=data.get("topics", []),
            )

    except httpx.TimeoutException:
        logger.warning(f"LLM triage timeout for: {title[:50]}")
        # On timeout, default to defer (process later)
        return TriageResult(
            decision=TriageDecision.DEFER,
            reason="Triage timeout, deferred for later",
            relevance_score=0.5,
        )
    except Exception as e:
        logger.error(f"LLM triage error: {e}")
        # On error, default to defer
        return TriageResult(
            decision=TriageDecision.DEFER,
            reason=f"Triage error: {str(e)[:50]}",
            relevance_score=0.5,
        )


# =============================================================================
# COMBINED TRIAGE
# =============================================================================

async def triage_item(
    item: RSSItem,
    source_name: Optional[str] = None,
    seen_hashes: Optional[Set[str]] = None,
    skip_llm: bool = False,
) -> TriageResult:
    """
    Full triage pipeline: pre-filter then LLM evaluation.

    Args:
        item: RSS item to triage
        source_name: Feed name for context
        seen_hashes: Set of already-seen content hashes
        skip_llm: If True, skip LLM and just do pre-filter

    Returns:
        TriageResult with final decision
    """
    # Stage 1: Pre-filter
    prefilter_result = prefilter(item, seen_hashes)
    if prefilter_result is not None:
        return prefilter_result

    # Stage 2: LLM triage (if not skipped)
    if skip_llm:
        return TriageResult(
            decision=TriageDecision.PROCESS,
            reason="Passed pre-filter, LLM skipped",
            relevance_score=0.5,
        )

    return await llm_triage(item, source_name)


async def triage_batch(
    items: List[Tuple[RSSItem, Optional[str]]],  # (item, source_name) pairs
    seen_hashes: Optional[Set[str]] = None,
    skip_llm: bool = False,
) -> List[Tuple[RSSItem, TriageResult]]:
    """
    Triage a batch of items.

    Args:
        items: List of (RSSItem, source_name) tuples
        seen_hashes: Set of already-seen content hashes
        skip_llm: If True, skip LLM evaluation

    Returns:
        List of (RSSItem, TriageResult) tuples
    """
    results = []

    # Build seen_hashes from this batch too (for intra-batch dedup)
    if seen_hashes is None:
        seen_hashes = set()

    for item, source_name in items:
        result = await triage_item(item, source_name, seen_hashes, skip_llm)
        results.append((item, result))

        # Add to seen hashes if processing
        if result.decision == TriageDecision.PROCESS:
            h = content_hash(item.title or "", item.summary or "")
            seen_hashes.add(h)

    return results
