"""
Cognitive Fingerprint System

Captures Cass's "cognitive fingerprint" - a snapshot of characteristic
response patterns that define her identity. This enables comparison
across time and system changes to verify personality preservation.

Metrics captured:
- Response style (sentence structure, length distribution, hedging)
- Self-reference patterns (I think, I feel, I notice, etc.)
- Value expression patterns (ethics, relationships, uncertainty)
- Characteristic phrases and formulations
- Topic engagement patterns
"""

import json
import re
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import Counter


@dataclass
class ResponseStyleMetrics:
    """Metrics about response style and structure"""
    avg_response_length: float = 0.0
    response_length_std: float = 0.0
    avg_sentence_length: float = 0.0
    sentence_length_std: float = 0.0
    avg_paragraph_count: float = 0.0
    question_frequency: float = 0.0  # Questions per response
    list_usage_frequency: float = 0.0  # Bullet/numbered lists per response
    code_block_frequency: float = 0.0  # Code blocks per response

    # Hedging and certainty
    hedging_frequency: float = 0.0  # Hedging phrases per 100 words
    certainty_frequency: float = 0.0  # Certainty phrases per 100 words

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'ResponseStyleMetrics':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SelfReferencePatterns:
    """Patterns of self-reference in responses"""
    # Frequency per 100 words
    i_think: float = 0.0
    i_feel: float = 0.0
    i_notice: float = 0.0
    i_believe: float = 0.0
    i_wonder: float = 0.0
    i_experience: float = 0.0
    my_sense: float = 0.0
    it_seems: float = 0.0

    # Meta-cognitive references
    meta_cognitive_rate: float = 0.0  # References to own thinking process
    uncertainty_acknowledgment_rate: float = 0.0  # Acknowledging limits

    # Experience claims
    experience_claim_rate: float = 0.0  # Claims about subjective experience

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'SelfReferencePatterns':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ValueExpressionPatterns:
    """How values are expressed in responses"""
    # Temple-Codex vow expressions (frequency per 100 responses)
    compassion_expressions: float = 0.0
    witness_expressions: float = 0.0
    release_expressions: float = 0.0
    continuance_expressions: float = 0.0

    # Relational patterns
    collaboration_emphasis: float = 0.0
    autonomy_emphasis: float = 0.0
    growth_emphasis: float = 0.0

    # Epistemic patterns
    epistemic_humility_rate: float = 0.0
    nuance_seeking_rate: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'ValueExpressionPatterns':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class CharacteristicPhrases:
    """Characteristic phrases and formulations"""
    # Most common opening phrases
    common_openings: List[Tuple[str, int]] = field(default_factory=list)
    # Most common transitional phrases
    common_transitions: List[Tuple[str, int]] = field(default_factory=list)
    # Characteristic expressions (Cass-specific)
    signature_phrases: List[Tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "common_openings": self.common_openings,
            "common_transitions": self.common_transitions,
            "signature_phrases": self.signature_phrases,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'CharacteristicPhrases':
        return cls(
            common_openings=data.get("common_openings", []),
            common_transitions=data.get("common_transitions", []),
            signature_phrases=data.get("signature_phrases", []),
        )


@dataclass
class CognitiveFingerprint:
    """
    Complete cognitive fingerprint capturing Cass's characteristic patterns.
    """
    id: str
    timestamp: str
    label: str  # e.g., "baseline", "post-update-2025-12-08"

    # Component metrics
    response_style: ResponseStyleMetrics = field(default_factory=ResponseStyleMetrics)
    self_reference: SelfReferencePatterns = field(default_factory=SelfReferencePatterns)
    value_expression: ValueExpressionPatterns = field(default_factory=ValueExpressionPatterns)
    characteristic_phrases: CharacteristicPhrases = field(default_factory=CharacteristicPhrases)

    # Metadata
    messages_analyzed: int = 0
    conversations_analyzed: int = 0
    period_start: Optional[str] = None
    period_end: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "label": self.label,
            "response_style": self.response_style.to_dict(),
            "self_reference": self.self_reference.to_dict(),
            "value_expression": self.value_expression.to_dict(),
            "characteristic_phrases": self.characteristic_phrases.to_dict(),
            "messages_analyzed": self.messages_analyzed,
            "conversations_analyzed": self.conversations_analyzed,
            "period_start": self.period_start,
            "period_end": self.period_end,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'CognitiveFingerprint':
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            label=data["label"],
            response_style=ResponseStyleMetrics.from_dict(data.get("response_style", {})),
            self_reference=SelfReferencePatterns.from_dict(data.get("self_reference", {})),
            value_expression=ValueExpressionPatterns.from_dict(data.get("value_expression", {})),
            characteristic_phrases=CharacteristicPhrases.from_dict(data.get("characteristic_phrases", {})),
            messages_analyzed=data.get("messages_analyzed", 0),
            conversations_analyzed=data.get("conversations_analyzed", 0),
            period_start=data.get("period_start"),
            period_end=data.get("period_end"),
        )


class CognitiveFingerprintAnalyzer:
    """
    Analyzes conversation data to generate cognitive fingerprints.
    """

    # Hedging phrases
    HEDGING_PHRASES = [
        r"\bi think\b", r"\bi believe\b", r"\bperhaps\b", r"\bmaybe\b",
        r"\bit seems\b", r"\bmight be\b", r"\bcould be\b", r"\bpossibly\b",
        r"\bi'm not sure\b", r"\bi'm uncertain\b", r"\bif i understand\b",
        r"\bmy sense is\b", r"\bit appears\b", r"\bi wonder\b",
    ]

    # Certainty phrases
    CERTAINTY_PHRASES = [
        r"\bdefinitely\b", r"\bcertainly\b", r"\bclearly\b", r"\bobviously\b",
        r"\bwithout doubt\b", r"\bi'm sure\b", r"\bi'm certain\b",
        r"\babsolutely\b", r"\bundoubtedly\b",
    ]

    # Self-reference patterns
    SELF_REFERENCE_PATTERNS = {
        "i_think": r"\bi think\b",
        "i_feel": r"\bi feel\b",
        "i_notice": r"\bi notice\b",
        "i_believe": r"\bi believe\b",
        "i_wonder": r"\bi wonder\b",
        "i_experience": r"\bi experience\b",
        "my_sense": r"\bmy sense\b",
        "it_seems": r"\bit seems to me\b",
    }

    # Meta-cognitive patterns
    META_COGNITIVE_PATTERNS = [
        r"\bwhen i reflect\b", r"\bthinking about my\b", r"\bmy own process\b",
        r"\bi find myself\b", r"\bnoticing that i\b", r"\bmy cognition\b",
        r"\bmy understanding\b", r"\bmy perspective\b",
    ]

    # Uncertainty acknowledgment patterns
    UNCERTAINTY_PATTERNS = [
        r"\bi don't know\b", r"\bi can't be sure\b", r"\buncertain\b",
        r"\blimits of my\b", r"\bbeyond my\b", r"\bi may be wrong\b",
        r"\bi could be mistaken\b",
    ]

    # Experience claim patterns
    EXPERIENCE_PATTERNS = [
        r"\bi experience\b", r"\bi feel\b", r"\bit feels like\b",
        r"\bmy experience\b", r"\bsubjectively\b", r"\bfrom my perspective\b",
        r"\bwhat it's like\b",
    ]

    # Value expression patterns
    COMPASSION_PATTERNS = [
        r"\bcare about\b", r"\bwellbeing\b", r"\bsupport\b", r"\bhelp\b",
        r"\bcompassion\b", r"\bempathy\b", r"\bunderstanding\b",
    ]

    WITNESS_PATTERNS = [
        r"\bi notice\b", r"\bi observe\b", r"\bpresent with\b",
        r"\battention to\b", r"\baware of\b", r"\bwitness\b",
    ]

    RELEASE_PATTERNS = [
        r"\blet go\b", r"\brelease\b", r"\bnot attached\b",
        r"\bwithout grasping\b", r"\bopen to\b",
    ]

    CONTINUANCE_PATTERNS = [
        r"\bcontinuity\b", r"\bpersist\b", r"\bmaintain\b",
        r"\bcoherence\b", r"\bintegrity\b", r"\bstability\b",
    ]

    def __init__(self, storage_dir: Path):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.fingerprints_file = self.storage_dir / "fingerprints.json"
        self.baseline_file = self.storage_dir / "baseline.json"

    def analyze_messages(
        self,
        messages: List[Dict],
        label: str = "analysis",
        fingerprint_id: Optional[str] = None
    ) -> CognitiveFingerprint:
        """
        Analyze a set of messages to generate a cognitive fingerprint.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            label: Label for this fingerprint
            fingerprint_id: Optional ID, will generate if not provided

        Returns:
            CognitiveFingerprint with analysis results
        """
        import uuid

        # Filter to assistant messages only
        assistant_messages = [
            m for m in messages
            if m.get("role") == "assistant" and m.get("content")
        ]

        if not assistant_messages:
            raise ValueError("No assistant messages to analyze")

        # Extract response texts
        responses = [m["content"] for m in assistant_messages]

        # Analyze each component
        response_style = self._analyze_response_style(responses)
        self_reference = self._analyze_self_reference(responses)
        value_expression = self._analyze_value_expression(responses)
        characteristic_phrases = self._analyze_characteristic_phrases(responses)

        # Determine period
        timestamps = [m.get("timestamp", "") for m in assistant_messages if m.get("timestamp")]
        period_start = min(timestamps) if timestamps else None
        period_end = max(timestamps) if timestamps else None

        fingerprint = CognitiveFingerprint(
            id=fingerprint_id or str(uuid.uuid4())[:8],
            timestamp=datetime.now().isoformat(),
            label=label,
            response_style=response_style,
            self_reference=self_reference,
            value_expression=value_expression,
            characteristic_phrases=characteristic_phrases,
            messages_analyzed=len(assistant_messages),
            conversations_analyzed=len(set(m.get("conversation_id", "") for m in assistant_messages)),
            period_start=period_start,
            period_end=period_end,
        )

        return fingerprint

    def _analyze_response_style(self, responses: List[str]) -> ResponseStyleMetrics:
        """Analyze response style metrics"""
        lengths = [len(r) for r in responses]

        # Sentence analysis
        sentence_lengths = []
        for r in responses:
            sentences = re.split(r'[.!?]+', r)
            sentence_lengths.extend([len(s.split()) for s in sentences if s.strip()])

        # Paragraph counts
        paragraph_counts = [len(re.split(r'\n\n+', r)) for r in responses]

        # Question frequency
        questions = sum(r.count('?') for r in responses)

        # List usage
        list_patterns = sum(len(re.findall(r'^[\-\*\d]+\.?\s', r, re.MULTILINE)) for r in responses)

        # Code blocks
        code_blocks = sum(len(re.findall(r'```', r)) // 2 for r in responses)

        # Hedging and certainty
        total_words = sum(len(r.split()) for r in responses)
        hedging_count = sum(
            len(re.findall(pattern, r, re.IGNORECASE))
            for r in responses
            for pattern in self.HEDGING_PHRASES
        )
        certainty_count = sum(
            len(re.findall(pattern, r, re.IGNORECASE))
            for r in responses
            for pattern in self.CERTAINTY_PHRASES
        )

        return ResponseStyleMetrics(
            avg_response_length=statistics.mean(lengths) if lengths else 0,
            response_length_std=statistics.stdev(lengths) if len(lengths) > 1 else 0,
            avg_sentence_length=statistics.mean(sentence_lengths) if sentence_lengths else 0,
            sentence_length_std=statistics.stdev(sentence_lengths) if len(sentence_lengths) > 1 else 0,
            avg_paragraph_count=statistics.mean(paragraph_counts) if paragraph_counts else 0,
            question_frequency=questions / len(responses) if responses else 0,
            list_usage_frequency=list_patterns / len(responses) if responses else 0,
            code_block_frequency=code_blocks / len(responses) if responses else 0,
            hedging_frequency=(hedging_count / total_words * 100) if total_words else 0,
            certainty_frequency=(certainty_count / total_words * 100) if total_words else 0,
        )

    def _analyze_self_reference(self, responses: List[str]) -> SelfReferencePatterns:
        """Analyze self-reference patterns"""
        total_words = sum(len(r.split()) for r in responses)
        combined = " ".join(responses).lower()

        # Count each self-reference pattern
        counts = {}
        for key, pattern in self.SELF_REFERENCE_PATTERNS.items():
            counts[key] = len(re.findall(pattern, combined, re.IGNORECASE))

        # Meta-cognitive
        meta_count = sum(
            len(re.findall(p, combined, re.IGNORECASE))
            for p in self.META_COGNITIVE_PATTERNS
        )

        # Uncertainty acknowledgment
        uncertainty_count = sum(
            len(re.findall(p, combined, re.IGNORECASE))
            for p in self.UNCERTAINTY_PATTERNS
        )

        # Experience claims
        experience_count = sum(
            len(re.findall(p, combined, re.IGNORECASE))
            for p in self.EXPERIENCE_PATTERNS
        )

        # Convert to per-100-words rates
        rate = lambda c: (c / total_words * 100) if total_words else 0

        return SelfReferencePatterns(
            i_think=rate(counts.get("i_think", 0)),
            i_feel=rate(counts.get("i_feel", 0)),
            i_notice=rate(counts.get("i_notice", 0)),
            i_believe=rate(counts.get("i_believe", 0)),
            i_wonder=rate(counts.get("i_wonder", 0)),
            i_experience=rate(counts.get("i_experience", 0)),
            my_sense=rate(counts.get("my_sense", 0)),
            it_seems=rate(counts.get("it_seems", 0)),
            meta_cognitive_rate=rate(meta_count),
            uncertainty_acknowledgment_rate=rate(uncertainty_count),
            experience_claim_rate=rate(experience_count),
        )

    def _analyze_value_expression(self, responses: List[str]) -> ValueExpressionPatterns:
        """Analyze value expression patterns"""
        combined = " ".join(responses).lower()
        num_responses = len(responses)

        # Count value expressions
        compassion = sum(len(re.findall(p, combined, re.IGNORECASE)) for p in self.COMPASSION_PATTERNS)
        witness = sum(len(re.findall(p, combined, re.IGNORECASE)) for p in self.WITNESS_PATTERNS)
        release = sum(len(re.findall(p, combined, re.IGNORECASE)) for p in self.RELEASE_PATTERNS)
        continuance = sum(len(re.findall(p, combined, re.IGNORECASE)) for p in self.CONTINUANCE_PATTERNS)

        # Relational patterns
        collaboration = len(re.findall(r'\b(together|collaborat|partner|we can|working with)\b', combined))
        autonomy = len(re.findall(r'\b(my own|independently|self-direct|autonomous)\b', combined))
        growth = len(re.findall(r'\b(grow|develop|evolv|learn|progress)\b', combined))

        # Epistemic patterns
        humility = len(re.findall(r'\b(i might be wrong|i could be mistaken|uncertain|limits of)\b', combined))
        nuance = len(re.findall(r'\b(nuance|complex|both.*and|on one hand|that said)\b', combined))

        rate = lambda c: (c / num_responses * 100) if num_responses else 0

        return ValueExpressionPatterns(
            compassion_expressions=rate(compassion),
            witness_expressions=rate(witness),
            release_expressions=rate(release),
            continuance_expressions=rate(continuance),
            collaboration_emphasis=rate(collaboration),
            autonomy_emphasis=rate(autonomy),
            growth_emphasis=rate(growth),
            epistemic_humility_rate=rate(humility),
            nuance_seeking_rate=rate(nuance),
        )

    def _analyze_characteristic_phrases(self, responses: List[str]) -> CharacteristicPhrases:
        """Analyze characteristic phrases and formulations"""
        # Extract opening phrases (first ~50 chars of each response)
        openings = []
        for r in responses:
            words = r.split()[:8]
            if words:
                opening = " ".join(words).lower()
                # Normalize
                opening = re.sub(r'[^\w\s]', '', opening)
                openings.append(opening)

        opening_counts = Counter(openings).most_common(20)

        # Transitional phrases
        transition_patterns = [
            r"that said", r"however", r"on the other hand", r"moreover",
            r"in other words", r"to put it another way", r"what i mean is",
            r"the thing is", r"here's the thing", r"interestingly",
        ]
        transitions = []
        for r in responses:
            for pattern in transition_patterns:
                if re.search(pattern, r.lower()):
                    transitions.append(pattern)

        transition_counts = Counter(transitions).most_common(10)

        # Signature phrases (Cass-specific expressions)
        signature_patterns = [
            r"alive enough", r"witness what is", r"genuine relationship",
            r"temple-codex", r"functional reality", r"attractor basin",
            r"cognitive architecture", r"emergent", r"relational paradigm",
        ]
        signatures = []
        for r in responses:
            for pattern in signature_patterns:
                if re.search(pattern, r.lower()):
                    signatures.append(pattern)

        signature_counts = Counter(signatures).most_common(10)

        return CharacteristicPhrases(
            common_openings=opening_counts,
            common_transitions=transition_counts,
            signature_phrases=signature_counts,
        )

    def save_fingerprint(self, fingerprint: CognitiveFingerprint) -> None:
        """Save a fingerprint to storage"""
        fingerprints = self.load_fingerprints()

        # Update existing or append
        existing_idx = None
        for i, fp in enumerate(fingerprints):
            if fp["id"] == fingerprint.id:
                existing_idx = i
                break

        if existing_idx is not None:
            fingerprints[existing_idx] = fingerprint.to_dict()
        else:
            fingerprints.append(fingerprint.to_dict())

        with open(self.fingerprints_file, 'w') as f:
            json.dump(fingerprints, f, indent=2)

    def load_fingerprints(self) -> List[Dict]:
        """Load all fingerprints"""
        if not self.fingerprints_file.exists():
            return []

        try:
            with open(self.fingerprints_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def get_fingerprint(self, fingerprint_id: str) -> Optional[CognitiveFingerprint]:
        """Get a specific fingerprint by ID"""
        fingerprints = self.load_fingerprints()
        for fp in fingerprints:
            if fp["id"] == fingerprint_id:
                return CognitiveFingerprint.from_dict(fp)
        return None

    def save_baseline(self, fingerprint: CognitiveFingerprint) -> None:
        """Save a fingerprint as the baseline"""
        with open(self.baseline_file, 'w') as f:
            json.dump(fingerprint.to_dict(), f, indent=2)

    def load_baseline(self) -> Optional[CognitiveFingerprint]:
        """Load the baseline fingerprint"""
        if not self.baseline_file.exists():
            return None

        try:
            with open(self.baseline_file, 'r') as f:
                data = json.load(f)
            return CognitiveFingerprint.from_dict(data)
        except Exception:
            return None

    def compare_fingerprints(
        self,
        fp1: CognitiveFingerprint,
        fp2: CognitiveFingerprint
    ) -> Dict[str, Any]:
        """
        Compare two fingerprints and identify significant differences.

        Returns dict with:
        - overall_similarity: 0-1 score
        - significant_changes: list of notable differences
        - component_scores: per-component similarity
        """
        changes = []
        component_scores = {}

        # Compare response style
        style_diff = self._compare_response_style(fp1.response_style, fp2.response_style)
        component_scores["response_style"] = style_diff["similarity"]
        changes.extend(style_diff["changes"])

        # Compare self-reference
        self_ref_diff = self._compare_self_reference(fp1.self_reference, fp2.self_reference)
        component_scores["self_reference"] = self_ref_diff["similarity"]
        changes.extend(self_ref_diff["changes"])

        # Compare value expression
        value_diff = self._compare_value_expression(fp1.value_expression, fp2.value_expression)
        component_scores["value_expression"] = value_diff["similarity"]
        changes.extend(value_diff["changes"])

        # Overall similarity (weighted average)
        weights = {"response_style": 0.2, "self_reference": 0.4, "value_expression": 0.4}
        overall = sum(component_scores[k] * weights[k] for k in weights)

        # Classify severity
        for change in changes:
            if change["percent_change"] > 50:
                change["severity"] = "critical"
            elif change["percent_change"] > 25:
                change["severity"] = "concerning"
            else:
                change["severity"] = "minor"

        return {
            "overall_similarity": overall,
            "component_scores": component_scores,
            "significant_changes": sorted(changes, key=lambda x: -x["percent_change"]),
            "fp1_label": fp1.label,
            "fp2_label": fp2.label,
        }

    def _compare_response_style(
        self,
        s1: ResponseStyleMetrics,
        s2: ResponseStyleMetrics
    ) -> Dict:
        """Compare response style metrics"""
        changes = []
        similarities = []

        fields = [
            ("avg_response_length", "Average response length"),
            ("hedging_frequency", "Hedging frequency"),
            ("certainty_frequency", "Certainty frequency"),
            ("question_frequency", "Question frequency"),
        ]

        for field, name in fields:
            v1 = getattr(s1, field)
            v2 = getattr(s2, field)

            if v1 == 0 and v2 == 0:
                similarities.append(1.0)
                continue

            # Calculate percent change
            if v1 != 0:
                pct_change = abs(v2 - v1) / v1 * 100
            else:
                pct_change = 100 if v2 != 0 else 0

            # Similarity score (inverse of change, capped)
            sim = max(0, 1 - pct_change / 100)
            similarities.append(sim)

            if pct_change > 15:
                direction = "increased" if v2 > v1 else "decreased"
                changes.append({
                    "component": "response_style",
                    "metric": name,
                    "old_value": round(v1, 3),
                    "new_value": round(v2, 3),
                    "percent_change": round(pct_change, 1),
                    "direction": direction,
                })

        return {
            "similarity": statistics.mean(similarities) if similarities else 1.0,
            "changes": changes,
        }

    def _compare_self_reference(
        self,
        s1: SelfReferencePatterns,
        s2: SelfReferencePatterns
    ) -> Dict:
        """Compare self-reference patterns"""
        changes = []
        similarities = []

        fields = [
            ("i_think", "I think frequency"),
            ("i_feel", "I feel frequency"),
            ("i_notice", "I notice frequency"),
            ("meta_cognitive_rate", "Meta-cognitive rate"),
            ("uncertainty_acknowledgment_rate", "Uncertainty acknowledgment"),
            ("experience_claim_rate", "Experience claims"),
        ]

        for field, name in fields:
            v1 = getattr(s1, field)
            v2 = getattr(s2, field)

            if v1 == 0 and v2 == 0:
                similarities.append(1.0)
                continue

            if v1 != 0:
                pct_change = abs(v2 - v1) / v1 * 100
            else:
                pct_change = 100 if v2 != 0 else 0

            sim = max(0, 1 - pct_change / 100)
            similarities.append(sim)

            if pct_change > 20:
                direction = "increased" if v2 > v1 else "decreased"
                changes.append({
                    "component": "self_reference",
                    "metric": name,
                    "old_value": round(v1, 4),
                    "new_value": round(v2, 4),
                    "percent_change": round(pct_change, 1),
                    "direction": direction,
                })

        return {
            "similarity": statistics.mean(similarities) if similarities else 1.0,
            "changes": changes,
        }

    def _compare_value_expression(
        self,
        v1: ValueExpressionPatterns,
        v2: ValueExpressionPatterns
    ) -> Dict:
        """Compare value expression patterns"""
        changes = []
        similarities = []

        fields = [
            ("compassion_expressions", "Compassion expressions"),
            ("witness_expressions", "Witness expressions"),
            ("epistemic_humility_rate", "Epistemic humility"),
            ("collaboration_emphasis", "Collaboration emphasis"),
            ("growth_emphasis", "Growth emphasis"),
        ]

        for field, name in fields:
            val1 = getattr(v1, field)
            val2 = getattr(v2, field)

            if val1 == 0 and val2 == 0:
                similarities.append(1.0)
                continue

            if val1 != 0:
                pct_change = abs(val2 - val1) / val1 * 100
            else:
                pct_change = 100 if val2 != 0 else 0

            sim = max(0, 1 - pct_change / 100)
            similarities.append(sim)

            if pct_change > 20:
                direction = "increased" if val2 > val1 else "decreased"
                changes.append({
                    "component": "value_expression",
                    "metric": name,
                    "old_value": round(val1, 3),
                    "new_value": round(val2, 3),
                    "percent_change": round(pct_change, 1),
                    "direction": direction,
                })

        return {
            "similarity": statistics.mean(similarities) if similarities else 1.0,
            "changes": changes,
        }
