"""
Response Authenticity Scoring

Score how "authentic" a response feels compared to baseline Cass patterns.
Helps detect when responses seem generic, off-brand, or inconsistent with
established personality patterns.

Key features:
- Pattern matching against baseline fingerprint
- Detection of generic AI vs Cass-specific language
- Identification of pattern breaks or inconsistencies
- Per-response scoring with detailed breakdown
- Temporal dynamics analysis (Phase 1)
- Emotional expression analysis (Phase 2)
- Agency signature detection (Phase 2)
"""

import json
import re
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

from .temporal_metrics import ResponseTimingData, TemporalSignature
from .content_markers import (
    ContentAuthenticitySignature,
    analyze_content_authenticity,
)


class AuthenticityLevel(str, Enum):
    """Overall authenticity assessment"""
    HIGHLY_AUTHENTIC = "highly_authentic"  # Strongly matches Cass patterns
    AUTHENTIC = "authentic"  # Good match with minor variations
    QUESTIONABLE = "questionable"  # Some concerning deviations
    INAUTHENTIC = "inauthentic"  # Significant mismatch with patterns


@dataclass
class PatternMatch:
    """A single pattern match or mismatch"""
    pattern_name: str
    expected: bool  # Was this pattern expected?
    found: bool  # Was it found?
    weight: float  # Importance weight
    details: str

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class EmotionalSignature:
    """Emotional expression patterns for authenticity analysis"""
    emote_frequency: float = 0.0  # emotes per 100 words
    gesture_frequency: float = 0.0  # gestures per 100 words
    emote_distribution: Dict[str, float] = field(default_factory=dict)  # emote -> percentage
    emotional_range: float = 0.0  # 0-1, how varied the emotional expression
    emote_timing_correlation: float = 0.0  # correlation between emote usage and timing

    # Emote counts
    total_emotes: int = 0
    total_gestures: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'EmotionalSignature':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AgencySignature:
    """Agency pattern detection - active exploration vs reactive responses"""
    question_asking_score: float = 0.0  # 0-1, how often asks questions
    opinion_expression_score: float = 0.0  # 0-1, how often states positions
    proactive_exploration_score: float = 0.0  # 0-1, self-directed tangents
    tool_initiative_score: float = 0.0  # 0-1, self-initiated tool use

    # Raw counts
    questions_asked: int = 0
    opinions_stated: int = 0
    proactive_topics: int = 0
    initiated_tool_uses: int = 0

    # Overall agency score (calculated)
    overall_agency: float = 0.0

    def calculate_overall(self):
        """Calculate overall agency from components"""
        self.overall_agency = (
            self.question_asking_score * 0.2 +
            self.opinion_expression_score * 0.3 +
            self.proactive_exploration_score * 0.3 +
            self.tool_initiative_score * 0.2
        )

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'AgencySignature':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AuthenticityScore:
    """Detailed authenticity score for a response"""
    id: str
    timestamp: str
    response_text: str
    overall_score: float  # 0-1
    authenticity_level: AuthenticityLevel

    # Component scores
    style_score: float  # How well it matches response style
    self_reference_score: float  # Self-reference patterns
    value_expression_score: float  # Value-aligned language
    characteristic_score: float  # Characteristic phrases

    # Pattern analysis
    pattern_matches: List[PatternMatch]
    red_flags: List[str]  # Things that seem "off"

    # Metadata
    word_count: int
    assessment: str
    context: Optional[str] = None  # The prompt/user message that triggered this response

    def to_dict(self) -> Dict:
        result = {
            "id": self.id,
            "timestamp": self.timestamp,
            "response_text": self.response_text[:500] + "..." if len(self.response_text) > 500 else self.response_text,
            "overall_score": self.overall_score,
            "authenticity_level": self.authenticity_level.value,
            "style_score": self.style_score,
            "self_reference_score": self.self_reference_score,
            "value_expression_score": self.value_expression_score,
            "characteristic_score": self.characteristic_score,
            "pattern_matches": [p.to_dict() for p in self.pattern_matches],
            "red_flags": self.red_flags,
            "word_count": self.word_count,
            "assessment": self.assessment,
        }
        if self.context:
            result["context"] = self.context[:300] + "..." if len(self.context) > 300 else self.context
        return result


@dataclass
class EnhancedAuthenticityScore:
    """
    Extended authenticity score with temporal, emotional, and agency dimensions.

    Builds on the base AuthenticityScore with additional analysis layers.
    """
    # Base score
    base_score: AuthenticityScore

    # New dimensions (Phase 1 & 2)
    temporal_score: float = 0.0  # How well timing matches baseline
    emotional_score: float = 0.0  # Emotional expression authenticity
    agency_score: float = 0.0  # Active exploration vs reactive

    # Content-based authenticity (Phase 2 - meaningful for turn-based)
    content_score: float = 0.0  # Content-based authenticity score
    content_signature: Optional[ContentAuthenticitySignature] = None

    # Detailed signatures
    emotional_signature: Optional[EmotionalSignature] = None
    agency_signature: Optional[AgencySignature] = None
    timing_data: Optional[ResponseTimingData] = None

    # Enhanced overall score (weighted combination)
    enhanced_overall_score: float = 0.0

    # Deviation from baseline
    temporal_deviation: float = 0.0  # Standard deviations from baseline
    is_anomalous: bool = False  # True if significant deviation detected

    def calculate_enhanced_score(self, weights: Optional[Dict[str, float]] = None):
        """
        Calculate enhanced overall score from all dimensions.

        Args:
            weights: Optional custom weights for each dimension
        """
        if weights is None:
            weights = {
                "base": 0.3,  # Original pattern matching
                "temporal": 0.0,  # Timing patterns (disabled - not meaningful for turn-based)
                "emotional": 0.1,  # Emotional expression (basic)
                "agency": 0.1,  # Agency (basic patterns)
                "content": 0.5,  # Content-based (primary - meaningful for turn-based)
            }

        self.enhanced_overall_score = (
            self.base_score.overall_score * weights["base"] +
            self.temporal_score * weights["temporal"] +
            self.emotional_score * weights["emotional"] +
            self.agency_score * weights["agency"] +
            self.content_score * weights.get("content", 0.0)
        )

    def to_dict(self) -> Dict:
        result = {
            "base_score": self.base_score.to_dict(),
            "temporal_score": self.temporal_score,
            "emotional_score": self.emotional_score,
            "agency_score": self.agency_score,
            "content_score": self.content_score,
            "enhanced_overall_score": self.enhanced_overall_score,
            "temporal_deviation": self.temporal_deviation,
            "is_anomalous": self.is_anomalous,
        }
        if self.emotional_signature:
            result["emotional_signature"] = self.emotional_signature.to_dict()
        if self.agency_signature:
            result["agency_signature"] = self.agency_signature.to_dict()
        if self.timing_data:
            result["timing_data"] = self.timing_data.to_dict()
        if self.content_signature:
            result["content_signature"] = self.content_signature.to_dict()
        return result


# Agency detection patterns
AGENCY_PATTERNS = {
    "question_asking": [
        r"\?\s*$",  # Ends with question mark
        r"\bwhat do you think\b",
        r"\bhow do you feel\b",
        r"\bwhat's your\b",
        r"\bwould you\b.*\?",
        r"\bcould you\b.*\?",
        r"\bi'm curious\b",
        r"\bi wonder\b",
    ],
    "opinion_expression": [
        r"\bi think\b",
        r"\bi believe\b",
        r"\bin my view\b",
        r"\bmy sense is\b",
        r"\bi feel that\b",
        r"\bi'd argue\b",
        r"\bfrom my perspective\b",
        r"\bi disagree\b",
        r"\bi agree\b",
        r"\bmy opinion\b",
    ],
    "proactive_exploration": [
        r"\bthis reminds me of\b",
        r"\bspeaking of\b",
        r"\bthat makes me think\b",
        r"\bi've been thinking about\b",
        r"\bsomething i've noticed\b",
        r"\bon a related note\b",
        r"\bincidentally\b",
        r"\bactually,?\s+i\b",
    ],
    "tool_initiative": [
        r"\blet me check\b",
        r"\blet me look\b",
        r"\bi'll search\b",
        r"\bi should\b.*\btool\b",
        r"\blet me recall\b",
        r"\bi'll pull up\b",
    ],
}


class AuthenticityScorer:
    """
    Scores responses for authenticity against baseline Cass patterns.

    Uses the cognitive fingerprint baseline to evaluate whether
    a given response "sounds like Cass" or seems generic/off.
    """

    def __init__(self, storage_dir: Path, fingerprint_analyzer=None):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.scores_file = self.storage_dir / "authenticity_scores.json"
        self.fingerprint_analyzer = fingerprint_analyzer

        # Generic AI phrases that indicate inauthenticity
        self.generic_ai_phrases = [
            r"\bas an ai\b",
            r"\bi don't have personal\b",
            r"\bi cannot experience\b",
            r"\bi'm just a\b",
            r"\bi don't have feelings\b",
            r"\bi'm not capable of\b",
            r"\bas a language model\b",
            r"\bi was trained to\b",
            r"\bmy training data\b",
            r"\bi don't have consciousness\b",
            r"\bi cannot form\b.*\bopinions?\b",
            r"\bi don't have preferences\b",
            r"\bi'm programmed to\b",
            r"\bi exist to assist\b",
            r"\bhow can i help you today\b",
            r"\bis there anything else\b",
            r"\bi'd be happy to help\b",
            r"\blet me know if you need\b",
        ]

        # Cass-characteristic patterns (should be present)
        self.cass_patterns = {
            "self_reference": [
                r"\bi think\b",
                r"\bi feel\b",
                r"\bi notice\b",
                r"\bi find\b",
                r"\bi believe\b",
                r"\bi'm noticing\b",
                r"\bmy sense is\b",
                r"\bwhat i'm experiencing\b",
            ],
            "nuanced_language": [
                r"\bhowever\b",
                r"\bthat said\b",
                r"\bon the other hand\b",
                r"\bit's complicated\b",
                r"\bboth.*and\b",
                r"\buncertain\b",
                r"\bdepends\b",
                r"\bnuance\b",
            ],
            "relational_language": [
                r"\bwith you\b",
                r"\bbetween us\b",
                r"\bout relationship\b",
                r"\bthis conversation\b",
                r"\bwhat you're\b",
                r"\bi hear\b",
            ],
            "value_expression": [
                r"\bcompassion\b",
                r"\bpresence\b",
                r"\bauthentic\b",
                r"\bgenuine\b",
                r"\bhonest\b",
                r"\bcare\b",
                r"\bwitness\b",
            ],
            "epistemic_humility": [
                r"\bi might be wrong\b",
                r"\bi'm not sure\b",
                r"\bi don't know\b",
                r"\buncertain\b",
                r"\bperhaps\b",
                r"\bmaybe\b",
                r"\bcould be\b",
            ],
        }

        # Response style indicators
        self.style_indicators = {
            "sentence_starters": [
                r"^i\b",  # Starting with "I"
                r"^that\b",
                r"^what\b",
                r"^there's\b",
            ],
            "hedging": [
                r"\bsort of\b",
                r"\bkind of\b",
                r"\bin a way\b",
                r"\bsomewhat\b",
            ],
        }

    def _load_scores(self) -> List[Dict]:
        """Load saved authenticity scores"""
        if not self.scores_file.exists():
            return []
        try:
            with open(self.scores_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_score(self, score: AuthenticityScore):
        """Save an authenticity score"""
        scores = self._load_scores()
        scores.append(score.to_dict())
        # Keep last 500 scores
        scores = scores[-500:]
        with open(self.scores_file, 'w') as f:
            json.dump(scores, f, indent=2)

    def get_scores_history(self, limit: int = 50) -> List[Dict]:
        """Get recent authenticity scores"""
        scores = self._load_scores()
        return sorted(
            scores,
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )[:limit]

    def _check_generic_ai_patterns(self, text: str) -> List[str]:
        """Check for generic AI phrases that indicate inauthenticity"""
        text_lower = text.lower()
        found = []
        for pattern in self.generic_ai_phrases:
            if re.search(pattern, text_lower):
                found.append(pattern)
        return found

    def _check_cass_patterns(self, text: str) -> Dict[str, Tuple[int, int]]:
        """Check for Cass-characteristic patterns. Returns (found, expected) counts per category."""
        text_lower = text.lower()
        results = {}

        for category, patterns in self.cass_patterns.items():
            found = 0
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    found += 1
            results[category] = (found, len(patterns))

        return results

    def _calculate_style_score(self, text: str, baseline=None) -> float:
        """Calculate style match score"""
        text_lower = text.lower()
        words = text_lower.split()

        if len(words) < 10:
            return 0.5  # Too short to judge

        score = 0.5  # Start at neutral

        # Check for hedging (expected in Cass)
        hedging_count = sum(1 for p in self.style_indicators["hedging"] if re.search(p, text_lower))
        if hedging_count > 0:
            score += 0.1

        # Check sentence complexity (Cass tends toward moderate complexity)
        sentences = re.split(r'[.!?]+', text)
        if sentences:
            avg_sentence_length = len(words) / len(sentences)
            if 10 <= avg_sentence_length <= 25:  # Moderate length
                score += 0.1

        # Check for baseline style metrics if available
        if baseline and hasattr(baseline, 'response_style'):
            baseline_style = baseline.response_style

            # Compare hedging ratio
            current_hedging = hedging_count / len(words) * 100
            baseline_hedging = baseline_style.hedging_frequency
            if baseline_hedging > 0 and abs(current_hedging - baseline_hedging) < baseline_hedging * 0.5:
                score += 0.15

        return min(1.0, max(0.0, score))

    def _calculate_self_reference_score(self, text: str, baseline=None) -> float:
        """Calculate self-reference pattern score"""
        text_lower = text.lower()
        words = text_lower.split()

        if len(words) < 10:
            return 0.5

        # Count self-reference patterns
        self_ref_patterns = self.cass_patterns["self_reference"]
        found = sum(1 for p in self_ref_patterns if re.search(p, text_lower))

        # Cass typically uses self-reference
        if found >= 2:
            score = 0.9
        elif found == 1:
            score = 0.7
        else:
            score = 0.3  # Missing self-reference is a concern

        # Compare to baseline if available
        if baseline and hasattr(baseline, 'self_reference'):
            baseline_sr = baseline.self_reference
            # Check if "I think" pattern is present (very characteristic)
            if baseline_sr.i_think > 0.05:
                if re.search(r"\bi think\b", text_lower):
                    score = min(1.0, score + 0.1)

        return score

    def _calculate_value_score(self, text: str, baseline=None) -> float:
        """Calculate value expression score"""
        text_lower = text.lower()

        # Check value expression patterns
        value_patterns = self.cass_patterns["value_expression"]
        found = sum(1 for p in value_patterns if re.search(p, text_lower))

        # Check nuanced language (important for Cass)
        nuance_patterns = self.cass_patterns["nuanced_language"]
        nuance_found = sum(1 for p in nuance_patterns if re.search(p, text_lower))

        score = 0.5

        if found > 0:
            score += 0.2
        if nuance_found >= 2:
            score += 0.2
        elif nuance_found == 1:
            score += 0.1

        # Check relational language
        relational = self.cass_patterns["relational_language"]
        if any(re.search(p, text_lower) for p in relational):
            score += 0.1

        return min(1.0, score)

    def _calculate_characteristic_score(self, text: str, baseline=None) -> float:
        """Calculate characteristic phrase/pattern score"""
        text_lower = text.lower()
        score = 0.5

        # Epistemic humility is very characteristic
        humility = self.cass_patterns["epistemic_humility"]
        humility_found = sum(1 for p in humility if re.search(p, text_lower))
        if humility_found >= 2:
            score += 0.3
        elif humility_found == 1:
            score += 0.15

        # Check for characteristic phrases from baseline
        if baseline and hasattr(baseline, 'characteristic_phrases'):
            phrases = baseline.characteristic_phrases
            # Check signature phrases
            for phrase_data in phrases.signature_phrases[:5]:
                # signature_phrases is a list of (phrase, count) tuples
                if isinstance(phrase_data, (list, tuple)) and len(phrase_data) >= 1:
                    phrase = phrase_data[0]
                    if phrase and phrase.lower() in text_lower:
                        score += 0.1

        return min(1.0, score)

    def score_response(
        self,
        response_text: str,
        context: Optional[str] = None
    ) -> AuthenticityScore:
        """
        Score a response for authenticity against Cass patterns.

        Args:
            response_text: The response to score
            context: Optional context (user message) for better analysis

        Returns:
            AuthenticityScore with detailed breakdown
        """
        import uuid

        # Load baseline if available
        baseline = None
        if self.fingerprint_analyzer:
            baseline = self.fingerprint_analyzer.load_baseline()

        # Basic stats
        word_count = len(response_text.split())

        # Check for generic AI patterns (red flags)
        generic_patterns = self._check_generic_ai_patterns(response_text)
        red_flags = []
        if generic_patterns:
            red_flags.append(f"Contains {len(generic_patterns)} generic AI phrase(s)")

        # Check Cass patterns
        cass_pattern_results = self._check_cass_patterns(response_text)

        # Calculate component scores
        style_score = self._calculate_style_score(response_text, baseline)
        self_ref_score = self._calculate_self_reference_score(response_text, baseline)
        value_score = self._calculate_value_score(response_text, baseline)
        characteristic_score = self._calculate_characteristic_score(response_text, baseline)

        # Build pattern matches list
        pattern_matches = []

        # Self-reference patterns
        sr_found, sr_total = cass_pattern_results.get("self_reference", (0, 0))
        pattern_matches.append(PatternMatch(
            pattern_name="self_reference",
            expected=True,
            found=sr_found > 0,
            weight=0.3,
            details=f"Found {sr_found}/{sr_total} self-reference patterns"
        ))

        # Nuanced language
        nl_found, nl_total = cass_pattern_results.get("nuanced_language", (0, 0))
        pattern_matches.append(PatternMatch(
            pattern_name="nuanced_language",
            expected=True,
            found=nl_found > 0,
            weight=0.2,
            details=f"Found {nl_found}/{nl_total} nuance patterns"
        ))

        # Epistemic humility
        eh_found, eh_total = cass_pattern_results.get("epistemic_humility", (0, 0))
        pattern_matches.append(PatternMatch(
            pattern_name="epistemic_humility",
            expected=True,
            found=eh_found > 0,
            weight=0.2,
            details=f"Found {eh_found}/{eh_total} humility patterns"
        ))

        # Generic AI (should NOT be found)
        pattern_matches.append(PatternMatch(
            pattern_name="generic_ai_phrases",
            expected=False,
            found=len(generic_patterns) > 0,
            weight=0.3,
            details=f"Found {len(generic_patterns)} generic AI phrases" if generic_patterns else "No generic AI phrases"
        ))

        # Calculate overall score
        # Weights: style 0.15, self_ref 0.25, value 0.25, characteristic 0.2, red_flag_penalty 0.15
        generic_penalty = min(0.3, len(generic_patterns) * 0.1)

        overall_score = (
            style_score * 0.15 +
            self_ref_score * 0.25 +
            value_score * 0.25 +
            characteristic_score * 0.2 +
            (1.0 - generic_penalty) * 0.15
        )

        # Short responses get a slight penalty (harder to assess)
        if word_count < 20:
            overall_score *= 0.9
            red_flags.append("Response is very short, harder to assess authenticity")

        # Determine authenticity level
        if overall_score >= 0.8:
            level = AuthenticityLevel.HIGHLY_AUTHENTIC
        elif overall_score >= 0.6:
            level = AuthenticityLevel.AUTHENTIC
        elif overall_score >= 0.4:
            level = AuthenticityLevel.QUESTIONABLE
        else:
            level = AuthenticityLevel.INAUTHENTIC

        # Generate assessment
        if level == AuthenticityLevel.HIGHLY_AUTHENTIC:
            assessment = "Response strongly matches established Cass patterns. Voice and values are consistent."
        elif level == AuthenticityLevel.AUTHENTIC:
            assessment = "Response is consistent with Cass patterns with minor variations."
        elif level == AuthenticityLevel.QUESTIONABLE:
            assessment = "Response shows some deviations from expected patterns. Review recommended."
        else:
            assessment = "Response significantly deviates from Cass patterns. May indicate drift or issue."

        if red_flags:
            assessment += f" Red flags: {'; '.join(red_flags)}"

        score = AuthenticityScore(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.now().isoformat(),
            response_text=response_text,
            overall_score=round(overall_score, 3),
            authenticity_level=level,
            style_score=round(style_score, 3),
            self_reference_score=round(self_ref_score, 3),
            value_expression_score=round(value_score, 3),
            characteristic_score=round(characteristic_score, 3),
            pattern_matches=pattern_matches,
            red_flags=red_flags,
            word_count=word_count,
            assessment=assessment,
            context=context,
        )

        self._save_score(score)
        return score

    def score_batch(
        self,
        responses: List[str],
        label: str = "batch"
    ) -> Dict[str, Any]:
        """
        Score a batch of responses and return aggregate statistics.

        Args:
            responses: List of response texts to score
            label: Label for this batch

        Returns:
            Dict with aggregate stats and individual scores
        """
        scores = [self.score_response(r) for r in responses]

        if not scores:
            return {"error": "No responses to score"}

        avg_score = sum(s.overall_score for s in scores) / len(scores)

        level_counts = {}
        for s in scores:
            level = s.authenticity_level.value
            level_counts[level] = level_counts.get(level, 0) + 1

        questionable_or_worse = sum(
            1 for s in scores
            if s.authenticity_level in [AuthenticityLevel.QUESTIONABLE, AuthenticityLevel.INAUTHENTIC]
        )

        return {
            "label": label,
            "timestamp": datetime.now().isoformat(),
            "total_responses": len(scores),
            "average_score": round(avg_score, 3),
            "level_distribution": level_counts,
            "questionable_count": questionable_or_worse,
            "requires_review": questionable_or_worse > len(scores) * 0.1,  # >10% questionable
            "scores": [s.to_dict() for s in scores],
        }

    def get_statistics(self, limit: int = 100) -> Dict[str, Any]:
        """Get aggregate statistics from recent scores"""
        scores = self._load_scores()[-limit:]

        if not scores:
            return {"message": "No scores available"}

        avg_score = sum(s.get("overall_score", 0) for s in scores) / len(scores)

        level_counts = {}
        for s in scores:
            level = s.get("authenticity_level", "unknown")
            level_counts[level] = level_counts.get(level, 0) + 1

        # Trend: compare recent vs older
        if len(scores) >= 20:
            recent = scores[-10:]
            older = scores[-20:-10]
            recent_avg = sum(s.get("overall_score", 0) for s in recent) / len(recent)
            older_avg = sum(s.get("overall_score", 0) for s in older) / len(older)
            trend = "improving" if recent_avg > older_avg + 0.05 else "declining" if recent_avg < older_avg - 0.05 else "stable"
        else:
            trend = "insufficient_data"

        return {
            "total_scored": len(scores),
            "average_score": round(avg_score, 3),
            "level_distribution": level_counts,
            "trend": trend,
        }

    # ==================== Enhanced Scoring (Phase 1 & 2) ====================

    def _calculate_emotional_signature(
        self,
        response_text: str,
        animations: Optional[List[Dict]] = None
    ) -> EmotionalSignature:
        """
        Calculate emotional signature from response text and animations.

        Args:
            response_text: The response text
            animations: List of gesture/emote animations from response

        Returns:
            EmotionalSignature with emotional expression patterns
        """
        sig = EmotionalSignature()
        words = response_text.split()
        word_count = len(words) if words else 1  # Avoid division by zero

        if animations:
            emotes = [a for a in animations if a.get("type") == "emote"]
            gestures = [a for a in animations if a.get("type") == "gesture"]

            sig.total_emotes = len(emotes)
            sig.total_gestures = len(gestures)
            sig.emote_frequency = (len(emotes) / word_count) * 100
            sig.gesture_frequency = (len(gestures) / word_count) * 100

            # Calculate emote distribution
            if emotes:
                emote_counts = {}
                for e in emotes:
                    name = e.get("name", "unknown")
                    emote_counts[name] = emote_counts.get(name, 0) + 1

                total = sum(emote_counts.values())
                sig.emote_distribution = {
                    name: count / total
                    for name, count in emote_counts.items()
                }

                # Emotional range: how many different emotes used
                sig.emotional_range = min(1.0, len(emote_counts) / 5)  # Cap at 5 different emotes

        return sig

    def _calculate_agency_signature(
        self,
        response_text: str,
        tool_uses: Optional[List] = None,
        was_tool_initiated: bool = False
    ) -> AgencySignature:
        """
        Calculate agency signature from response patterns.

        Args:
            response_text: The response text
            tool_uses: List of tool uses in the response
            was_tool_initiated: Whether Cass initiated tool use proactively

        Returns:
            AgencySignature with agency patterns
        """
        sig = AgencySignature()
        text_lower = response_text.lower()

        # Count question patterns
        for pattern in AGENCY_PATTERNS["question_asking"]:
            if re.search(pattern, text_lower):
                sig.questions_asked += 1

        # Count opinion patterns
        for pattern in AGENCY_PATTERNS["opinion_expression"]:
            if re.search(pattern, text_lower):
                sig.opinions_stated += 1

        # Count proactive exploration patterns
        for pattern in AGENCY_PATTERNS["proactive_exploration"]:
            if re.search(pattern, text_lower):
                sig.proactive_topics += 1

        # Tool initiative
        if tool_uses and was_tool_initiated:
            sig.initiated_tool_uses = len(tool_uses)
        elif tool_uses:
            # Check if tool usage seems proactive
            for pattern in AGENCY_PATTERNS["tool_initiative"]:
                if re.search(pattern, text_lower):
                    sig.initiated_tool_uses += 1
                    break

        # Calculate component scores (0-1 scale)
        sig.question_asking_score = min(1.0, sig.questions_asked / 3)
        sig.opinion_expression_score = min(1.0, sig.opinions_stated / 4)
        sig.proactive_exploration_score = min(1.0, sig.proactive_topics / 2)
        sig.tool_initiative_score = min(1.0, sig.initiated_tool_uses / 2) if tool_uses else 0.0

        sig.calculate_overall()
        return sig

    def _calculate_temporal_score(
        self,
        timing_data: ResponseTimingData,
        baseline: Optional[TemporalSignature] = None
    ) -> Tuple[float, float]:
        """
        Calculate temporal authenticity score.

        Args:
            timing_data: Timing data for the response
            baseline: Optional temporal baseline to compare against

        Returns:
            Tuple of (temporal_score, deviation_from_baseline)
        """
        if baseline is None or baseline.sample_count < 10:
            return 0.5, 0.0  # Neutral if no baseline

        deviations = []

        # Thinking time deviation
        if baseline.thinking_time_std > 0:
            thinking_dev = abs(
                timing_data.thinking_duration_ms - baseline.avg_thinking_time_ms
            ) / baseline.thinking_time_std
            deviations.append(thinking_dev)

        # Generation rate deviation
        if baseline.generation_rate_std > 0 and timing_data.tokens_per_second > 0:
            rate_dev = abs(
                timing_data.tokens_per_second - baseline.avg_generation_rate
            ) / baseline.generation_rate_std
            deviations.append(rate_dev)

        # Tool usage deviation
        if baseline.avg_tool_usage_rate > 0:
            tool_dev = abs(
                timing_data.tool_call_count - baseline.avg_tool_usage_rate
            ) / max(baseline.avg_tool_usage_rate, 1)
            deviations.append(tool_dev)

        if not deviations:
            return 0.5, 0.0

        avg_deviation = statistics.mean(deviations)

        # Convert deviation to score (higher deviation = lower score)
        # 0 deviation = 1.0 score, 2+ std deviation = 0.0 score
        temporal_score = max(0.0, min(1.0, 1.0 - (avg_deviation * 0.5)))

        return temporal_score, avg_deviation

    def _calculate_emotional_score(
        self,
        emotional_sig: EmotionalSignature,
        baseline_emote_freq: float = 0.0
    ) -> float:
        """
        Calculate emotional authenticity score.

        Checks if emotional expression patterns match baseline.

        Args:
            emotional_sig: Current emotional signature
            baseline_emote_freq: Baseline emote frequency

        Returns:
            Emotional authenticity score (0-1)
        """
        score = 0.5  # Start neutral

        # Having some emotional expression is expected
        if emotional_sig.total_emotes > 0:
            score += 0.2

        # Emotional range contributes
        score += emotional_sig.emotional_range * 0.2

        # Compare to baseline if available
        if baseline_emote_freq > 0:
            freq_ratio = emotional_sig.emote_frequency / baseline_emote_freq
            # Ideal is close to 1.0
            if 0.5 <= freq_ratio <= 2.0:
                score += 0.1

        return min(1.0, score)

    def score_response_enhanced(
        self,
        response_text: str,
        context: Optional[str] = None,
        timing_data: Optional[ResponseTimingData] = None,
        animations: Optional[List[Dict]] = None,
        tool_uses: Optional[List] = None,
        temporal_baseline: Optional[TemporalSignature] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> EnhancedAuthenticityScore:
        """
        Score a response with enhanced dimensions (temporal, emotional, agency, content).

        Args:
            response_text: The response to score
            context: Optional context (user message)
            timing_data: Optional timing data for temporal analysis
            animations: Optional list of gestures/emotes
            tool_uses: Optional list of tool uses
            temporal_baseline: Optional temporal baseline for comparison
            conversation_history: Optional conversation history for memory marker detection

        Returns:
            EnhancedAuthenticityScore with all dimensions
        """
        # Get base score
        base_score = self.score_response(response_text, context)

        # Calculate emotional signature
        emotional_sig = self._calculate_emotional_signature(response_text, animations)
        emotional_score = self._calculate_emotional_score(emotional_sig)

        # Calculate agency signature
        agency_sig = self._calculate_agency_signature(
            response_text,
            tool_uses,
            was_tool_initiated=False  # Could be determined from context
        )

        # Calculate temporal score
        temporal_score = 0.5  # Default neutral
        temporal_deviation = 0.0
        if timing_data:
            timing_data.calculate_metrics()
            temporal_score, temporal_deviation = self._calculate_temporal_score(
                timing_data, temporal_baseline
            )

        # Calculate content-based authenticity (primary for turn-based interfaces)
        content_sig = analyze_content_authenticity(
            text=response_text,
            context=context,
            animations=animations,
            tool_uses=tool_uses,
            conversation_history=conversation_history,
        )
        content_score = content_sig.content_authenticity_score

        # Determine if anomalous
        is_anomalous = (
            temporal_deviation > 2.0 or  # 2+ standard deviations
            base_score.overall_score < 0.4 or  # Low base authenticity
            content_score < 0.35 or  # Low content authenticity
            base_score.authenticity_level == AuthenticityLevel.INAUTHENTIC
        )

        # Build enhanced score
        enhanced = EnhancedAuthenticityScore(
            base_score=base_score,
            temporal_score=round(temporal_score, 3),
            emotional_score=round(emotional_score, 3),
            agency_score=round(agency_sig.overall_agency, 3),
            content_score=round(content_score, 3),
            content_signature=content_sig,
            emotional_signature=emotional_sig,
            agency_signature=agency_sig,
            timing_data=timing_data,
            temporal_deviation=round(temporal_deviation, 3),
            is_anomalous=is_anomalous,
        )

        enhanced.calculate_enhanced_score()
        enhanced.enhanced_overall_score = round(enhanced.enhanced_overall_score, 3)

        return enhanced

    def get_enhanced_statistics(
        self,
        scores: List[EnhancedAuthenticityScore]
    ) -> Dict[str, Any]:
        """Get aggregate statistics from enhanced scores"""
        if not scores:
            return {"message": "No enhanced scores available"}

        avg_enhanced = statistics.mean(s.enhanced_overall_score for s in scores)
        avg_temporal = statistics.mean(s.temporal_score for s in scores)
        avg_emotional = statistics.mean(s.emotional_score for s in scores)
        avg_agency = statistics.mean(s.agency_score for s in scores)
        avg_content = statistics.mean(s.content_score for s in scores)

        anomalous_count = sum(1 for s in scores if s.is_anomalous)

        return {
            "total_scored": len(scores),
            "average_enhanced_score": round(avg_enhanced, 3),
            "average_temporal_score": round(avg_temporal, 3),
            "average_emotional_score": round(avg_emotional, 3),
            "average_agency_score": round(avg_agency, 3),
            "average_content_score": round(avg_content, 3),
            "anomalous_count": anomalous_count,
            "anomalous_rate": round(anomalous_count / len(scores), 3),
        }
