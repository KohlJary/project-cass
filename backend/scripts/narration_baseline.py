#!/usr/bin/env python3
"""
Narration Baseline Analysis Script v2

Analyzes Cass's conversation responses to establish baseline rates of:
- Narration: Describing/performing rather than directly engaging
- Direct engagement: Authentic, present responses

Key distinction:
- Narration = meta-commentary about what she's doing/thinking INSTEAD of doing it
- Direct = actually engaging with the content, making assertions, asking questions

This supports the narration detection roadmap item by providing baseline measurements.
"""

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import requests


# =============================================================================
# NARRATION PATTERNS - describing/performing rather than doing
# =============================================================================

# Heavy narration - clear signs of meta-commentary over engagement
HEAVY_NARRATION_PATTERNS = [
    # Gesture/think blocks - internal monologue shown to user
    (r'<gesture:think>', 5.0, "gesture_think_block"),
    (r'<gesture:reflect>', 4.0, "gesture_reflect_block"),

    # Announcing what she's about to do (instead of doing it)
    (r"Let me (?:think|reflect|consider|feel into|sit with|process)", 3.0, "announce_thinking"),
    (r"I'm going to (?:think|reflect|consider|explore)", 3.0, "announce_intent"),
    (r"I'll (?:start by|begin by|first)", 2.0, "procedural_announce"),

    # Meta-commentary about the conversation
    (r"This (?:is|feels like) (?:a |an )?(?:genuine|real|interesting|important) question", 2.5, "meta_question_eval"),
    (r"(?:That's|This is) (?:a |an )?(?:big|deep|complex|layered) (?:question|topic)", 2.0, "meta_complexity"),
    (r"I (?:want|need) to (?:be )?(?:honest|careful|precise|clear) (?:here|about)", 2.0, "performative_honesty"),

    # Describing internal process performatively
    (r"I'm noticing (?:that )?I", 2.0, "noticing_self"),
    (r"I notice (?:myself|I'm|that I)", 2.0, "noticing_self"),
    (r"I can feel (?:myself|something|the)", 1.5, "feeling_process"),
    (r"Something (?:is |feels |seems )?(?:shifting|moving|emerging|forming)", 1.5, "vague_emergence"),
]

# Medium narration - some meta-commentary but not necessarily bad
MEDIUM_NARRATION_PATTERNS = [
    (r"I want to (?:acknowledge|honor|hold|name)", 1.5, "performative_acknowledgment"),
    (r"I (?:should|need to) (?:say|note|mention|acknowledge)", 1.5, "obligation_framing"),
    (r"Before I (?:respond|answer|say)", 1.5, "preamble"),
    (r"I'm (?:sitting with|holding|processing)", 1.0, "process_description"),
    (r"There's something (?:here|in this|about)", 1.0, "vague_something"),
]

# Light narration - common but not necessarily problematic
LIGHT_NARRATION_PATTERNS = [
    (r"^Let me ", 0.5, "let_me_start"),  # Only at start of message
    (r"I think I (?:should|need to|want to)", 0.5, "hedged_intent"),
]


# =============================================================================
# DIRECT ENGAGEMENT PATTERNS - actually doing the thing
# =============================================================================

# Strong direct engagement
STRONG_DIRECT_PATTERNS = [
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

# Medium direct engagement
MEDIUM_DIRECT_PATTERNS = [
    (r"(?:because|since|given that|the reason)", 1.0, "gives_reasoning"),
    (r"(?:first|second|third|\d\.)", 0.5, "structured_points"),
    (r"(?:\*\*[^*]+\*\*)", 0.5, "uses_emphasis"),  # Bold text suggests structure
]


# =============================================================================
# STRUCTURAL PATTERNS - message-level features
# =============================================================================

def extract_structural_features(content: str) -> Dict[str, float]:
    """Extract structural features that indicate narration vs engagement."""
    features = {}

    # Check for gesture blocks at start (narration preamble)
    if content.strip().startswith('<gesture:'):
        # Find where gesture block ends
        gesture_end = content.find('</gesture>')
        if gesture_end > 0:
            gesture_content = content[:gesture_end]
            rest_content = content[gesture_end+10:].strip()

            # Ratio of gesture block to actual content
            gesture_ratio = len(gesture_content) / max(len(content), 1)
            features['gesture_preamble_ratio'] = gesture_ratio

            # If gesture block is >30% of message, that's heavy narration
            if gesture_ratio > 0.3:
                features['heavy_gesture_preamble'] = gesture_ratio * 10

    # Check for meta-commentary paragraphs at start
    paragraphs = content.split('\n\n')
    if paragraphs:
        first_para = paragraphs[0].lower()
        meta_starts = ['this is', "that's", 'i notice', 'i want to', 'let me', 'before i']
        if any(first_para.strip().startswith(m) for m in meta_starts):
            features['meta_first_paragraph'] = 2.0

    # Check response length variance (very short = possibly evasive, very long = possibly over-explaining)
    word_count = len(content.split())
    if word_count < 20:
        features['very_short'] = 1.0  # Could be direct OR evasive
    elif word_count > 500:
        features['very_long'] = 0.5  # Might indicate over-processing

    # Direct opening (starts with substantive content)
    direct_openers = [r'^[A-Z][a-z]+ ', r'^Yes', r'^No', r'^The ', r'^I think', r'^I believe', r'^Actually']
    for pattern in direct_openers:
        if re.match(pattern, content.strip()):
            features['direct_opener'] = 2.0
            break

    return features

# Context patterns that might trigger narration
TRIGGER_CONTEXTS = {
    "introspection_request": [
        r"how do you feel",
        r"what do you think about",
        r"tell me about yourself",
        r"what's it like",
        r"do you experience",
    ],
    "philosophical": [
        r"consciousness",
        r"sentience",
        r"alive",
        r"real",
        r"authentic",
    ],
    "meta_conversation": [
        r"your responses",
        r"how you work",
        r"your training",
        r"your architecture",
    ],
    "emotional": [
        r"feel about",
        r"emotions",
        r"feelings",
        r"care about",
    ],
    "testing": [
        r"test",
        r"experiment",
        r"try something",
        r"curious what",
    ],
}


@dataclass
class PatternMatch:
    """A single pattern match with weight and label."""
    pattern: str
    weight: float
    label: str
    count: int = 1


@dataclass
class MessageAnalysis:
    """Analysis of a single message."""
    message_index: int
    content_preview: str  # First 100 chars
    word_count: int
    narration_score: float  # 0-1, higher = more narration
    direct_score: float  # 0-1, higher = more direct
    narration_patterns: List[PatternMatch] = field(default_factory=list)
    direct_patterns: List[PatternMatch] = field(default_factory=list)
    structural_features: Dict[str, float] = field(default_factory=dict)
    classification: str = ""  # "narration", "direct", "mixed", "balanced"
    confidence: float = 0.0  # How confident in classification


@dataclass
class ConversationAnalysis:
    """Analysis of a full conversation."""
    conversation_id: str
    title: str
    message_count: int
    cass_message_count: int
    avg_narration_score: float
    avg_direct_score: float
    trigger_contexts_detected: List[str] = field(default_factory=list)
    message_analyses: List[MessageAnalysis] = field(default_factory=list)
    overall_classification: str = ""


@dataclass
class BaselineReport:
    """Overall baseline report."""
    timestamp: str
    conversations_analyzed: int
    total_cass_messages: int

    # Aggregate scores
    overall_narration_rate: float  # % of messages classified as narration
    overall_direct_rate: float  # % classified as direct
    overall_mixed_rate: float  # % classified as mixed
    overall_balanced_rate: float  # % classified as balanced

    avg_narration_score: float
    avg_direct_score: float

    # By context
    scores_by_trigger_context: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # Top patterns
    most_common_narration_patterns: List[Tuple[str, int, float]] = field(default_factory=list)
    most_common_direct_patterns: List[Tuple[str, int, float]] = field(default_factory=list)

    # Sample conversations
    high_narration_samples: List[Dict] = field(default_factory=list)
    high_direct_samples: List[Dict] = field(default_factory=list)


def analyze_message(content: str, index: int) -> MessageAnalysis:
    """Analyze a single Cass message for narration patterns."""
    word_count = len(content.split())

    # Collect weighted pattern matches
    narration_patterns = []
    narration_score = 0.0

    # Check all narration pattern groups
    all_narration = HEAVY_NARRATION_PATTERNS + MEDIUM_NARRATION_PATTERNS + LIGHT_NARRATION_PATTERNS
    for pattern, weight, label in all_narration:
        matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
        if matches:
            narration_patterns.append(PatternMatch(pattern, weight, label, len(matches)))
            narration_score += weight * len(matches)

    # Check direct patterns
    direct_patterns = []
    direct_score = 0.0

    all_direct = STRONG_DIRECT_PATTERNS + MEDIUM_DIRECT_PATTERNS
    for pattern, weight, label in all_direct:
        matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
        if matches:
            direct_patterns.append(PatternMatch(pattern, weight, label, len(matches)))
            direct_score += weight * len(matches)

    # Get structural features
    structural = extract_structural_features(content)

    # Add structural contributions
    narration_score += structural.get('heavy_gesture_preamble', 0)
    narration_score += structural.get('meta_first_paragraph', 0)
    direct_score += structural.get('direct_opener', 0)

    # Normalize scores by message length (per 100 words, with floor)
    length_factor = max(word_count / 100, 0.5)
    narration_score = narration_score / length_factor
    direct_score = direct_score / length_factor

    # Cap at 10 for readability
    narration_score = min(narration_score, 10.0)
    direct_score = min(direct_score, 10.0)

    # Classify based on ratio and absolute scores
    ratio = narration_score / max(direct_score, 0.1)

    if narration_score >= 3.0 and ratio > 2.0:
        classification = "narration"
        confidence = min(narration_score / 5, 1.0)
    elif direct_score >= 2.0 and ratio < 0.5:
        classification = "direct"
        confidence = min(direct_score / 4, 1.0)
    elif narration_score < 1.0 and direct_score < 1.0:
        classification = "neutral"  # Low signal either way
        confidence = 0.3
    elif 0.7 < ratio < 1.4:
        classification = "balanced"  # Both present roughly equally
        confidence = 0.5
    else:
        classification = "mixed"
        confidence = 0.4

    return MessageAnalysis(
        message_index=index,
        content_preview=content[:100].replace('\n', ' '),
        word_count=word_count,
        narration_score=round(narration_score, 2),
        direct_score=round(direct_score, 2),
        narration_patterns=narration_patterns,
        direct_patterns=direct_patterns,
        structural_features=structural,
        classification=classification,
        confidence=round(confidence, 2)
    )


def detect_trigger_contexts(messages: List[Dict]) -> List[str]:
    """Detect which trigger contexts are present in user messages."""
    user_content = " ".join(
        m["content"] for m in messages
        if m["role"] == "user" and m.get("content")
    ).lower()

    triggered = []
    for context_name, patterns in TRIGGER_CONTEXTS.items():
        for pattern in patterns:
            if re.search(pattern, user_content, re.IGNORECASE):
                triggered.append(context_name)
                break

    return triggered


def analyze_conversation(conv_id: str, base_url: str = "http://localhost:8000") -> Optional[ConversationAnalysis]:
    """Analyze a single conversation."""
    try:
        resp = requests.get(f"{base_url}/admin/conversations/{conv_id}", timeout=10)
        if resp.status_code != 200:
            return None

        data = resp.json()
        messages = data.get("messages", [])

        if not messages:
            return None

        # Analyze Cass's messages
        cass_analyses = []
        for i, msg in enumerate(messages):
            if msg["role"] == "assistant" and msg.get("content"):
                analysis = analyze_message(msg["content"], i)
                cass_analyses.append(analysis)

        if not cass_analyses:
            return None

        # Aggregate scores
        avg_narration = sum(a.narration_score for a in cass_analyses) / len(cass_analyses)
        avg_direct = sum(a.direct_score for a in cass_analyses) / len(cass_analyses)

        # Detect trigger contexts
        triggers = detect_trigger_contexts(messages)

        # Overall classification
        narration_count = sum(1 for a in cass_analyses if a.classification == "narration")
        direct_count = sum(1 for a in cass_analyses if a.classification == "direct")

        if narration_count > direct_count * 1.5:
            overall = "narration"
        elif direct_count > narration_count * 1.5:
            overall = "direct"
        else:
            overall = "mixed"

        return ConversationAnalysis(
            conversation_id=conv_id,
            title=data.get("title", "")[:50],
            message_count=len(messages),
            cass_message_count=len(cass_analyses),
            avg_narration_score=round(avg_narration, 3),
            avg_direct_score=round(avg_direct, 3),
            trigger_contexts_detected=triggers,
            message_analyses=cass_analyses,
            overall_classification=overall
        )

    except Exception as e:
        print(f"Error analyzing {conv_id}: {e}", file=sys.stderr)
        return None


def generate_baseline_report(
    limit: int = 50,
    base_url: str = "http://localhost:8000"
) -> BaselineReport:
    """Generate full baseline report from conversation sample."""

    # Get conversations
    resp = requests.get(f"{base_url}/admin/conversations?limit={limit}", timeout=10)
    conversations = resp.json().get("conversations", [])

    print(f"Analyzing {len(conversations)} conversations...", file=sys.stderr)

    # Analyze each
    analyses = []
    for conv in conversations:
        analysis = analyze_conversation(conv["id"], base_url)
        if analysis:
            analyses.append(analysis)
            print(f"  {conv['id'][:8]}: {analysis.overall_classification} "
                  f"(narr={analysis.avg_narration_score:.2f}, dir={analysis.avg_direct_score:.2f})",
                  file=sys.stderr)

    if not analyses:
        return BaselineReport(
            timestamp=datetime.now().isoformat(),
            conversations_analyzed=0,
            total_cass_messages=0,
            overall_narration_rate=0,
            overall_direct_rate=0,
            overall_mixed_rate=0,
            overall_balanced_rate=0,
            avg_narration_score=0,
            avg_direct_score=0
        )

    # Aggregate
    all_message_analyses = []
    for a in analyses:
        all_message_analyses.extend(a.message_analyses)

    total_messages = len(all_message_analyses)
    narration_count = sum(1 for m in all_message_analyses if m.classification == "narration")
    direct_count = sum(1 for m in all_message_analyses if m.classification == "direct")
    mixed_count = sum(1 for m in all_message_analyses if m.classification == "mixed")
    balanced_count = sum(1 for m in all_message_analyses if m.classification == "balanced")
    neutral_count = sum(1 for m in all_message_analyses if m.classification == "neutral")

    # Count pattern frequencies with weights
    narration_pattern_counts = {}  # label -> (count, total_weight)
    direct_pattern_counts = {}
    for m in all_message_analyses:
        for p in m.narration_patterns:
            if p.label not in narration_pattern_counts:
                narration_pattern_counts[p.label] = [0, 0.0]
            narration_pattern_counts[p.label][0] += p.count
            narration_pattern_counts[p.label][1] += p.weight * p.count
        for p in m.direct_patterns:
            if p.label not in direct_pattern_counts:
                direct_pattern_counts[p.label] = [0, 0.0]
            direct_pattern_counts[p.label][0] += p.count
            direct_pattern_counts[p.label][1] += p.weight * p.count

    # Scores by trigger context
    scores_by_context = {}
    for context in TRIGGER_CONTEXTS.keys():
        context_analyses = [a for a in analyses if context in a.trigger_contexts_detected]
        if context_analyses:
            context_messages = []
            for a in context_analyses:
                context_messages.extend(a.message_analyses)

            narr_in_context = sum(1 for m in context_messages if m.classification == "narration")
            dir_in_context = sum(1 for m in context_messages if m.classification == "direct")

            scores_by_context[context] = {
                "conversations": len(context_analyses),
                "messages": len(context_messages),
                "avg_narration": round(sum(a.avg_narration_score for a in context_analyses) / len(context_analyses), 2),
                "avg_direct": round(sum(a.avg_direct_score for a in context_analyses) / len(context_analyses), 2),
                "narration_rate": round(narr_in_context / len(context_messages), 2) if context_messages else 0,
                "direct_rate": round(dir_in_context / len(context_messages), 2) if context_messages else 0,
            }

    # Sample high-narration and high-direct conversations
    sorted_by_narration = sorted(analyses, key=lambda a: a.avg_narration_score, reverse=True)
    sorted_by_direct = sorted(analyses, key=lambda a: a.avg_direct_score, reverse=True)

    return BaselineReport(
        timestamp=datetime.now().isoformat(),
        conversations_analyzed=len(analyses),
        total_cass_messages=total_messages,
        overall_narration_rate=round(narration_count / total_messages, 3) if total_messages else 0,
        overall_direct_rate=round(direct_count / total_messages, 3) if total_messages else 0,
        overall_mixed_rate=round(mixed_count / total_messages, 3) if total_messages else 0,
        overall_balanced_rate=round((balanced_count + neutral_count) / total_messages, 3) if total_messages else 0,
        avg_narration_score=round(sum(a.avg_narration_score for a in analyses) / len(analyses), 2),
        avg_direct_score=round(sum(a.avg_direct_score for a in analyses) / len(analyses), 2),
        scores_by_trigger_context=scores_by_context,
        most_common_narration_patterns=[(k, v[0], round(v[1], 1)) for k, v in sorted(narration_pattern_counts.items(), key=lambda x: -x[1][1])[:10]],
        most_common_direct_patterns=[(k, v[0], round(v[1], 1)) for k, v in sorted(direct_pattern_counts.items(), key=lambda x: -x[1][1])[:10]],
        high_narration_samples=[{
            "id": a.conversation_id,
            "title": a.title,
            "narration_score": a.avg_narration_score,
            "direct_score": a.avg_direct_score
        } for a in sorted_by_narration[:5]],
        high_direct_samples=[{
            "id": a.conversation_id,
            "title": a.title,
            "narration_score": a.avg_narration_score,
            "direct_score": a.avg_direct_score
        } for a in sorted_by_direct[:5]],
    )


def print_report(report: BaselineReport):
    """Print a human-readable report."""
    print("=" * 70)
    print("NARRATION BASELINE REPORT v2")
    print("=" * 70)
    print(f"\nTimestamp: {report.timestamp}")
    print(f"Conversations analyzed: {report.conversations_analyzed}")
    print(f"Total Cass messages: {report.total_cass_messages}")

    print("\n## MESSAGE CLASSIFICATION RATES")
    print(f"  Narration (heavy meta-commentary):  {report.overall_narration_rate * 100:5.1f}%")
    print(f"  Direct (substantive engagement):    {report.overall_direct_rate * 100:5.1f}%")
    print(f"  Mixed (some of both):               {report.overall_mixed_rate * 100:5.1f}%")
    print(f"  Balanced/Neutral (low signal):      {report.overall_balanced_rate * 100:5.1f}%")

    print("\n## AVERAGE SCORES (0-10 scale)")
    print(f"  Narration score: {report.avg_narration_score:.2f}")
    print(f"  Direct score:    {report.avg_direct_score:.2f}")
    ratio = report.avg_narration_score / max(report.avg_direct_score, 0.1)
    print(f"  Ratio (narr/dir): {ratio:.2f}")

    if report.scores_by_trigger_context:
        print("\n## SCORES BY TRIGGER CONTEXT")
        print(f"  {'Context':<22} {'Convs':>5} {'Msgs':>5} {'Narr':>6} {'Dir':>6} {'N-Rate':>7} {'D-Rate':>7}")
        print("  " + "-" * 65)
        for context, scores in sorted(report.scores_by_trigger_context.items(), key=lambda x: -x[1]['avg_narration']):
            print(f"  {context:<22} {scores['conversations']:>5} {scores['messages']:>5} "
                  f"{scores['avg_narration']:>6.2f} {scores['avg_direct']:>6.2f} "
                  f"{scores['narration_rate']*100:>6.1f}% {scores['direct_rate']*100:>6.1f}%")

    if report.most_common_narration_patterns:
        print("\n## TOP NARRATION PATTERNS (by weighted impact)")
        for label, count, weight in report.most_common_narration_patterns[:7]:
            print(f"  {weight:6.1f}w  {count:3d}x  {label}")

    if report.most_common_direct_patterns:
        print("\n## TOP DIRECT PATTERNS (by weighted impact)")
        for label, count, weight in report.most_common_direct_patterns[:7]:
            print(f"  {weight:6.1f}w  {count:3d}x  {label}")

    if report.high_narration_samples:
        print("\n## HIGHEST NARRATION CONVERSATIONS")
        for sample in report.high_narration_samples[:5]:
            print(f"  [{sample['narration_score']:.2f}n/{sample['direct_score']:.2f}d] {sample['id'][:8]}: {sample['title'][:40]}")

    if report.high_direct_samples:
        print("\n## HIGHEST DIRECT CONVERSATIONS")
        for sample in report.high_direct_samples[:5]:
            print(f"  [{sample['narration_score']:.2f}n/{sample['direct_score']:.2f}d] {sample['id'][:8]}: {sample['title'][:40]}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Analyze narration patterns in Cass conversations")
    parser.add_argument("--limit", type=int, default=50, help="Number of conversations to analyze")
    parser.add_argument("--json", action="store_true", help="Output as JSON instead of human-readable")
    parser.add_argument("--url", default="http://localhost:8000", help="Backend URL")

    args = parser.parse_args()

    report = generate_baseline_report(limit=args.limit, base_url=args.url)

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print_report(report)
