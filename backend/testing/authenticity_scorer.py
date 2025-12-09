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
"""

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum


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
