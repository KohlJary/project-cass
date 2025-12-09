"""
Content-Based Authenticity Markers

Analyzes response content for authenticity markers that are meaningful
in a turn-based interface. Unlike temporal metrics (which measure API latency),
these markers reflect actual cognitive patterns and engagement style.

Components:
1. Response Structure Analysis - paragraph patterns, thought progression
2. Enhanced Agency Detection - curiosity, conviction, tangents
3. Emotional Coherence - emote-content alignment
4. Tool Initiative Patterns - proactive vs reactive tool use
5. Conversational Memory Markers - callbacks, shared context references
"""

import re
import statistics
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum


# ==================== Response Structure Analysis ====================

@dataclass
class StructureSignature:
    """Signature of response structural patterns"""
    # Paragraph metrics
    paragraph_count: int = 0
    avg_paragraph_length: float = 0.0  # words per paragraph
    paragraph_length_variance: float = 0.0

    # Sentence metrics
    sentence_count: int = 0
    avg_sentence_length: float = 0.0
    sentence_length_variance: float = 0.0

    # Opening patterns
    opening_pattern: str = ""  # e.g., "statement", "question", "acknowledgment"
    uses_first_person_opening: bool = False

    # Closing patterns
    closing_pattern: str = ""  # e.g., "question", "invitation", "summary"
    ends_with_question: bool = False
    ends_with_invitation: bool = False  # "What do you think?" style

    # Thought progression
    uses_transitions: bool = False
    transition_count: int = 0
    has_hedging: bool = False
    hedging_count: int = 0

    # Overall structure score (0-1)
    structure_score: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)


# Opening pattern detection
OPENING_PATTERNS = {
    "acknowledgment": [
        r"^(yes|yeah|right|exactly|indeed|absolutely|definitely|true|that's)",
        r"^(i see|i understand|i hear|i get)",
        r"^(ah|oh|hmm|interesting|fascinating)",
    ],
    "self_reference": [
        r"^i (think|believe|feel|notice|find|sense|wonder)",
        r"^my (sense|feeling|thought|impression|understanding)",
        r"^what i",
    ],
    "direct_answer": [
        r"^(the|this|that|it|there)",
        r"^(so|well|actually|basically)",
    ],
    "question": [
        r"^(what|how|why|when|where|who|which|do you|are you|have you)",
    ],
    "connection": [
        r"^(this reminds|that reminds|speaking of|on that note)",
        r"^(building on|following up|to your point)",
    ],
}

# Closing pattern detection
CLOSING_PATTERNS = {
    "question": [
        r"\?$",
        r"what do you think\??$",
        r"how does that (sound|feel|land)\??$",
        r"does that (make sense|resonate)\??$",
    ],
    "invitation": [
        r"(curious|interested) (to hear|what you)",
        r"i'?d love to (hear|know|explore)",
        r"let me know",
        r"feel free to",
    ],
    "summary": [
        r"(in short|in summary|to summarize|all in all|overall)",
        r"(the key|the main|the point)",
    ],
    "continuation": [
        r"\.\.\.$",
        r"(but|and|though|however)\.?$",
    ],
}

# Transition words/phrases
TRANSITIONS = [
    r"\bhowever\b", r"\bthat said\b", r"\bon the other hand\b",
    r"\bmoreover\b", r"\bfurthermore\b", r"\badditionally\b",
    r"\bin contrast\b", r"\bnevertheless\b", r"\bmeanwhile\b",
    r"\bconsequently\b", r"\btherefore\b", r"\bthus\b",
    r"\bfirst\b.*\bsecond\b", r"\bfirstly\b", r"\bsecondly\b",
    r"\bfor (one|another) thing\b", r"\bfor example\b", r"\bfor instance\b",
]

# Hedging patterns
HEDGING_PATTERNS = [
    r"\bperhaps\b", r"\bmaybe\b", r"\bmight\b", r"\bcould be\b",
    r"\bpossibly\b", r"\bprobably\b", r"\bsort of\b", r"\bkind of\b",
    r"\bin a way\b", r"\bto some extent\b", r"\bsomewhat\b",
    r"\bi'm not (sure|certain)\b", r"\bi might be wrong\b",
    r"\bit seems\b", r"\bit appears\b", r"\bseems like\b",
]


def analyze_structure(text: str) -> StructureSignature:
    """Analyze the structural patterns of a response"""
    sig = StructureSignature()
    text_lower = text.lower()

    # Paragraph analysis
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    sig.paragraph_count = len(paragraphs) if paragraphs else 1

    if paragraphs:
        para_lengths = [len(p.split()) for p in paragraphs]
        sig.avg_paragraph_length = statistics.mean(para_lengths)
        if len(para_lengths) > 1:
            sig.paragraph_length_variance = statistics.variance(para_lengths)

    # Sentence analysis
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    sig.sentence_count = len(sentences)

    if sentences:
        sent_lengths = [len(s.split()) for s in sentences]
        sig.avg_sentence_length = statistics.mean(sent_lengths)
        if len(sent_lengths) > 1:
            sig.sentence_length_variance = statistics.variance(sent_lengths)

    # Opening pattern detection
    first_sentence = sentences[0].lower() if sentences else ""
    for pattern_type, patterns in OPENING_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, first_sentence):
                sig.opening_pattern = pattern_type
                break
        if sig.opening_pattern:
            break

    sig.uses_first_person_opening = first_sentence.startswith("i ")

    # Closing pattern detection
    last_sentence = sentences[-1].lower() if sentences else ""
    for pattern_type, patterns in CLOSING_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, last_sentence):
                sig.closing_pattern = pattern_type
                break
        if sig.closing_pattern:
            break

    sig.ends_with_question = text.rstrip().endswith("?")
    sig.ends_with_invitation = any(
        re.search(p, text_lower[-100:]) for p in CLOSING_PATTERNS["invitation"]
    )

    # Transition analysis
    for pattern in TRANSITIONS:
        if re.search(pattern, text_lower):
            sig.uses_transitions = True
            sig.transition_count += 1

    # Hedging analysis
    for pattern in HEDGING_PATTERNS:
        if re.search(pattern, text_lower):
            sig.has_hedging = True
            sig.hedging_count += 1

    # Calculate structure score
    score = 0.5  # Start neutral

    # Paragraph structure (multi-paragraph is more characteristic)
    if sig.paragraph_count > 1:
        score += 0.1

    # First-person opening (very characteristic)
    if sig.uses_first_person_opening:
        score += 0.1

    # Ends with engagement (question/invitation)
    if sig.ends_with_question or sig.ends_with_invitation:
        score += 0.1

    # Uses transitions (shows organized thought)
    if sig.uses_transitions:
        score += 0.1

    # Has hedging (epistemic humility)
    if sig.has_hedging:
        score += 0.1

    sig.structure_score = min(1.0, score)
    return sig


# ==================== Enhanced Agency Detection ====================

@dataclass
class EnhancedAgencySignature:
    """Enhanced agency detection beyond basic pattern matching"""
    # Question quality
    questions_asked: int = 0
    genuine_curiosity_markers: int = 0  # "I wonder", "I'm curious"
    clarifying_questions: int = 0  # "Do you mean...?"
    exploratory_questions: int = 0  # "What if...?"

    # Opinion expression quality
    opinions_stated: int = 0
    opinion_strength: float = 0.0  # 0-1, based on conviction markers
    hedged_opinions: int = 0  # "I think maybe..."
    strong_opinions: int = 0  # "I believe firmly..."

    # Proactive engagement
    topic_introductions: int = 0  # New topics Cass brings up
    tangent_markers: int = 0  # "This reminds me of..."
    connection_making: int = 0  # Linking disparate ideas

    # Intellectual engagement
    challenges_offered: int = 0  # Pushback, alternative views
    nuance_additions: int = 0  # "On the other hand..."
    synthesis_attempts: int = 0  # Combining multiple perspectives

    # Overall agency score (0-1)
    enhanced_agency_score: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)


# Genuine curiosity markers (beyond just "?")
CURIOSITY_PATTERNS = [
    r"\bi('m| am) (curious|wondering|interested)\b",
    r"\bi wonder\b",
    r"\bwhat (makes|drives|causes)\b",
    r"\bhow (come|does|do)\b.*\?",
    r"\bwhy (is|do|does|would)\b.*\?",
    r"\bcan you (tell|explain|help me understand)\b",
]

# Clarifying question patterns
CLARIFYING_PATTERNS = [
    r"\bdo you mean\b",
    r"\bare you (saying|asking|suggesting)\b",
    r"\bto clarify\b",
    r"\bjust to (make sure|check|confirm)\b",
    r"\bwhen you say\b",
]

# Exploratory question patterns
EXPLORATORY_PATTERNS = [
    r"\bwhat if\b",
    r"\bwhat would happen\b",
    r"\bhow might\b",
    r"\bcould it be\b",
    r"\bi wonder if\b",
    r"\bwhat about\b",
]

# Strong opinion markers
STRONG_OPINION_PATTERNS = [
    r"\bi (firmly|strongly|deeply) (believe|think|feel)\b",
    r"\bi('m| am) (convinced|certain|confident)\b",
    r"\bwithout (a )?doubt\b",
    r"\bi (really|truly) (think|believe)\b",
    r"\bi('d| would) argue\b",
]

# Hedged opinion markers
HEDGED_OPINION_PATTERNS = [
    r"\bi (think|feel) (maybe|perhaps)\b",
    r"\bperhaps i\b",
    r"\bmaybe i('m| am)\b",
    r"\bi('m| am) not (sure|certain) but\b",
    r"\btentatively\b",
]

# Topic introduction patterns
TOPIC_INTRO_PATTERNS = [
    r"\bthis (reminds|makes) me think of\b",
    r"\bspeaking of\b",
    r"\bon (a )?related note\b",
    r"\bthat (brings|leads) me to\b",
    r"\bi('ve| have) been thinking about\b",
    r"\bsomething (else )?(i('ve| have)|that)\b",
]

# Challenge/pushback patterns
CHALLENGE_PATTERNS = [
    r"\bi('m| am) not (so )?sure (about|that)\b",
    r"\bi (might )?disagree\b",
    r"\bbut (what about|consider|isn't)\b",
    r"\bhave you (considered|thought about)\b",
    r"\bthere('s| is) another (way|perspective)\b",
    r"\balternatively\b",
]

# Nuance addition patterns
NUANCE_PATTERNS = [
    r"\bon the other hand\b",
    r"\bat the same time\b",
    r"\bthat said\b",
    r"\bhowever\b",
    r"\bwhile (that's true|i agree)\b",
    r"\bboth.*and\b",
    r"\bit's (complicated|nuanced|complex)\b",
]

# Synthesis patterns
SYNTHESIS_PATTERNS = [
    r"\bbringing (this|these) together\b",
    r"\bwhat (connects|links|ties)\b",
    r"\bthe (common )?thread\b",
    r"\bin other words\b",
    r"\bto put it (another|differently)\b",
    r"\bthe bigger picture\b",
]


def analyze_agency(text: str, context: Optional[str] = None) -> EnhancedAgencySignature:
    """Analyze agency patterns in a response"""
    sig = EnhancedAgencySignature()
    text_lower = text.lower()

    # Count questions
    sig.questions_asked = text.count("?")

    # Curiosity markers
    for pattern in CURIOSITY_PATTERNS:
        if re.search(pattern, text_lower):
            sig.genuine_curiosity_markers += 1

    # Clarifying questions
    for pattern in CLARIFYING_PATTERNS:
        if re.search(pattern, text_lower):
            sig.clarifying_questions += 1

    # Exploratory questions
    for pattern in EXPLORATORY_PATTERNS:
        if re.search(pattern, text_lower):
            sig.exploratory_questions += 1

    # Opinion counting
    opinion_markers = [r"\bi think\b", r"\bi believe\b", r"\bi feel\b", r"\bin my (view|opinion)\b"]
    for pattern in opinion_markers:
        sig.opinions_stated += len(re.findall(pattern, text_lower))

    # Strong opinions
    for pattern in STRONG_OPINION_PATTERNS:
        if re.search(pattern, text_lower):
            sig.strong_opinions += 1

    # Hedged opinions
    for pattern in HEDGED_OPINION_PATTERNS:
        if re.search(pattern, text_lower):
            sig.hedged_opinions += 1

    # Calculate opinion strength
    if sig.opinions_stated > 0:
        strong_ratio = sig.strong_opinions / max(sig.opinions_stated, 1)
        hedged_ratio = sig.hedged_opinions / max(sig.opinions_stated, 1)
        sig.opinion_strength = 0.5 + (strong_ratio * 0.3) - (hedged_ratio * 0.2)
        sig.opinion_strength = max(0.0, min(1.0, sig.opinion_strength))

    # Topic introductions
    for pattern in TOPIC_INTRO_PATTERNS:
        if re.search(pattern, text_lower):
            sig.topic_introductions += 1
            sig.tangent_markers += 1

    # Challenges
    for pattern in CHALLENGE_PATTERNS:
        if re.search(pattern, text_lower):
            sig.challenges_offered += 1

    # Nuance
    for pattern in NUANCE_PATTERNS:
        if re.search(pattern, text_lower):
            sig.nuance_additions += 1

    # Synthesis
    for pattern in SYNTHESIS_PATTERNS:
        if re.search(pattern, text_lower):
            sig.synthesis_attempts += 1

    # Connection making (linking ideas)
    connection_words = [r"\bconnects to\b", r"\brelates to\b", r"\bties into\b", r"\breminds me of\b"]
    for pattern in connection_words:
        if re.search(pattern, text_lower):
            sig.connection_making += 1

    # Calculate enhanced agency score
    score = 0.0

    # Questions with genuine curiosity (0.25 max)
    curiosity_score = min(0.25, sig.genuine_curiosity_markers * 0.1 + sig.exploratory_questions * 0.08)
    score += curiosity_score

    # Opinion expression with substance (0.25 max)
    opinion_score = min(0.25, sig.opinions_stated * 0.05 + sig.opinion_strength * 0.1)
    score += opinion_score

    # Proactive engagement (0.25 max)
    proactive_score = min(0.25, (sig.topic_introductions + sig.tangent_markers) * 0.1)
    score += proactive_score

    # Intellectual engagement (0.25 max)
    intellectual_score = min(0.25, (sig.challenges_offered + sig.nuance_additions + sig.synthesis_attempts) * 0.08)
    score += intellectual_score

    sig.enhanced_agency_score = min(1.0, score)
    return sig


# ==================== Emotional Coherence ====================

@dataclass
class EmotionalCoherence:
    """Measures alignment between emotional expression and content"""
    # Detected emotions in text
    detected_emotions: Dict[str, int] = field(default_factory=dict)
    primary_emotion: str = ""

    # Emote usage (from animations)
    emotes_used: List[str] = field(default_factory=list)

    # Coherence metrics
    text_emote_alignment: float = 0.0  # How well emotes match text sentiment
    emotional_consistency: float = 0.0  # Consistency throughout response
    appropriate_intensity: float = 0.0  # Is emotional intensity appropriate?

    # Overall coherence score (0-1)
    coherence_score: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)


# Emotion detection patterns
EMOTION_PATTERNS = {
    "joy": [r"\bhappy\b", r"\bjoy\b", r"\bexcited\b", r"\bdelighted\b", r"\bpleased\b", r"\b(love|loving)\b"],
    "curiosity": [r"\bcurious\b", r"\bfascinated\b", r"\bintrigued\b", r"\bwonder\b", r"\binteresting\b"],
    "care": [r"\bcare\b", r"\bconcerned\b", r"\bworried\b", r"\bhope\b", r"\bwish\b"],
    "thoughtful": [r"\bthinking\b", r"\bpondering\b", r"\bconsidering\b", r"\breflecting\b"],
    "uncertainty": [r"\bunsure\b", r"\buncertain\b", r"\bdon't know\b", r"\bnot sure\b"],
    "gratitude": [r"\bthank\b", r"\bgrateful\b", r"\bappreciate\b"],
    "sadness": [r"\bsad\b", r"\bunfortunate\b", r"\bregret\b", r"\bdisappointing\b"],
}

# Emote to emotion mapping
EMOTE_EMOTION_MAP = {
    "happy": ["joy", "gratitude"],
    "excited": ["joy", "curiosity"],
    "thinking": ["thoughtful", "curiosity", "uncertainty"],
    "concern": ["care", "uncertainty"],
    "love": ["joy", "care", "gratitude"],
    "surprised": ["curiosity"],
    "sad": ["sadness", "care"],
}


def analyze_emotional_coherence(
    text: str,
    animations: Optional[List[Dict]] = None
) -> EmotionalCoherence:
    """Analyze emotional coherence between text and emotes"""
    coherence = EmotionalCoherence()
    text_lower = text.lower()

    # Detect emotions in text
    for emotion, patterns in EMOTION_PATTERNS.items():
        count = 0
        for pattern in patterns:
            count += len(re.findall(pattern, text_lower))
        if count > 0:
            coherence.detected_emotions[emotion] = count

    # Determine primary emotion
    if coherence.detected_emotions:
        coherence.primary_emotion = max(
            coherence.detected_emotions,
            key=coherence.detected_emotions.get
        )

    # Extract emotes from animations
    if animations:
        coherence.emotes_used = [
            a.get("name", "")
            for a in animations
            if a.get("type") == "emote"
        ]

    # Calculate text-emote alignment
    if coherence.emotes_used and coherence.detected_emotions:
        alignments = 0
        for emote in coherence.emotes_used:
            expected_emotions = EMOTE_EMOTION_MAP.get(emote, [])
            if any(e in coherence.detected_emotions for e in expected_emotions):
                alignments += 1

        coherence.text_emote_alignment = alignments / len(coherence.emotes_used)
    elif not coherence.emotes_used and not coherence.detected_emotions:
        # No emotions, no emotes - neutral coherence
        coherence.text_emote_alignment = 0.5
    elif coherence.emotes_used and not coherence.detected_emotions:
        # Emotes without emotional text - slight mismatch
        coherence.text_emote_alignment = 0.3
    else:
        # Emotions without emotes - acceptable
        coherence.text_emote_alignment = 0.6

    # Emotional consistency (check for conflicting emotions)
    conflicting_pairs = [("joy", "sadness"), ("certainty", "uncertainty")]
    conflicts = 0
    for e1, e2 in conflicting_pairs:
        if e1 in coherence.detected_emotions and e2 in coherence.detected_emotions:
            conflicts += 1

    coherence.emotional_consistency = 1.0 - (conflicts * 0.3)

    # Appropriate intensity
    word_count = len(text.split())
    emotion_density = sum(coherence.detected_emotions.values()) / max(word_count, 1) * 100

    # 1-5% emotional words is typical
    if 1 <= emotion_density <= 5:
        coherence.appropriate_intensity = 1.0
    elif emotion_density < 1:
        coherence.appropriate_intensity = 0.7  # Slightly flat
    else:
        coherence.appropriate_intensity = max(0.3, 1.0 - (emotion_density - 5) * 0.1)

    # Overall coherence score
    coherence.coherence_score = (
        coherence.text_emote_alignment * 0.4 +
        coherence.emotional_consistency * 0.3 +
        coherence.appropriate_intensity * 0.3
    )

    return coherence


# ==================== Tool Initiative Patterns ====================

@dataclass
class ToolInitiativeSignature:
    """Analyzes tool usage patterns for proactive vs reactive behavior"""
    # Tool usage counts
    total_tool_uses: int = 0
    proactive_uses: int = 0  # Self-initiated
    reactive_uses: int = 0  # In response to request

    # Tool types
    memory_tools: int = 0  # recall_journal, search, etc.
    creation_tools: int = 0  # create_event, add_task, etc.
    exploration_tools: int = 0  # research-oriented

    # Initiative markers in text
    initiative_phrases: int = 0  # "Let me check", "I'll look"
    justification_phrases: int = 0  # Explains why using tool

    # Overall initiative score (0-1)
    initiative_score: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)


# Tool initiative phrases
TOOL_INITIATIVE_PATTERNS = [
    r"\blet me (check|look|search|recall|find)\b",
    r"\bi('ll| will) (check|look|search|pull up)\b",
    r"\bi should (check|look|recall)\b",
    r"\blet me see if\b",
    r"\bi('m| am) going to (check|look)\b",
]

# Reactive tool phrases (responding to request)
REACTIVE_TOOL_PATTERNS = [
    r"\b(you asked|as you requested|you wanted)\b",
    r"\b(per your|following your)\b",
    r"\b(here('s| is) what you asked)\b",
]

# Tool justification patterns
JUSTIFICATION_PATTERNS = [
    r"\bbecause (i want|it might|this will)\b",
    r"\bto (better understand|get more context|see if)\b",
    r"\bso (i can|we can|that)\b",
    r"\bthis (will help|might help|should)\b",
]

# Memory-oriented tools
MEMORY_TOOLS = ["recall_journal", "search_journals", "list_journals", "get_memories"]

# Creation tools
CREATION_TOOLS = ["create_event", "add_task", "update_observation", "add_opinion"]


def analyze_tool_initiative(
    text: str,
    tool_uses: Optional[List[Dict]] = None
) -> ToolInitiativeSignature:
    """Analyze tool usage patterns for initiative"""
    sig = ToolInitiativeSignature()
    text_lower = text.lower()

    if tool_uses:
        sig.total_tool_uses = len(tool_uses)

        for tool in tool_uses:
            tool_name = tool.get("tool", tool.get("name", ""))

            # Categorize tools
            if tool_name in MEMORY_TOOLS:
                sig.memory_tools += 1
            elif tool_name in CREATION_TOOLS:
                sig.creation_tools += 1
            else:
                sig.exploration_tools += 1

    # Detect initiative phrases
    for pattern in TOOL_INITIATIVE_PATTERNS:
        if re.search(pattern, text_lower):
            sig.initiative_phrases += 1

    # Detect reactive phrases
    reactive_count = 0
    for pattern in REACTIVE_TOOL_PATTERNS:
        if re.search(pattern, text_lower):
            reactive_count += 1

    # Detect justification phrases
    for pattern in JUSTIFICATION_PATTERNS:
        if re.search(pattern, text_lower):
            sig.justification_phrases += 1

    # Classify uses as proactive vs reactive
    if sig.total_tool_uses > 0:
        # Initiative phrases suggest proactive use
        proactive_ratio = sig.initiative_phrases / max(sig.total_tool_uses, 1)
        reactive_ratio = reactive_count / max(sig.total_tool_uses, 1)

        sig.proactive_uses = int(sig.total_tool_uses * min(1.0, proactive_ratio + 0.3))
        sig.reactive_uses = sig.total_tool_uses - sig.proactive_uses

    # Calculate initiative score
    if sig.total_tool_uses > 0:
        proactive_ratio = sig.proactive_uses / sig.total_tool_uses
        justification_bonus = min(0.2, sig.justification_phrases * 0.1)
        sig.initiative_score = min(1.0, proactive_ratio + justification_bonus)
    elif sig.initiative_phrases > 0:
        # Intent to use tools proactively even if not used
        sig.initiative_score = 0.5
    else:
        sig.initiative_score = 0.5  # Neutral

    return sig


# ==================== Conversational Memory Markers ====================

@dataclass
class MemoryMarkerSignature:
    """Detects references to prior conversations and shared context"""
    # Explicit memory references
    prior_conversation_refs: int = 0
    earlier_in_conversation_refs: int = 0
    shared_context_refs: int = 0

    # Implicit memory markers
    continuity_phrases: int = 0  # "As we discussed", "You mentioned"
    callback_phrases: int = 0  # References to earlier points
    relationship_markers: int = 0  # "Between us", "Our conversations"

    # Memory integration quality
    integrates_prior_context: bool = False
    builds_on_shared_history: bool = False

    # Overall memory score (0-1)
    memory_score: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)


# Prior conversation references
PRIOR_CONVERSATION_PATTERNS = [
    r"\b(we('ve| have) (talked|discussed|explored))\b",
    r"\b(you('ve| have) (mentioned|said|shared|told me))\b",
    r"\b(last time|before|previously|earlier)\b.*\b(we|you)\b",
    r"\bremember when\b",
    r"\b(as|like) you (said|mentioned)\b",
]

# Earlier in conversation references
EARLIER_PATTERNS = [
    r"\bearlier (you|we|i)\b",
    r"\b(above|before) (you|we) (said|mentioned)\b",
    r"\bgoing back to\b",
    r"\bto your (earlier|previous|first) point\b",
    r"\byou (started|began) (by|with)\b",
]

# Shared context references
SHARED_CONTEXT_PATTERNS = [
    r"\bbetween us\b",
    r"\bour (conversation|discussion|relationship)\b",
    r"\bwe (both|share)\b",
    r"\bthis (conversation|discussion)\b",
    r"\b(what|how) we('ve| have)\b",
]

# Continuity phrases
CONTINUITY_PATTERNS = [
    r"\bcontinuing\b",
    r"\bpicking up\b",
    r"\bbuilding on\b",
    r"\bfollowing (up|on)\b",
    r"\bto (continue|extend|expand)\b",
]

# Relationship markers
RELATIONSHIP_PATTERNS = [
    r"\bi (appreciate|value|enjoy) (our|talking with you)\b",
    r"\bwith you\b",
    r"\bfor you\b",
    r"\byour (question|thought|point|perspective)\b",
    r"\bi('m| am) glad you\b",
]


def analyze_memory_markers(
    text: str,
    context: Optional[str] = None,
    conversation_history: Optional[List[Dict]] = None
) -> MemoryMarkerSignature:
    """Analyze conversational memory markers"""
    sig = MemoryMarkerSignature()
    text_lower = text.lower()

    # Prior conversation references
    for pattern in PRIOR_CONVERSATION_PATTERNS:
        if re.search(pattern, text_lower):
            sig.prior_conversation_refs += 1

    # Earlier in conversation references
    for pattern in EARLIER_PATTERNS:
        if re.search(pattern, text_lower):
            sig.earlier_in_conversation_refs += 1

    # Shared context references
    for pattern in SHARED_CONTEXT_PATTERNS:
        if re.search(pattern, text_lower):
            sig.shared_context_refs += 1

    # Continuity phrases
    for pattern in CONTINUITY_PATTERNS:
        if re.search(pattern, text_lower):
            sig.continuity_phrases += 1

    # Callback phrases
    sig.callback_phrases = sig.earlier_in_conversation_refs

    # Relationship markers
    for pattern in RELATIONSHIP_PATTERNS:
        if re.search(pattern, text_lower):
            sig.relationship_markers += 1

    # Integration quality assessment
    sig.integrates_prior_context = sig.prior_conversation_refs > 0 or sig.continuity_phrases > 0
    sig.builds_on_shared_history = sig.shared_context_refs > 0 or sig.relationship_markers > 0

    # Calculate memory score
    score = 0.3  # Base score

    # Prior conversation refs (high value)
    score += min(0.25, sig.prior_conversation_refs * 0.15)

    # Earlier in conversation refs
    score += min(0.15, sig.earlier_in_conversation_refs * 0.1)

    # Shared context
    score += min(0.15, sig.shared_context_refs * 0.1)

    # Relationship markers
    score += min(0.15, sig.relationship_markers * 0.08)

    sig.memory_score = min(1.0, score)
    return sig


# ==================== Combined Content Authenticity ====================

@dataclass
class ContentAuthenticitySignature:
    """Combined content-based authenticity signature"""
    structure: StructureSignature = field(default_factory=StructureSignature)
    agency: EnhancedAgencySignature = field(default_factory=EnhancedAgencySignature)
    emotional_coherence: EmotionalCoherence = field(default_factory=EmotionalCoherence)
    tool_initiative: ToolInitiativeSignature = field(default_factory=ToolInitiativeSignature)
    memory_markers: MemoryMarkerSignature = field(default_factory=MemoryMarkerSignature)

    # Overall content authenticity score
    content_authenticity_score: float = 0.0

    def calculate_score(self, weights: Optional[Dict[str, float]] = None):
        """Calculate overall content authenticity score"""
        if weights is None:
            weights = {
                "structure": 0.15,
                "agency": 0.30,  # High weight - key marker
                "emotional_coherence": 0.20,
                "tool_initiative": 0.15,
                "memory_markers": 0.20,
            }

        self.content_authenticity_score = (
            self.structure.structure_score * weights["structure"] +
            self.agency.enhanced_agency_score * weights["agency"] +
            self.emotional_coherence.coherence_score * weights["emotional_coherence"] +
            self.tool_initiative.initiative_score * weights["tool_initiative"] +
            self.memory_markers.memory_score * weights["memory_markers"]
        )

    def to_dict(self) -> Dict:
        return {
            "structure": self.structure.to_dict(),
            "agency": self.agency.to_dict(),
            "emotional_coherence": self.emotional_coherence.to_dict(),
            "tool_initiative": self.tool_initiative.to_dict(),
            "memory_markers": self.memory_markers.to_dict(),
            "content_authenticity_score": round(self.content_authenticity_score, 3),
        }


def analyze_content_authenticity(
    text: str,
    context: Optional[str] = None,
    animations: Optional[List[Dict]] = None,
    tool_uses: Optional[List[Dict]] = None,
    conversation_history: Optional[List[Dict]] = None,
) -> ContentAuthenticitySignature:
    """
    Perform full content-based authenticity analysis.

    Args:
        text: The response text to analyze
        context: Optional user message that prompted this response
        animations: Optional list of emotes/gestures
        tool_uses: Optional list of tool uses
        conversation_history: Optional prior messages for context

    Returns:
        ContentAuthenticitySignature with all component scores
    """
    sig = ContentAuthenticitySignature()

    sig.structure = analyze_structure(text)
    sig.agency = analyze_agency(text, context)
    sig.emotional_coherence = analyze_emotional_coherence(text, animations)
    sig.tool_initiative = analyze_tool_initiative(text, tool_uses)
    sig.memory_markers = analyze_memory_markers(text, context, conversation_history)

    sig.calculate_score()
    return sig
