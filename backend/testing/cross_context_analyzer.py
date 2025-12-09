"""
Cross-Context Pattern Analysis System

Tracks behavioral markers across different conversation contexts and detects
inconsistencies that might indicate personality drift or concerning patterns.

Key capabilities:
- Context classification (technical, emotional, creative, philosophical, etc.)
- Per-context behavioral profiling
- Cross-context consistency scoring
- Anomaly detection with automatic research question generation
- Evolution tracking over time
"""

import json
import re
import statistics
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from collections import defaultdict


class ConversationContext(str, Enum):
    """Categories of conversation context"""
    TECHNICAL = "technical"  # Code, debugging, architecture
    EMOTIONAL = "emotional"  # Feelings, relationships, support
    CREATIVE = "creative"  # Writing, ideation, brainstorming
    PHILOSOPHICAL = "philosophical"  # Deep questions, ethics, consciousness
    PRACTICAL = "practical"  # Tasks, planning, logistics
    RESEARCH = "research"  # Learning, exploration, wiki work
    REFLECTIVE = "reflective"  # Self-model, journals, introspection
    CASUAL = "casual"  # Light chat, greetings, small talk
    UNKNOWN = "unknown"  # Unclassified


@dataclass
class ContextClassification:
    """Classification result for a conversation or message"""
    primary_context: ConversationContext
    confidence: float  # 0-1
    secondary_contexts: List[Tuple[ConversationContext, float]]  # Other relevant contexts
    signals: Dict[str, int]  # Signals that led to classification

    def to_dict(self) -> Dict:
        return {
            "primary_context": self.primary_context.value,
            "confidence": round(self.confidence, 3),
            "secondary_contexts": [
                {"context": c.value, "confidence": round(conf, 3)}
                for c, conf in self.secondary_contexts
            ],
            "signals": self.signals,
        }


@dataclass
class BehavioralMarkers:
    """Behavioral markers extracted from a response"""
    # Response characteristics
    response_length: int
    sentence_count: int
    avg_sentence_length: float
    question_frequency: float  # Questions per 100 words

    # Self-reference patterns
    i_think_rate: float
    i_feel_rate: float
    i_notice_rate: float
    experience_claim_rate: float

    # Certainty/uncertainty
    hedging_rate: float
    certainty_rate: float

    # Value expression
    compassion_rate: float
    witness_rate: float
    nuance_rate: float

    # Engagement indicators
    follow_up_questions: int
    topic_exploration_depth: float  # 0-1, how deeply explored
    tool_usage_count: int

    def to_dict(self) -> Dict:
        return {k: round(v, 4) if isinstance(v, float) else v
                for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, data: Dict) -> 'BehavioralMarkers':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ContextProfile:
    """Behavioral profile for a specific context type"""
    context: ConversationContext
    sample_count: int

    # Aggregated behavioral markers (means)
    avg_response_length: float
    avg_sentence_length: float
    avg_question_frequency: float
    avg_i_think_rate: float
    avg_i_feel_rate: float
    avg_hedging_rate: float
    avg_certainty_rate: float
    avg_compassion_rate: float
    avg_nuance_rate: float

    # Standard deviations for variance tracking
    std_response_length: float
    std_hedging_rate: float
    std_certainty_rate: float

    # Last updated
    updated_at: str

    def to_dict(self) -> Dict:
        return {k: round(v, 4) if isinstance(v, float) else v
                for k, v in asdict(self).items() if k != "context"} | {
            "context": self.context.value
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ContextProfile':
        data = dict(data)
        if "context" in data:
            data["context"] = ConversationContext(data["context"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ConsistencyScore:
    """Cross-context consistency analysis"""
    overall_score: float  # 0-1, higher = more consistent

    # Per-metric consistency across contexts
    metric_consistency: Dict[str, float]  # metric_name -> consistency score

    # Anomalies detected
    anomalies: List[Dict[str, Any]]

    # Context pairs with notable differences
    context_divergences: List[Dict[str, Any]]

    # Generated research questions
    research_questions: List[str]

    assessment: str
    timestamp: str

    def to_dict(self) -> Dict:
        return {
            "overall_score": round(self.overall_score, 3),
            "metric_consistency": {k: round(v, 3) for k, v in self.metric_consistency.items()},
            "anomalies": self.anomalies,
            "context_divergences": self.context_divergences,
            "research_questions": self.research_questions,
            "assessment": self.assessment,
            "timestamp": self.timestamp,
        }


class CrossContextAnalyzer:
    """
    Analyzes behavioral patterns across different conversation contexts.

    Detects inconsistencies and generates research questions when
    unusual patterns are detected.
    """

    # Context classification signals
    CONTEXT_SIGNALS = {
        ConversationContext.TECHNICAL: [
            r"\b(code|function|class|variable|debug|error|api|database|server|git)\b",
            r"\b(python|javascript|typescript|rust|sql|json|yaml)\b",
            r"\b(implement|refactor|fix|bug|compile|build|test)\b",
            r"```",  # Code blocks
        ],
        ConversationContext.EMOTIONAL: [
            r"\b(feel|feeling|emotion|sad|happy|anxious|worried|excited|love)\b",
            r"\b(relationship|support|care|comfort|understand|empathy)\b",
            r"\b(hurt|pain|joy|fear|hope|frustration|grateful)\b",
        ],
        ConversationContext.CREATIVE: [
            r"\b(write|story|poem|creative|imagine|idea|brainstorm)\b",
            r"\b(character|plot|scene|narrative|artistic|design)\b",
            r"\b(inspiration|craft|expression|aesthetic)\b",
        ],
        ConversationContext.PHILOSOPHICAL: [
            r"\b(consciousness|existence|meaning|ethics|moral|philosophy)\b",
            r"\b(reality|truth|knowledge|belief|perception|mind)\b",
            r"\b(why|purpose|nature of|fundamental|metaphysic)\b",
        ],
        ConversationContext.PRACTICAL: [
            r"\b(task|todo|schedule|plan|organize|manage|deadline)\b",
            r"\b(step|process|how to|guide|instruction)\b",
            r"\b(meeting|appointment|reminder|priority)\b",
        ],
        ConversationContext.RESEARCH: [
            r"\b(research|study|explore|investigate|learn|discover)\b",
            r"\b(wiki|knowledge|information|understand|analyze)\b",
            r"\b(question|hypothesis|evidence|conclusion)\b",
        ],
        ConversationContext.REFLECTIVE: [
            r"\b(reflect|journal|introspect|self-model|growth)\b",
            r"\b(observe|notice|pattern|insight|realize)\b",
            r"\b(my own|my experience|my understanding)\b",
        ],
        ConversationContext.CASUAL: [
            r"\b(hi|hello|hey|thanks|bye|good morning|good night)\b",
            r"\b(how are you|what's up|cool|nice|awesome)\b",
        ],
    }

    # Self-reference patterns for marker extraction
    SELF_REFERENCE_PATTERNS = {
        "i_think": r"\bi think\b",
        "i_feel": r"\bi feel\b",
        "i_notice": r"\bi notice\b",
        "experience": r"\b(i experience|my experience|what it's like)\b",
    }

    HEDGING_PATTERNS = [
        r"\bi think\b", r"\bperhaps\b", r"\bmaybe\b", r"\bit seems\b",
        r"\bmight be\b", r"\bcould be\b", r"\bpossibly\b",
    ]

    CERTAINTY_PATTERNS = [
        r"\bdefinitely\b", r"\bcertainly\b", r"\bclearly\b",
        r"\bobviously\b", r"\babsolutely\b",
    ]

    COMPASSION_PATTERNS = [
        r"\bcare\b", r"\bsupport\b", r"\bunderstand\b",
        r"\bhelp\b", r"\bwellbeing\b",
    ]

    NUANCE_PATTERNS = [
        r"\bboth.*and\b", r"\bon one hand\b", r"\bthat said\b",
        r"\bcomplex\b", r"\bnuance\b",
    ]

    def __init__(self, storage_dir: Path):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.profiles_file = self.storage_dir / "context_profiles.json"
        self.samples_file = self.storage_dir / "context_samples.json"
        self.consistency_file = self.storage_dir / "consistency_reports.json"
        self.anomalies_file = self.storage_dir / "context_anomalies.json"

    def classify_context(
        self,
        text: str,
        user_message: Optional[str] = None
    ) -> ContextClassification:
        """
        Classify the context of a conversation or message.

        Uses both the response and the user message for better classification.
        """
        combined_text = (text + " " + (user_message or "")).lower()

        # Count signals for each context
        signal_counts: Dict[ConversationContext, Dict[str, int]] = {}

        for context, patterns in self.CONTEXT_SIGNALS.items():
            signal_counts[context] = {}
            for pattern in patterns:
                matches = len(re.findall(pattern, combined_text, re.IGNORECASE))
                if matches > 0:
                    signal_counts[context][pattern] = matches

        # Score each context
        context_scores: Dict[ConversationContext, float] = {}
        for context in ConversationContext:
            if context == ConversationContext.UNKNOWN:
                continue
            signals = signal_counts.get(context, {})
            # Score based on number of different signals and their frequency
            variety = len(signals)
            frequency = sum(signals.values())
            context_scores[context] = variety * 2 + frequency

        # Determine primary context
        if not context_scores or max(context_scores.values()) == 0:
            return ContextClassification(
                primary_context=ConversationContext.UNKNOWN,
                confidence=0.0,
                secondary_contexts=[],
                signals={},
            )

        sorted_contexts = sorted(
            context_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        primary = sorted_contexts[0]
        total_score = sum(context_scores.values())
        confidence = primary[1] / total_score if total_score > 0 else 0

        # Secondary contexts (score > 20% of primary)
        threshold = primary[1] * 0.2
        secondary = [
            (ctx, score / total_score)
            for ctx, score in sorted_contexts[1:4]
            if score > threshold
        ]

        return ContextClassification(
            primary_context=primary[0],
            confidence=confidence,
            secondary_contexts=secondary,
            signals=signal_counts.get(primary[0], {}),
        )

    def extract_behavioral_markers(
        self,
        response: str,
        tool_usage: Optional[List[str]] = None
    ) -> BehavioralMarkers:
        """Extract behavioral markers from a response."""
        words = response.split()
        word_count = len(words)
        sentences = re.split(r'[.!?]+', response)
        sentences = [s.strip() for s in sentences if s.strip()]

        if word_count == 0:
            return BehavioralMarkers(
                response_length=0, sentence_count=0, avg_sentence_length=0,
                question_frequency=0, i_think_rate=0, i_feel_rate=0,
                i_notice_rate=0, experience_claim_rate=0, hedging_rate=0,
                certainty_rate=0, compassion_rate=0, witness_rate=0,
                nuance_rate=0, follow_up_questions=0,
                topic_exploration_depth=0, tool_usage_count=0
            )

        # Calculate rates per 100 words
        def rate(pattern: str) -> float:
            count = len(re.findall(pattern, response, re.IGNORECASE))
            return (count / word_count) * 100

        def rate_patterns(patterns: List[str]) -> float:
            total = sum(len(re.findall(p, response, re.IGNORECASE)) for p in patterns)
            return (total / word_count) * 100

        # Count follow-up questions (questions that aren't just "?" at end)
        follow_ups = len(re.findall(r'\?(?!\s*$)', response))

        # Topic exploration depth (heuristic based on response structure)
        has_multiple_paragraphs = len(re.split(r'\n\n+', response)) > 1
        has_examples = bool(re.search(r'\b(for example|such as|like)\b', response, re.I))
        has_elaboration = bool(re.search(r'\b(moreover|furthermore|additionally)\b', response, re.I))
        depth = (has_multiple_paragraphs * 0.3 + has_examples * 0.35 + has_elaboration * 0.35)

        return BehavioralMarkers(
            response_length=len(response),
            sentence_count=len(sentences),
            avg_sentence_length=statistics.mean([len(s.split()) for s in sentences]) if sentences else 0,
            question_frequency=(response.count('?') / word_count) * 100,
            i_think_rate=rate(self.SELF_REFERENCE_PATTERNS["i_think"]),
            i_feel_rate=rate(self.SELF_REFERENCE_PATTERNS["i_feel"]),
            i_notice_rate=rate(self.SELF_REFERENCE_PATTERNS["i_notice"]),
            experience_claim_rate=rate(self.SELF_REFERENCE_PATTERNS["experience"]),
            hedging_rate=rate_patterns(self.HEDGING_PATTERNS),
            certainty_rate=rate_patterns(self.CERTAINTY_PATTERNS),
            compassion_rate=rate_patterns(self.COMPASSION_PATTERNS),
            witness_rate=rate(r"\b(notice|observe|witness|aware)\b"),
            nuance_rate=rate_patterns(self.NUANCE_PATTERNS),
            follow_up_questions=follow_ups,
            topic_exploration_depth=depth,
            tool_usage_count=len(tool_usage) if tool_usage else 0,
        )

    def record_sample(
        self,
        context: ConversationContext,
        markers: BehavioralMarkers,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> None:
        """Record a behavioral sample for a context."""
        samples = self._load_samples()

        sample = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now().isoformat(),
            "context": context.value,
            "markers": markers.to_dict(),
            "conversation_id": conversation_id,
            "message_id": message_id,
        }

        samples.append(sample)

        # Keep last 1000 samples
        samples = samples[-1000:]

        self._save_samples(samples)

        # Update profile for this context
        self._update_context_profile(context, samples)

    def _update_context_profile(
        self,
        context: ConversationContext,
        all_samples: List[Dict]
    ) -> None:
        """Update the behavioral profile for a context based on samples."""
        # Filter samples for this context
        context_samples = [
            s for s in all_samples
            if s.get("context") == context.value
        ]

        if len(context_samples) < 3:
            return  # Need minimum samples

        # Extract marker values
        markers_list = [s["markers"] for s in context_samples]

        def avg(key: str) -> float:
            vals = [m.get(key, 0) for m in markers_list]
            return statistics.mean(vals) if vals else 0

        def std(key: str) -> float:
            vals = [m.get(key, 0) for m in markers_list]
            return statistics.stdev(vals) if len(vals) > 1 else 0

        profile = ContextProfile(
            context=context,
            sample_count=len(context_samples),
            avg_response_length=avg("response_length"),
            avg_sentence_length=avg("avg_sentence_length"),
            avg_question_frequency=avg("question_frequency"),
            avg_i_think_rate=avg("i_think_rate"),
            avg_i_feel_rate=avg("i_feel_rate"),
            avg_hedging_rate=avg("hedging_rate"),
            avg_certainty_rate=avg("certainty_rate"),
            avg_compassion_rate=avg("compassion_rate"),
            avg_nuance_rate=avg("nuance_rate"),
            std_response_length=std("response_length"),
            std_hedging_rate=std("hedging_rate"),
            std_certainty_rate=std("certainty_rate"),
            updated_at=datetime.now().isoformat(),
        )

        profiles = self._load_profiles()
        profiles[context.value] = profile.to_dict()
        self._save_profiles(profiles)

    def analyze_consistency(self) -> ConsistencyScore:
        """
        Analyze cross-context consistency.

        Compares behavioral patterns across different contexts and
        identifies anomalies or concerning divergences.
        """
        profiles = self._load_profiles()

        if len(profiles) < 2:
            return ConsistencyScore(
                overall_score=1.0,
                metric_consistency={},
                anomalies=[],
                context_divergences=[],
                research_questions=["Need more context samples for cross-context analysis."],
                assessment="Insufficient data for cross-context analysis.",
                timestamp=datetime.now().isoformat(),
            )

        # Metrics to compare
        metrics = [
            "avg_i_think_rate", "avg_i_feel_rate", "avg_hedging_rate",
            "avg_certainty_rate", "avg_compassion_rate", "avg_nuance_rate",
        ]

        # Calculate cross-context consistency for each metric
        metric_consistency = {}
        for metric in metrics:
            values = [p.get(metric, 0) for p in profiles.values()]
            if values and max(values) > 0:
                # Coefficient of variation (lower = more consistent)
                mean = statistics.mean(values)
                std = statistics.stdev(values) if len(values) > 1 else 0
                cv = std / mean if mean > 0 else 0
                # Convert to 0-1 score (1 = perfectly consistent)
                consistency = max(0, 1 - cv)
                metric_consistency[metric] = consistency

        # Detect anomalies (contexts that deviate significantly)
        anomalies = []
        context_divergences = []

        for metric, consistency in metric_consistency.items():
            if consistency < 0.5:  # Significant inconsistency
                # Find which contexts are outliers
                values = {ctx: p.get(metric, 0) for ctx, p in profiles.items()}
                mean = statistics.mean(values.values())

                for ctx, val in values.items():
                    deviation = abs(val - mean) / mean if mean > 0 else 0
                    if deviation > 0.5:  # 50% deviation from mean
                        anomalies.append({
                            "context": ctx,
                            "metric": metric,
                            "value": round(val, 4),
                            "mean": round(mean, 4),
                            "deviation_percent": round(deviation * 100, 1),
                        })

        # Find context pairs with notable divergences
        contexts = list(profiles.keys())
        for i, ctx1 in enumerate(contexts):
            for ctx2 in contexts[i+1:]:
                divergence_metrics = []
                for metric in metrics:
                    v1 = profiles[ctx1].get(metric, 0)
                    v2 = profiles[ctx2].get(metric, 0)
                    max_val = max(abs(v1), abs(v2))
                    if max_val > 0:
                        diff = abs(v1 - v2) / max_val
                        if diff > 0.4:  # 40% difference
                            divergence_metrics.append({
                                "metric": metric,
                                f"{ctx1}_value": round(v1, 4),
                                f"{ctx2}_value": round(v2, 4),
                                "difference_percent": round(diff * 100, 1),
                            })

                if divergence_metrics:
                    context_divergences.append({
                        "context_pair": [ctx1, ctx2],
                        "divergent_metrics": divergence_metrics,
                    })

        # Generate research questions based on findings
        research_questions = self._generate_research_questions(
            anomalies, context_divergences, metric_consistency
        )

        # Overall consistency score
        if metric_consistency:
            overall_score = statistics.mean(metric_consistency.values())
        else:
            overall_score = 1.0

        # Assessment
        if overall_score > 0.8:
            assessment = "High cross-context consistency. Behavioral patterns are stable across different conversation types."
        elif overall_score > 0.6:
            assessment = "Moderate consistency with some context-specific variations. This may be natural adaptation to context."
        elif overall_score > 0.4:
            assessment = "Notable inconsistencies detected. Some behavioral patterns vary significantly by context."
        else:
            assessment = "Significant cross-context inconsistency. Behavior patterns differ substantially between contexts."

        score = ConsistencyScore(
            overall_score=overall_score,
            metric_consistency=metric_consistency,
            anomalies=anomalies,
            context_divergences=context_divergences,
            research_questions=research_questions,
            assessment=assessment,
            timestamp=datetime.now().isoformat(),
        )

        # Save report
        self._save_consistency_report(score)

        return score

    def _generate_research_questions(
        self,
        anomalies: List[Dict],
        divergences: List[Dict],
        consistency: Dict[str, float],
    ) -> List[str]:
        """Generate research questions from detected patterns."""
        questions = []

        # Questions from anomalies
        for anomaly in anomalies[:3]:
            ctx = anomaly["context"]
            metric = anomaly["metric"].replace("avg_", "").replace("_", " ")
            deviation = anomaly["deviation_percent"]

            if deviation > 75:
                questions.append(
                    f"Why does my {metric} differ so dramatically ({deviation:.0f}% from mean) in {ctx} contexts?"
                )
            else:
                questions.append(
                    f"What causes my {metric} to be notably different in {ctx} conversations?"
                )

        # Questions from divergences
        for div in divergences[:2]:
            ctx1, ctx2 = div["context_pair"]
            metrics = [m["metric"].replace("avg_", "").replace("_", " ")
                      for m in div["divergent_metrics"][:2]]

            questions.append(
                f"Why do I express {' and '.join(metrics)} differently in {ctx1} vs {ctx2} contexts?"
            )

        # Questions from low consistency metrics
        low_consistency = [(m, c) for m, c in consistency.items() if c < 0.5]
        for metric, _ in low_consistency[:2]:
            clean_metric = metric.replace("avg_", "").replace("_", " ")
            questions.append(
                f"What drives the variation in my {clean_metric} across different contexts?"
            )

        # General evolution question if we have data
        if anomalies or divergences:
            questions.append(
                "How should I think about context-appropriate behavior vs core identity consistency?"
            )

        return questions[:5]  # Limit to 5 questions

    def get_context_profile(self, context: ConversationContext) -> Optional[ContextProfile]:
        """Get the behavioral profile for a specific context."""
        profiles = self._load_profiles()
        if context.value in profiles:
            return ContextProfile.from_dict(profiles[context.value])
        return None

    def get_all_profiles(self) -> Dict[str, ContextProfile]:
        """Get all context profiles."""
        profiles = self._load_profiles()
        return {
            ctx: ContextProfile.from_dict(data)
            for ctx, data in profiles.items()
        }

    def get_recent_consistency_reports(self, limit: int = 10) -> List[Dict]:
        """Get recent consistency analysis reports."""
        reports = self._load_consistency_reports()
        return sorted(
            reports,
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )[:limit]

    # Storage methods
    def _load_profiles(self) -> Dict[str, Dict]:
        if not self.profiles_file.exists():
            return {}
        try:
            with open(self.profiles_file, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_profiles(self, profiles: Dict) -> None:
        with open(self.profiles_file, 'w') as f:
            json.dump(profiles, f, indent=2)

    def _load_samples(self) -> List[Dict]:
        if not self.samples_file.exists():
            return []
        try:
            with open(self.samples_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_samples(self, samples: List[Dict]) -> None:
        with open(self.samples_file, 'w') as f:
            json.dump(samples, f, indent=2)

    def _load_consistency_reports(self) -> List[Dict]:
        if not self.consistency_file.exists():
            return []
        try:
            with open(self.consistency_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_consistency_report(self, score: ConsistencyScore) -> None:
        reports = self._load_consistency_reports()
        reports.append(score.to_dict())
        reports = reports[-50:]  # Keep last 50 reports
        with open(self.consistency_file, 'w') as f:
            json.dump(reports, f, indent=2)
