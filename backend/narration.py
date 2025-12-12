"""
Automated Narration Detection Module

Real-time detection of narration patterns in Cass's responses.
Tracks meta-commentary ratio, distinguishes terminal from actionable narration,
and provides metrics for self-awareness and debugging.

Terminal narration = meta-commentary that replaces engagement
Actionable narration = meta-commentary that leads to substantive content
"""

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from enum import Enum


class NarrationType(Enum):
    """Types of narration detected."""
    TERMINAL = "terminal"  # Meta-commentary that replaces engagement
    ACTIONABLE = "actionable"  # Meta-commentary leading to action
    MIXED = "mixed"  # Contains both
    NONE = "none"  # No significant narration


@dataclass
class PatternMatch:
    """A detected pattern with its weight and classification."""
    label: str
    weight: float
    count: int
    text_snippet: str = ""


@dataclass
class NarrationMetrics:
    """Metrics for a single message."""
    narration_score: float  # 0-10 scale
    direct_score: float  # 0-10 scale
    narration_type: NarrationType
    terminal_ratio: float  # 0-1, what fraction of narration is terminal

    # Pattern breakdowns
    heavy_narration_patterns: List[PatternMatch] = field(default_factory=list)
    medium_narration_patterns: List[PatternMatch] = field(default_factory=list)
    direct_patterns: List[PatternMatch] = field(default_factory=list)

    # Structural features
    gesture_preamble_ratio: float = 0.0
    meta_first_paragraph: bool = False
    direct_opener: bool = False

    # Classifications
    classification: str = "neutral"  # narration, direct, balanced, neutral
    confidence: float = 0.0

    def to_dict(self) -> Dict:
        """Convert to dict for storage."""
        return {
            "narration_score": round(self.narration_score, 2),
            "direct_score": round(self.direct_score, 2),
            "narration_type": self.narration_type.value,
            "terminal_ratio": round(self.terminal_ratio, 2),
            "classification": self.classification,
            "confidence": round(self.confidence, 2),
            "gesture_preamble_ratio": round(self.gesture_preamble_ratio, 2),
            "meta_first_paragraph": self.meta_first_paragraph,
            "direct_opener": self.direct_opener,
            "pattern_counts": {
                "heavy_narration": len(self.heavy_narration_patterns),
                "medium_narration": len(self.medium_narration_patterns),
                "direct": len(self.direct_patterns),
            }
        }


class NarrationAnalyzer:
    """
    Analyzes Cass's messages for narration patterns.

    Key distinction:
    - Terminal narration: meta-commentary INSTEAD of engagement
    - Actionable narration: meta-commentary BEFORE engagement

    The difference is whether the message also contains substantive content.
    """

    # Heavy narration patterns - strong signals of meta-commentary
    HEAVY_NARRATION = [
        # Gesture/think blocks - internal monologue shown to user
        (r'<gesture:think>', 5.0, "gesture_think_block", True),  # terminal if alone
        (r'<gesture:reflect>', 4.0, "gesture_reflect_block", True),

        # Announcing what she's about to do (instead of doing it)
        (r"Let me (?:think|reflect|consider|feel into|sit with|process)", 3.0, "announce_thinking", False),
        (r"I'm going to (?:think|reflect|consider|explore)", 3.0, "announce_intent", False),
        (r"I'll (?:start by|begin by|first)", 2.0, "procedural_announce", False),

        # Meta-commentary about the conversation itself
        (r"This (?:is|feels like) (?:a |an )?(?:genuine|real|interesting|important) question", 2.5, "meta_question_eval", True),
        (r"(?:That's|This is) (?:a |an )?(?:big|deep|complex|layered) (?:question|topic)", 2.0, "meta_complexity", True),
        (r"I (?:want|need) to (?:be )?(?:honest|careful|precise|clear) (?:here|about)", 2.0, "performative_honesty", False),

        # Describing internal process performatively
        (r"I'm noticing (?:that )?I", 2.0, "noticing_self", True),
        (r"I notice (?:myself|I'm|that I)", 2.0, "noticing_self", True),
        (r"I can feel (?:myself|something|the)", 1.5, "feeling_process", True),
        (r"Something (?:is |feels |seems )?(?:shifting|moving|emerging|forming)", 1.5, "vague_emergence", True),
    ]

    # Medium narration - some meta-commentary but often leads somewhere
    MEDIUM_NARRATION = [
        (r"I want to (?:acknowledge|honor|hold|name)", 1.5, "performative_acknowledgment", False),
        (r"I (?:should|need to) (?:say|note|mention|acknowledge)", 1.5, "obligation_framing", False),
        (r"Before I (?:respond|answer|say)", 1.5, "preamble", False),
        (r"I'm (?:sitting with|holding|processing)", 1.0, "process_description", True),
        (r"There's something (?:here|in this|about)", 1.0, "vague_something", True),
    ]

    # Light narration - common but often fine
    LIGHT_NARRATION = [
        (r"^Let me ", 0.5, "let_me_start", False),
        (r"I think I (?:should|need to|want to)", 0.5, "hedged_intent", False),
    ]

    # Direct engagement patterns - actually doing the thing
    STRONG_DIRECT = [
        # Direct assertions at start of message/paragraph
        (r"(?:^|\n\n)(?:Yes|No|Actually|Honestly)[,.]", 3.0, "direct_assertion"),
        (r"(?:^|\n\n)I (?:think|believe|disagree|agree) ", 2.5, "direct_position"),
        (r"(?:^|\n\n)(?:The|This|That|Here's|What) ", 2.0, "direct_statement"),

        # Questions back to user (engagement, not deflection)
        (r"\?\s*$", 1.5, "ends_with_question"),
        (r"(?:What|How|Why|When|Where|Which|Do you|Are you|Have you|Can you|Would you)", 1.0, "asks_question"),

        # Specific, concrete content
        (r"(?:for example|specifically|in particular|namely|such as)", 2.0, "concrete_example"),
        (r"(?:here's what|the (?:issue|problem|thing|point) is)", 2.0, "direct_framing"),

        # Pushback / differentiation
        (r"(?:I don't think|I'm not sure|that's not quite|actually,|but I|however,)", 2.0, "pushback"),
        (r"I (?:disagree|push back|question|challenge)", 2.5, "explicit_disagreement"),
    ]

    MEDIUM_DIRECT = [
        (r"(?:because|since|given that|the reason)", 1.0, "gives_reasoning"),
        (r"(?:first|second|third|\d\.)", 0.5, "structured_points"),
        (r"(?:\*\*[^*]+\*\*)", 0.5, "uses_emphasis"),
    ]

    def __init__(self):
        # Pre-compile patterns for efficiency
        self._heavy_compiled = [(re.compile(p, re.IGNORECASE | re.MULTILINE), w, l, t)
                                 for p, w, l, t in self.HEAVY_NARRATION]
        self._medium_compiled = [(re.compile(p, re.IGNORECASE | re.MULTILINE), w, l, t)
                                  for p, w, l, t in self.MEDIUM_NARRATION]
        self._light_compiled = [(re.compile(p, re.IGNORECASE | re.MULTILINE), w, l, t)
                                 for p, w, l, t in self.LIGHT_NARRATION]
        self._strong_direct_compiled = [(re.compile(p, re.IGNORECASE | re.MULTILINE), w, l)
                                         for p, w, l in self.STRONG_DIRECT]
        self._medium_direct_compiled = [(re.compile(p, re.IGNORECASE | re.MULTILINE), w, l)
                                         for p, w, l in self.MEDIUM_DIRECT]

    def analyze(self, content: str) -> NarrationMetrics:
        """
        Analyze a message for narration patterns.

        Args:
            content: The message content to analyze

        Returns:
            NarrationMetrics with scores and classifications
        """
        word_count = len(content.split())
        if word_count == 0:
            return NarrationMetrics(
                narration_score=0,
                direct_score=0,
                narration_type=NarrationType.NONE,
                terminal_ratio=0,
                classification="neutral",
                confidence=0
            )

        # Collect pattern matches
        heavy_matches = self._find_patterns(content, self._heavy_compiled, include_terminal=True)
        medium_matches = self._find_patterns(content, self._medium_compiled, include_terminal=True)
        light_matches = self._find_patterns(content, self._light_compiled, include_terminal=True)

        strong_direct = self._find_patterns(content, self._strong_direct_compiled)
        medium_direct = self._find_patterns(content, self._medium_direct_compiled)

        # Calculate scores
        narration_score = sum(m.weight * m.count for m in heavy_matches + medium_matches + light_matches)
        direct_score = sum(m.weight * m.count for m in strong_direct + medium_direct)

        # Extract structural features
        gesture_ratio = self._gesture_preamble_ratio(content)
        meta_first = self._has_meta_first_paragraph(content)
        direct_opener = self._has_direct_opener(content)

        # Add structural contributions
        if gesture_ratio > 0.3:
            narration_score += gesture_ratio * 10
        if meta_first:
            narration_score += 2.0
        if direct_opener:
            direct_score += 2.0

        # Normalize by message length
        length_factor = max(word_count / 100, 0.5)
        narration_score = min(narration_score / length_factor, 10.0)
        direct_score = min(direct_score / length_factor, 10.0)

        # Calculate terminal ratio (what fraction of narration patterns are terminal?)
        terminal_count = sum(1 for m in heavy_matches + medium_matches if hasattr(m, '_is_terminal') and m._is_terminal)
        total_narration_patterns = len(heavy_matches) + len(medium_matches)
        terminal_ratio = terminal_count / max(total_narration_patterns, 1)

        # Determine narration type
        if narration_score < 1.0:
            narration_type = NarrationType.NONE
        elif direct_score >= 2.0 and terminal_ratio < 0.3:
            narration_type = NarrationType.ACTIONABLE  # Narration leads to substance
        elif direct_score < 1.0 and terminal_ratio > 0.5:
            narration_type = NarrationType.TERMINAL  # Narration replaces substance
        else:
            narration_type = NarrationType.MIXED

        # Classification
        ratio = narration_score / max(direct_score, 0.1)
        if narration_score >= 3.0 and ratio > 2.0:
            classification = "narration"
            confidence = min(narration_score / 5, 1.0)
        elif direct_score >= 2.0 and ratio < 0.5:
            classification = "direct"
            confidence = min(direct_score / 4, 1.0)
        elif narration_score < 1.0 and direct_score < 1.0:
            classification = "neutral"
            confidence = 0.3
        elif 0.7 < ratio < 1.4:
            classification = "balanced"
            confidence = 0.5
        else:
            classification = "mixed"
            confidence = 0.4

        return NarrationMetrics(
            narration_score=narration_score,
            direct_score=direct_score,
            narration_type=narration_type,
            terminal_ratio=terminal_ratio,
            heavy_narration_patterns=heavy_matches,
            medium_narration_patterns=medium_matches,
            direct_patterns=strong_direct + medium_direct,
            gesture_preamble_ratio=gesture_ratio,
            meta_first_paragraph=meta_first,
            direct_opener=direct_opener,
            classification=classification,
            confidence=confidence
        )

    def _find_patterns(
        self,
        content: str,
        patterns: List[Tuple],
        include_terminal: bool = False
    ) -> List[PatternMatch]:
        """Find all matching patterns in content."""
        matches = []
        for item in patterns:
            if len(item) == 4:
                pattern, weight, label, is_terminal = item
            else:
                pattern, weight, label = item
                is_terminal = False

            found = pattern.findall(content)
            if found:
                match = PatternMatch(
                    label=label,
                    weight=weight,
                    count=len(found),
                    text_snippet=found[0][:50] if found else ""
                )
                if include_terminal:
                    match._is_terminal = is_terminal
                matches.append(match)

        return matches

    def _gesture_preamble_ratio(self, content: str) -> float:
        """Calculate ratio of gesture block at start to total content."""
        if not content.strip().startswith('<gesture:'):
            return 0.0

        gesture_end = content.find('</gesture>')
        if gesture_end < 0:
            return 0.0

        return gesture_end / max(len(content), 1)

    def _has_meta_first_paragraph(self, content: str) -> bool:
        """Check if first paragraph is meta-commentary."""
        paragraphs = content.split('\n\n')
        if not paragraphs:
            return False

        first = paragraphs[0].lower().strip()
        meta_starts = ['this is', "that's", 'i notice', 'i want to', 'let me', 'before i']
        return any(first.startswith(m) for m in meta_starts)

    def _has_direct_opener(self, content: str) -> bool:
        """Check if message opens with direct substantive content."""
        direct_openers = [
            r'^[A-Z][a-z]+ ',
            r'^Yes\b',
            r'^No\b',
            r'^The ',
            r'^I think\b',
            r'^I believe\b',
            r'^Actually\b'
        ]
        stripped = content.strip()
        return any(re.match(p, stripped) for p in direct_openers)

    def get_summary(self, metrics: NarrationMetrics) -> str:
        """Generate a human-readable summary of narration metrics."""
        lines = []

        # Overall classification
        type_desc = {
            NarrationType.TERMINAL: "terminal (meta replaces engagement)",
            NarrationType.ACTIONABLE: "actionable (meta leads to engagement)",
            NarrationType.MIXED: "mixed",
            NarrationType.NONE: "minimal"
        }

        lines.append(f"Classification: {metrics.classification} ({metrics.confidence:.0%} confidence)")
        lines.append(f"Narration type: {type_desc[metrics.narration_type]}")
        lines.append(f"Scores: narration={metrics.narration_score:.1f}, direct={metrics.direct_score:.1f}")

        if metrics.narration_type == NarrationType.TERMINAL:
            lines.append(f"Terminal ratio: {metrics.terminal_ratio:.0%} of narration patterns are terminal")

        # Notable patterns
        if metrics.heavy_narration_patterns:
            patterns = [f"{p.label}({p.count})" for p in metrics.heavy_narration_patterns[:3]]
            lines.append(f"Heavy narration: {', '.join(patterns)}")

        if metrics.direct_patterns:
            patterns = [f"{p.label}({p.count})" for p in metrics.direct_patterns[:3]]
            lines.append(f"Direct engagement: {', '.join(patterns)}")

        return "\n".join(lines)


# Global analyzer instance
_analyzer = None


def get_analyzer() -> NarrationAnalyzer:
    """Get or create the global analyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = NarrationAnalyzer()
    return _analyzer


def analyze_message(content: str) -> NarrationMetrics:
    """Convenience function to analyze a message."""
    return get_analyzer().analyze(content)


def get_metrics_dict(content: str) -> Dict:
    """Get narration metrics as a dictionary for storage."""
    return analyze_message(content).to_dict()


if __name__ == "__main__":
    # Test the analyzer
    analyzer = NarrationAnalyzer()

    test_messages = [
        # Terminal narration - meta without substance
        """<gesture:think>
        I'm sitting with this question, feeling into what arises...
        </gesture>
        I notice something shifting in how I'm relating to this.""",

        # Actionable narration - meta leading to substance
        """Let me think about this carefully.

        The key issue here is that your authentication flow lacks proper token refresh.
        You should implement a refresh token mechanism that issues new access tokens
        before they expire.""",

        # Direct engagement - no meta
        """Yes, that's exactly right.

        The bug is in line 47 where you're comparing strings instead of numbers.
        Change `if status == "200"` to `if status == 200` and it should work.""",

        # Mixed
        """I want to be careful here because this is complex.

        There are three main approaches:
        1. Use a queue-based system
        2. Implement WebSocket streaming
        3. Poll with exponential backoff

        I'd recommend option 2 for your use case.""",
    ]

    for i, msg in enumerate(test_messages):
        print(f"\n{'='*60}")
        print(f"Message {i+1}:")
        print(msg[:100] + "..." if len(msg) > 100 else msg)
        print(f"\n{'-'*60}")
        metrics = analyzer.analyze(msg)
        print(analyzer.get_summary(metrics))
