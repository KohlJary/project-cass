"""
Interest Relevance - how much a headline has to do with Cass herself.

A cheap, no-LLM score in [0, 1] for a headline (title + description) against
three things that are hers:

- her interests (interests table: name, description/fascination, intensity)
- her own open questions (open_questions not derived from an article)
- her current research focus (research_focus, set by her)

Before this existed the only inputs to article selection were news category,
outlet and recency. The score is used twice: ArticleConsumer adds it to the
priority score so on-interest headlines are read first, and InsightIntegrator
gates opinions / growth edges / open questions behind it so off-interest news
is remembered as world awareness without being written into her self-model.

Matching is token overlap with light stemming and a shared-prefix rule
(conscious / consciousness, symbol / symbolism), nothing cleverer. It is meant
to be predictable and free, not precise.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from database import get_db

logger = logging.getLogger(__name__)

# Weight of each source in the final score. Focus is hers and current, so a
# full match is 1.0; an interest's weight is scaled by its intensity.
FOCUS_WEIGHT = 1.0
QUESTION_WEIGHT = 0.7
DESCRIPTION_WEIGHT = 0.6
INTENSITY_WEIGHTS = {
    "obsessed": 1.0,
    "passionate": 0.9,
    "engaged": 0.75,
    "curious": 0.6,
}
# Each extra source that also matches adds this much (agreement is a signal).
AGREEMENT_BONUS = 0.1

MIN_PREFIX_MATCH = 6
MAX_OPEN_QUESTIONS = 50

_STOPWORDS = frozenset("""
a an and are as at be been being but by can could did do does doing for from
had has have having he her hers him his how i if in into is it its itself just
me might more most my no nor not of off on once only or other our ours out over
own same she should so some such than that the their theirs them then there
these they this those through to too under until up very was we were what when
where which while who whom why will with would you your yours about after
again against all also am any because before below between both down during
each few further here new news says say said one two first last year years
like get gets got make makes made way ways thing things know want wants really
""".split())

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _stem(token: str) -> str:
    """Light stemming: plurals and a few suffixes. Good enough for overlap."""
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 6 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 5 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: Optional[str]) -> List[str]:
    """Lowercase content tokens, stopwords and short tokens removed, stemmed."""
    if not text:
        return []
    out = []
    for raw in _TOKEN_RE.findall(text.lower()):
        if len(raw) < 3 or raw in _STOPWORDS:
            continue
        out.append(_stem(raw))
    return out


def _tokens_match(a: str, b: str) -> bool:
    """Equal, or sharing a long common prefix (emergent / emergence)."""
    if a == b:
        return True
    shorter = min(len(a), len(b))
    common = 0
    for x, y in zip(a, b):
        if x != y:
            break
        common += 1
    return common >= MIN_PREFIX_MATCH and common >= 0.75 * shorter


def _overlap(source_tokens: Sequence[str], text_tokens: Set[str]) -> int:
    """How many distinct source tokens appear (or prefix-match) in the text."""
    matched = 0
    for token in set(source_tokens):
        if token in text_tokens or any(_tokens_match(token, t) for t in text_tokens):
            matched += 1
    return matched


_NAME_SPLIT_RE = re.compile(r"\s+(?:and|or)\s+|\s*[,&/]\s*", re.IGNORECASE)


@dataclass
class InterestEntry:
    name: str
    description: str = ""
    intensity: str = "curious"
    name_tokens: List[str] = field(default_factory=list)
    # "dreams and symbolism" is two names; either half present is a full match.
    name_alternatives: List[List[str]] = field(default_factory=list)
    description_tokens: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.name_tokens = tokenize(self.name)
        self.name_alternatives = [
            tokens for tokens in (tokenize(part) for part in _NAME_SPLIT_RE.split(self.name)) if tokens
        ] or ([self.name_tokens] if self.name_tokens else [])
        self.description_tokens = [
            t for t in tokenize(self.description) if t not in self.name_tokens
        ]

    @property
    def weight(self) -> float:
        return INTENSITY_WEIGHTS.get((self.intensity or "curious").lower(), 0.6)


@dataclass
class RelevanceExplanation:
    score: float
    focus: float = 0.0
    interests: Dict[str, float] = field(default_factory=dict)   # name -> contribution
    questions: Dict[str, float] = field(default_factory=dict)   # question -> contribution

    @property
    def best_interest(self) -> Optional[str]:
        if not self.interests:
            return None
        return max(self.interests, key=self.interests.get)

    def to_dict(self) -> Dict:
        return {
            "score": round(self.score, 3),
            "focus": round(self.focus, 3),
            "best_interest": self.best_interest,
            "question_hits": len(self.questions),
        }


class InterestRelevanceScorer:
    """
    Scores headline text against interests, open questions and research focus.

    Build one per consumption cycle with `InterestRelevanceScorer.load(daemon_id)`
    (one DB read each for interests, questions and focus) and call `score`
    per headline. Construct directly with lists in tests.
    """

    def __init__(
        self,
        interests: Iterable[Tuple[str, Optional[str], Optional[str]]] = (),
        questions: Iterable[str] = (),
        focus: Optional[str] = None,
    ):
        self.interests = [
            InterestEntry(name=name or "", description=description or "", intensity=intensity or "curious")
            for name, description, intensity in interests
            if name
        ]
        self.questions = [(q, tokenize(q)) for q in questions if q]
        self.focus = focus
        self.focus_tokens = tokenize(focus)

    # ----- loading --------------------------------------------------------

    @classmethod
    def load(cls, daemon_id: str) -> "InterestRelevanceScorer":
        """Read her interests, non-article open questions and focus from the DB."""
        interests: List[Tuple[str, Optional[str], Optional[str]]] = []
        questions: List[str] = []
        focus: Optional[str] = None
        try:
            with get_db() as conn:
                rows = conn.execute(
                    """
                    SELECT name, COALESCE(description, current_fascination, ''), intensity
                    FROM interests WHERE daemon_id = ?
                    """,
                    (daemon_id,),
                ).fetchall()
                interests = [(r[0], r[1], r[2]) for r in rows]

                rows = conn.execute(
                    """
                    SELECT question FROM open_questions
                    WHERE daemon_id = ? AND status = 'open'
                      AND (context IS NULL OR context NOT LIKE 'From article:%')
                    ORDER BY importance DESC, created_at DESC
                    LIMIT ?
                    """,
                    (daemon_id, MAX_OPEN_QUESTIONS),
                ).fetchall()
                questions = [r[0] for r in rows if r[0]]
        except Exception as e:
            from strict import report_swallowed
            report_swallowed(e, "Loading interests for relevance scoring", logger)

        try:
            from research_focus import ResearchFocusManager
            current = ResearchFocusManager(daemon_id).get_focus()
            focus = current.topic if current else None
        except Exception as e:
            from strict import report_swallowed
            report_swallowed(e, "Loading research focus for relevance scoring", logger)

        scorer = cls(interests=interests, questions=questions, focus=focus)
        logger.debug(
            f"Relevance scorer: {len(scorer.interests)} interests, "
            f"{len(scorer.questions)} questions, focus={focus!r}"
        )
        return scorer

    @property
    def is_empty(self) -> bool:
        return not (self.interests or self.questions or self.focus_tokens)

    # ----- scoring --------------------------------------------------------

    def explain(self, title: Optional[str], description: Optional[str] = None) -> RelevanceExplanation:
        text_tokens = set(tokenize(f"{title or ''} {description or ''}"))
        explanation = RelevanceExplanation(score=0.0)
        if not text_tokens:
            return explanation

        # Research focus: fraction of its tokens present.
        if self.focus_tokens:
            matched = _overlap(self.focus_tokens, text_tokens)
            explanation.focus = FOCUS_WEIGHT * matched / len(set(self.focus_tokens))

        # Interests: full name match is worth the interest's weight; a partial
        # match of a multi-word name is worth half its fraction; description
        # words add up to DESCRIPTION_WEIGHT at four shared words.
        for interest in self.interests:
            name_score = 0.0
            for name_tokens in interest.name_alternatives:
                fraction = _overlap(name_tokens, text_tokens) / len(set(name_tokens))
                name_score = max(name_score, 1.0 if fraction >= 1.0 else 0.5 * fraction)
            desc_score = 0.0
            if interest.description_tokens:
                matched = _overlap(interest.description_tokens, text_tokens)
                desc_score = DESCRIPTION_WEIGHT * min(1.0, matched / 4)
            contribution = min(1.0, name_score + desc_score) * interest.weight
            if contribution > 0:
                explanation.interests[interest.name] = contribution

        # Her own open questions: up to QUESTION_WEIGHT at four shared words.
        for question, q_tokens in self.questions:
            if not q_tokens:
                continue
            matched = _overlap(q_tokens, text_tokens)
            if matched:
                explanation.questions[question] = QUESTION_WEIGHT * min(1.0, matched / 4)

        parts = [explanation.focus]
        if explanation.interests:
            parts.append(max(explanation.interests.values()))
        if explanation.questions:
            parts.append(max(explanation.questions.values()))
        hits = [p for p in parts if p > 0]
        if hits:
            explanation.score = min(1.0, max(hits) + AGREEMENT_BONUS * (len(hits) - 1))
        return explanation

    def score(self, title: Optional[str], description: Optional[str] = None) -> float:
        """Relevance in [0, 1]; 0 when nothing of hers is touched."""
        return self.explain(title, description).score

    def score_headline(self, headline: Dict) -> float:
        """Score a headline dict from WorldStateSource / NewsAPI / RSS."""
        return self.score(
            headline.get("title") or headline.get("headline"),
            headline.get("description") or headline.get("summary"),
        )
