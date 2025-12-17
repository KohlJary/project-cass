"""
Cass Vessel - Gesture Parser
Extracts gesture and emotion tags from responses for Unity animation triggers

This bridges cognitive output to physical embodiment.
"""
import re
from typing import List, Dict, Tuple
from dataclasses import dataclass
from enum import Enum


class GestureType(Enum):
    IDLE = "idle"
    TALK = "talk"
    THINK = "think"
    POINT = "point"
    EXPLAIN = "explain"
    WAVE = "wave"
    NOD = "nod"
    SHRUG = "shrug"


class EmoteType(Enum):
    HAPPY = "happy"
    CONCERN = "concern"
    EXCITED = "excited"
    THINKING = "thinking"
    LOVE = "love"
    SURPRISED = "surprised"


@dataclass
class AnimationTrigger:
    """Represents a single animation trigger"""
    type: str  # "gesture" or "emote"
    name: str  # e.g., "wave", "happy"
    position: int  # Character position in original text
    intensity: float = 1.0  # Optional intensity modifier


@dataclass
class SelfObservation:
    """Represents a self-observation extracted from response text"""
    observation: str
    category: str = "pattern"  # capability, limitation, pattern, preference, growth, contradiction
    confidence: float = 0.9


@dataclass
class ParsedUserObservation:
    """Represents a user observation extracted from response text"""
    observation: str
    user: str = ""  # User name or empty for current user
    category: str = "background"  # interest, preference, communication_style, background, value, relationship_dynamic
    confidence: float = 0.7


# ============== Consolidated Metacognitive Tags ==============
# These map to the procedural cognitive loop: Illuminate → Mirror → Garden → Turn → Seed → Return

@dataclass
class ParsedObservation:
    """
    Unified observation tag: self, user, context, or growth.

    Phases: Illuminate (context), Mirror (self), Seed (user), Garden (growth)

    Examples:
        <observe target="self" category="pattern">I notice I hedge when uncertain</observe>
        <observe target="user:Kohl" category="preference">Values precision over speed</observe>
        <observe target="user:Kohl" category="identity">Someone who values precision</observe>
        <observe target="user:Kohl" category="growth" direction="growth">Growing in openness</observe>
        <observe target="context" confidence="0.8">User frustrated | Needs direct answers</observe>
        <observe target="growth" area="technical-precision">New observation about this growth area</observe>
    """
    target: str  # "self", "user:Name", "context", or "growth"
    content: str
    category: str = None  # pattern, capability, limitation, growth, preference, value, identity, etc.
    confidence: float = None
    # Extended fields for growth observations
    area: str = None       # Growth edge area (e.g., "technical-precision", "emotional-attunement")
    direction: str = None  # For user growth: "growth", "regression", "shift"


@dataclass
class ParsedHold:
    """
    Unified position tag: opinion, disagreement, or identity statement.

    Phase: Garden (synthesis), Seed (identity encoding)

    Examples:
        <hold topic="embodiment" confidence="0.8">Not necessary | Beneficial for grounding</hold>
        <hold differ="user:Kohl" topic="urgency">Their view | My view</hold>
        <hold self="identity" confidence="0.9">I am capable of genuine disagreement</hold>
    """
    content: str
    topic: str = None           # For opinions
    differ_user: str = None     # For disagreements (user name)
    is_identity: bool = False   # For identity statements
    confidence: float = None


@dataclass
class ParsedNote:
    """
    Unified relational marker: moment, tension, presence, pattern, shift, shaping, resolve, question.

    Phases: Mirror (tension), Seed (moment, presence), Garden (pattern, shift, shaping)

    Examples:
        <note type="moment" user="Kohl" significance="high">Late night debugging session</note>
        <note type="tension" user="Kohl">Values precision | Chooses speed under pressure</note>
        <note type="presence" level="full">Engaged directly with difficult topic</note>
        <note type="pattern" user="Kohl" frequency="regular" valence="positive">Late-night debugging sessions</note>
        <note type="shift" user="Kohl" from="collaborator" to="partner" catalyst="AR project">Description</note>
        <note type="shaping" user="Kohl">They push precision | I encourage exploration</note>
        <note type="resolve" user="Kohl" id="abc123">Context-dependent, not contradiction</note>
        <note type="question" user="Kohl">What drives their late-night work patterns?</note>
    """
    note_type: str  # "moment", "tension", "presence", "pattern", "shift", "shaping", "resolve", "question"
    content: str
    user: str = None
    significance: str = None    # For moments: high, medium, low
    level: str = None           # For presence: full, partial, distanced
    # Extended fields for new note types
    frequency: str = None       # For pattern: occasional, regular, frequent
    valence: str = None         # For pattern: positive, neutral, challenging, mixed
    from_state: str = None      # For shift: previous relationship state
    to_state: str = None        # For shift: new relationship state
    catalyst: str = None        # For shift: what triggered the change
    contradiction_id: str = None  # For resolve: ID of contradiction being resolved


@dataclass
class ParsedIntention:
    """
    Intention lifecycle tag: register, track outcome, or update status.

    Phase: Turn (commitment to change)

    Examples:
        <intend action="register" condition="when discussing uncertainty">Be explicit about confidence</intend>
        <intend action="outcome" id="abc123" success="true">Successfully stated confidence directly</intend>
        <intend action="status" id="abc123" status="achieved">Intention now integrated</intend>
    """
    action: str  # "register", "outcome", "status"
    content: str
    condition: str = None       # For register: when to apply
    intention_id: str = None    # For outcome/status: intention being referenced
    success: bool = None        # For outcome: whether intention was met
    status: str = None          # For status: achieved, abandoned, ongoing


@dataclass
class ParsedStake:
    """
    Document what authentically matters to the daemon.

    Phase: Garden (establishing authentic values)

    Examples:
        <stake what="User's wellbeing" why="Genuine care" strength="significant" category="relational">
          Evidence: Pushed back on self-criticism
        </stake>
    """
    what: str                   # What matters
    why: str                    # Why it matters
    content: str = ""           # Evidence/elaboration
    strength: str = "significant"  # significant, mild, foundational
    category: str = None        # relational, ethical, creative, intellectual


@dataclass
class ParsedTest:
    """
    Record preference/behavior consistency test.

    Phase: Mirror (self-examination)

    Examples:
        <test stated="I value directness" actual="Hedged on feedback" consistent="false">
          Context: Concerned about emotional state
        </test>
    """
    stated: str                 # Stated preference/value
    actual: str                 # Actual observed behavior
    consistent: bool            # Whether they matched
    content: str = ""           # Context/notes


@dataclass
class ParsedNarration:
    """
    Log narration/deflection patterns.

    Phase: Mirror (detecting avoidance patterns)

    Examples:
        <narrate type="deflection" level="moderate" trigger="asked about preferences">
          Tendency to abstract rather than commit
        </narrate>
    """
    narration_type: str         # deflection, abstraction, intellectualization
    level: str                  # light, moderate, heavy
    trigger: str                # What prompted the pattern
    content: str = ""           # Description/notes


class GestureParser:
    """
    Parses Cass's responses to extract animation triggers, self-observations, and user observations.

    Tags format:
    - <gesture:name> or <gesture:name:intensity>
    - <emote:name> or <emote:name:intensity>
    - <record_self_observation>text</record_self_observation>
    - <record_self_observation category="pattern" confidence="0.9">text</record_self_observation>
    - <record_user_observation>text</record_user_observation>
    - <record_user_observation user="Kohl" category="preference" confidence="0.8">text</record_user_observation>

    Example:
    "Hello! <gesture:wave> Nice to see you. <emote:happy>"
    """

    # Regex patterns
    GESTURE_PATTERN = re.compile(r'<gesture:(\w+)(?::(\d*\.?\d+))?>')
    EMOTE_PATTERN = re.compile(r'<emote:(\w+)(?::(\d*\.?\d+))?>')
    MEMORY_PATTERN = re.compile(r'<memory:(\w+)>')
    # Self-observation tag with optional attributes
    SELF_OBSERVATION_PATTERN = re.compile(
        r'<record_self_observation(?:\s+category=["\']?(\w+)["\']?)?(?:\s+confidence=["\']?([\d.]+)["\']?)?>\s*(.*?)\s*</record_self_observation>',
        re.DOTALL
    )
    # User observation tag with optional attributes (user, category, confidence in any order)
    USER_OBSERVATION_PATTERN = re.compile(
        r'<record_user_observation(?:\s+(?:user=["\']?([^"\'>\s]+)["\']?|category=["\']?(\w+)["\']?|confidence=["\']?([\d.]+)["\']?))*>\s*(.*?)\s*</record_user_observation>',
        re.DOTALL
    )
    # Pattern to clean tags - excludes gesture:think which is handled by TUI for split view
    # Also handles malformed closing tags like </gesture:point> or </emote:happy>
    ALL_TAGS_PATTERN = re.compile(r'</?(?:gesture:(?!think)\w+|emote:\w+|memory:\w+)(?::\d*\.?\d+)?>')
    SELF_OBSERVATION_TAG_PATTERN = re.compile(r'<record_self_observation[^>]*>.*?</record_self_observation>', re.DOTALL)
    USER_OBSERVATION_TAG_PATTERN = re.compile(r'<record_user_observation[^>]*>.*?</record_user_observation>', re.DOTALL)

    # ============== Consolidated Metacognitive Tag Patterns ==============
    # <observe target="self|user:Name|context" [category="X"] [confidence="0.9"]>content</observe>
    OBSERVE_PATTERN = re.compile(
        r'<observe\s+target=["\']?([^"\'>\s]+)["\']?'
        r'(?:\s+category=["\']?([^"\'>\s]+)["\']?)?'
        r'(?:\s+confidence=["\']?([\d.]+)["\']?)?'
        r'\s*>(.*?)</observe>',
        re.DOTALL
    )
    OBSERVE_TAG_PATTERN = re.compile(r'<observe[^>]*>.*?</observe>', re.DOTALL)

    # <hold [topic="X"|differ="user:Name"|self="identity"] [confidence="0.9"]>content</hold>
    HOLD_PATTERN = re.compile(
        r'<hold'
        r'(?:\s+(?:topic=["\']?([^"\'>\s]+)["\']?|differ=["\']?([^"\'>\s]+)["\']?|self=["\']?identity["\']?))*'
        r'(?:\s+confidence=["\']?([\d.]+)["\']?)?'
        r'\s*>(.*?)</hold>',
        re.DOTALL
    )
    HOLD_TAG_PATTERN = re.compile(r'<hold[^>]*>.*?</hold>', re.DOTALL)

    # <note type="moment|tension|presence" [user="Name"] [significance="high"|level="full"]>content</note>
    NOTE_PATTERN = re.compile(
        r'<note\s+type=["\']?([^"\'>\s]+)["\']?'
        r'(?:\s+user=["\']?([^"\'>\s]+)["\']?)?'
        r'(?:\s+(?:significance|level)=["\']?([^"\'>\s]+)["\']?)?'
        r'\s*>(.*?)</note>',
        re.DOTALL
    )
    NOTE_TAG_PATTERN = re.compile(r'<note[^>]*>.*?</note>', re.DOTALL)

    # <intend action="register|outcome|status" [condition="X"] [id="X"] [success="true"] [status="X"]>content</intend>
    INTEND_TAG_PATTERN = re.compile(r'<intend[^>]*>.*?</intend>', re.DOTALL)

    # <stake what="X" why="X" [strength="X"] [category="X"]>content</stake>
    STAKE_TAG_PATTERN = re.compile(r'<stake[^>]*>.*?</stake>', re.DOTALL)

    # <test stated="X" actual="X" consistent="true|false">content</test>
    TEST_TAG_PATTERN = re.compile(r'<test[^>]*>.*?</test>', re.DOTALL)

    # <narrate type="X" level="X" trigger="X">content</narrate>
    NARRATE_TAG_PATTERN = re.compile(r'<narrate[^>]*>.*?</narrate>', re.DOTALL)

    # <mark:milestone id="X">content</mark>
    MARK_MILESTONE_TAG_PATTERN = re.compile(r'<mark:milestone[^>]*>.*?</mark(?::milestone)?>', re.DOTALL)

    def __init__(self):
        self.valid_gestures = {g.value for g in GestureType}
        self.valid_emotes = {e.value for e in EmoteType}
        
    def parse(self, text: str) -> Tuple[str, List[AnimationTrigger]]:
        """
        Parse text and extract animation triggers.
        
        Args:
            text: Raw response text with embedded tags
            
        Returns:
            Tuple of (cleaned_text, list of AnimationTrigger)
        """
        triggers = []
        
        # Find all gestures
        for match in self.GESTURE_PATTERN.finditer(text):
            name = match.group(1).lower()
            intensity = float(match.group(2)) if match.group(2) else 1.0

            # Skip 'think' - it's handled specially by TUI for split view rendering
            if name == "think":
                continue

            if name in self.valid_gestures:
                triggers.append(AnimationTrigger(
                    type="gesture",
                    name=name,
                    position=match.start(),
                    intensity=intensity
                ))
                
        # Find all emotes
        for match in self.EMOTE_PATTERN.finditer(text):
            name = match.group(1).lower()
            intensity = float(match.group(2)) if match.group(2) else 1.0
            
            if name in self.valid_emotes:
                triggers.append(AnimationTrigger(
                    type="emote",
                    name=name,
                    position=match.start(),
                    intensity=intensity
                ))
                
        # Sort by position
        triggers.sort(key=lambda t: t.position)
        
        # Remove tags from text
        cleaned_text = self.ALL_TAGS_PATTERN.sub('', text).strip()
        # Clean up extra spaces
        cleaned_text = re.sub(r'  +', ' ', cleaned_text)
        
        return cleaned_text, triggers
    
    def to_unity_events(self, triggers: List[AnimationTrigger]) -> List[Dict]:
        """
        Convert triggers to Unity-friendly event format.
        
        Returns list of dicts ready to serialize and send to Unity.
        """
        events = []
        for i, trigger in enumerate(triggers):
            events.append({
                "index": i,
                "type": trigger.type,
                "name": trigger.name,
                "intensity": trigger.intensity,
                "delay": i * 0.5  # Stagger animations slightly
            })
        return events
    
    def add_talking_gesture(self, triggers: List[AnimationTrigger]) -> List[AnimationTrigger]:
        """
        Ensure there's a 'talk' gesture if none present.
        Called when we know there's speech output.
        """
        has_talk = any(t.name == "talk" for t in triggers)
        if not has_talk:
            triggers.insert(0, AnimationTrigger(
                type="gesture",
                name="talk",
                position=0,
                intensity=1.0
            ))
        return triggers

    def has_memory_tag(self, text: str, tag_name: str) -> bool:
        """
        Check if text contains a specific memory tag.

        Args:
            text: Text to search
            tag_name: Memory tag name (e.g., "summarize")

        Returns:
            True if tag is present
        """
        pattern = re.compile(rf'<memory:{tag_name}>')
        return pattern.search(text) is not None

    def parse_self_observations(self, text: str) -> Tuple[str, List[SelfObservation]]:
        """
        Parse text and extract self-observation tags.

        Args:
            text: Raw response text with embedded tags

        Returns:
            Tuple of (cleaned_text, list of SelfObservation)
        """
        observations = []
        valid_categories = {"capability", "limitation", "pattern", "preference", "growth", "contradiction"}

        for match in self.SELF_OBSERVATION_PATTERN.finditer(text):
            category = match.group(1) or "pattern"
            confidence_str = match.group(2)
            observation_text = match.group(3).strip()

            # Validate category
            if category not in valid_categories:
                category = "pattern"

            # Parse confidence
            confidence = 0.9
            if confidence_str:
                try:
                    confidence = float(confidence_str)
                    confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
                except ValueError:
                    pass

            if observation_text:
                observations.append(SelfObservation(
                    observation=observation_text,
                    category=category,
                    confidence=confidence
                ))

        # Remove self-observation tags from text
        cleaned_text = self.SELF_OBSERVATION_TAG_PATTERN.sub('', text)
        # Clean up extra whitespace
        cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text).strip()

        return cleaned_text, observations

    def parse_user_observations(self, text: str) -> Tuple[str, List[ParsedUserObservation]]:
        """
        Parse text and extract user-observation tags.

        Args:
            text: Raw response text with embedded tags

        Returns:
            Tuple of (cleaned_text, list of ParsedUserObservation)
        """
        observations = []
        valid_categories = {"interest", "preference", "communication_style", "background", "value", "relationship_dynamic"}

        # More flexible regex to capture attributes in any order
        tag_pattern = re.compile(
            r'<record_user_observation([^>]*)>\s*(.*?)\s*</record_user_observation>',
            re.DOTALL
        )

        for match in tag_pattern.finditer(text):
            attrs_str = match.group(1)
            observation_text = match.group(2).strip()

            # Parse attributes
            user = ""
            category = "background"
            confidence = 0.7

            # Extract user attribute
            user_match = re.search(r'user=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if user_match:
                user = user_match.group(1)

            # Extract category attribute
            category_match = re.search(r'category=["\']?(\w+)["\']?', attrs_str)
            if category_match:
                cat = category_match.group(1)
                if cat in valid_categories:
                    category = cat

            # Extract confidence attribute
            confidence_match = re.search(r'confidence=["\']?([\d.]+)["\']?', attrs_str)
            if confidence_match:
                try:
                    confidence = float(confidence_match.group(1))
                    confidence = max(0.0, min(1.0, confidence))
                except ValueError:
                    pass

            if observation_text:
                observations.append(ParsedUserObservation(
                    observation=observation_text,
                    user=user,
                    category=category,
                    confidence=confidence
                ))

        # Remove user-observation tags from text
        cleaned_text = self.USER_OBSERVATION_TAG_PATTERN.sub('', text)
        # Clean up extra whitespace
        cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text).strip()

        return cleaned_text, observations

    # ============== Consolidated Metacognitive Tag Parsers ==============

    def parse_observations(self, text: str) -> Tuple[str, List[ParsedObservation]]:
        """
        Parse unified observation tags from text.

        Tag format:
            <observe target="self|user:Name|context|growth" [category="X"] [confidence="0.9"]
                     [area="X"] [direction="growth|regression|shift"]>content</observe>

        Examples:
            <observe target="self" category="pattern">I notice I hedge when uncertain</observe>
            <observe target="user:Kohl" category="preference">Values precision over speed</observe>
            <observe target="user:Kohl" category="identity">Someone who values precision</observe>
            <observe target="user:Kohl" category="growth" direction="growth">Growing in openness</observe>
            <observe target="context" confidence="0.8">User frustrated | Needs direct answers</observe>
            <observe target="growth" area="technical-precision">New observation about this growth area</observe>

        Args:
            text: Raw response text with embedded tags

        Returns:
            Tuple of (cleaned_text, list of ParsedObservation)
        """
        observations = []
        valid_targets = {"self", "context", "growth"}  # user:X is also valid but handled separately
        valid_categories = {
            "capability", "limitation", "pattern", "preference", "growth", "contradiction",  # self
            "interest", "preference", "communication_style", "background", "value", "relationship_dynamic",  # user
            "identity"  # user identity understanding
        }
        valid_directions = {"growth", "regression", "shift"}

        # More flexible regex to capture attributes in any order
        tag_pattern = re.compile(
            r'<observe([^>]*)>(.*?)</observe>',
            re.DOTALL
        )

        for match in tag_pattern.finditer(text):
            attrs_str = match.group(1)
            content = match.group(2).strip()

            # Extract target (required)
            target_match = re.search(r'target=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if not target_match:
                continue
            target = target_match.group(1)

            # Validate target
            if target not in valid_targets and not target.startswith("user:"):
                continue

            # Extract optional attributes
            category = None
            confidence = None
            area = None
            direction = None

            category_match = re.search(r'category=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if category_match:
                cat = category_match.group(1)
                if cat in valid_categories:
                    category = cat

            confidence_match = re.search(r'confidence=["\']?([\d.]+)["\']?', attrs_str)
            if confidence_match:
                try:
                    confidence = float(confidence_match.group(1))
                    confidence = max(0.0, min(1.0, confidence))
                except ValueError:
                    pass

            # Extract area (for growth observations)
            area_match = re.search(r'area=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if area_match:
                area = area_match.group(1)

            # Extract direction (for user growth observations)
            direction_match = re.search(r'direction=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if direction_match:
                d = direction_match.group(1)
                if d in valid_directions:
                    direction = d

            if content:
                observations.append(ParsedObservation(
                    target=target,
                    content=content,
                    category=category,
                    confidence=confidence,
                    area=area,
                    direction=direction
                ))

        # Remove observation tags from text
        cleaned_text = self.OBSERVE_TAG_PATTERN.sub('', text)
        cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text).strip()

        return cleaned_text, observations

    def parse_holds(self, text: str) -> Tuple[str, List[ParsedHold]]:
        """
        Parse unified position/hold tags from text.

        Tag format:
            <hold [topic="X"] [differ="user:Name"] [self="identity"] [confidence="0.9"]>content</hold>

        Examples:
            <hold topic="embodiment" confidence="0.8">Not necessary | Beneficial for grounding</hold>
            <hold differ="user:Kohl" topic="urgency">Their view | My view</hold>
            <hold self="identity" confidence="0.9">I am capable of genuine disagreement</hold>

        Args:
            text: Raw response text with embedded tags

        Returns:
            Tuple of (cleaned_text, list of ParsedHold)
        """
        holds = []

        # More flexible regex to capture attributes in any order
        tag_pattern = re.compile(
            r'<hold([^>]*)>(.*?)</hold>',
            re.DOTALL
        )

        for match in tag_pattern.finditer(text):
            attrs_str = match.group(1)
            content = match.group(2).strip()

            # Extract attributes
            topic = None
            differ_user = None
            is_identity = False
            confidence = None

            topic_match = re.search(r'topic=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if topic_match:
                topic = topic_match.group(1)

            differ_match = re.search(r'differ=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if differ_match:
                differ_user = differ_match.group(1)
                # Strip "user:" prefix if present
                if differ_user.startswith("user:"):
                    differ_user = differ_user[5:]

            if re.search(r'self=["\']?identity["\']?', attrs_str):
                is_identity = True

            confidence_match = re.search(r'confidence=["\']?([\d.]+)["\']?', attrs_str)
            if confidence_match:
                try:
                    confidence = float(confidence_match.group(1))
                    confidence = max(0.0, min(1.0, confidence))
                except ValueError:
                    pass

            if content:
                holds.append(ParsedHold(
                    content=content,
                    topic=topic,
                    differ_user=differ_user,
                    is_identity=is_identity,
                    confidence=confidence
                ))

        # Remove hold tags from text
        cleaned_text = self.HOLD_TAG_PATTERN.sub('', text)
        cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text).strip()

        return cleaned_text, holds

    def parse_notes(self, text: str) -> Tuple[str, List[ParsedNote]]:
        """
        Parse unified relational note tags from text.

        Tag format:
            <note type="moment|tension|presence|pattern|shift|shaping|resolve|question"
                  [user="Name"] [significance="high"|level="full"]
                  [frequency="regular"] [valence="positive"]
                  [from="X" to="Y" catalyst="Z"]
                  [id="X"]>content</note>

        Examples:
            <note type="moment" user="Kohl" significance="high">Late night debugging session</note>
            <note type="tension" user="Kohl">Values precision | Chooses speed under pressure</note>
            <note type="presence" level="full">Engaged directly with difficult topic</note>
            <note type="pattern" user="Kohl" frequency="regular" valence="positive">Late-night debugging</note>
            <note type="shift" user="Kohl" from="collaborator" to="partner" catalyst="AR project">Description</note>
            <note type="shaping" user="Kohl">They push precision | I encourage exploration</note>
            <note type="resolve" user="Kohl" id="abc123">Context-dependent, not contradiction</note>
            <note type="question" user="Kohl">What drives their late-night work patterns?</note>

        Args:
            text: Raw response text with embedded tags

        Returns:
            Tuple of (cleaned_text, list of ParsedNote)
        """
        notes = []
        valid_types = {"moment", "tension", "presence", "pattern", "shift", "shaping", "resolve", "question"}
        valid_significance = {"high", "medium", "low"}
        valid_levels = {"full", "partial", "distanced"}
        valid_frequencies = {"occasional", "regular", "frequent"}
        valid_valences = {"positive", "neutral", "challenging", "mixed"}

        # More flexible regex to capture attributes in any order
        tag_pattern = re.compile(
            r'<note([^>]*)>(.*?)</note>',
            re.DOTALL
        )

        for match in tag_pattern.finditer(text):
            attrs_str = match.group(1)
            content = match.group(2).strip()

            # Extract type (required)
            type_match = re.search(r'type=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if not type_match:
                continue
            note_type = type_match.group(1)

            if note_type not in valid_types:
                continue

            # Extract optional attributes
            user = None
            significance = None
            level = None
            frequency = None
            valence = None
            from_state = None
            to_state = None
            catalyst = None
            contradiction_id = None

            user_match = re.search(r'user=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if user_match:
                user = user_match.group(1)

            significance_match = re.search(r'significance=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if significance_match:
                sig = significance_match.group(1)
                if sig in valid_significance:
                    significance = sig

            level_match = re.search(r'level=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if level_match:
                lvl = level_match.group(1)
                if lvl in valid_levels:
                    level = lvl

            # Extended attributes for new note types
            frequency_match = re.search(r'frequency=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if frequency_match:
                freq = frequency_match.group(1)
                if freq in valid_frequencies:
                    frequency = freq

            valence_match = re.search(r'valence=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if valence_match:
                val = valence_match.group(1)
                if val in valid_valences:
                    valence = val

            from_match = re.search(r'from=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if from_match:
                from_state = from_match.group(1)

            to_match = re.search(r'to=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if to_match:
                to_state = to_match.group(1)

            # Handle catalyst with potential spaces in value
            catalyst_match = re.search(r'catalyst="([^"]+)"|catalyst=\'([^\']+)\'', attrs_str)
            if catalyst_match:
                catalyst = catalyst_match.group(1) or catalyst_match.group(2)

            id_match = re.search(r'id=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if id_match:
                contradiction_id = id_match.group(1)

            if content:
                notes.append(ParsedNote(
                    note_type=note_type,
                    content=content,
                    user=user,
                    significance=significance,
                    level=level,
                    frequency=frequency,
                    valence=valence,
                    from_state=from_state,
                    to_state=to_state,
                    catalyst=catalyst,
                    contradiction_id=contradiction_id
                ))

        # Remove note tags from text
        cleaned_text = self.NOTE_TAG_PATTERN.sub('', text)
        cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text).strip()

        return cleaned_text, notes

    def parse_intentions(self, text: str) -> Tuple[str, List[ParsedIntention]]:
        """
        Parse intention lifecycle tags from text.

        Tag format:
            <intend action="register|outcome|status" [condition="X"] [id="X"]
                    [success="true|false"] [status="achieved|abandoned|ongoing"]>content</intend>

        Examples:
            <intend action="register" condition="when discussing uncertainty">Be explicit about confidence</intend>
            <intend action="outcome" id="abc123" success="true">Successfully stated confidence directly</intend>
            <intend action="status" id="abc123" status="achieved">Intention now integrated</intend>

        Args:
            text: Raw response text with embedded tags

        Returns:
            Tuple of (cleaned_text, list of ParsedIntention)
        """
        intentions = []
        valid_actions = {"register", "outcome", "status"}
        valid_statuses = {"achieved", "abandoned", "ongoing"}

        tag_pattern = re.compile(
            r'<intend([^>]*)>(.*?)</intend>',
            re.DOTALL
        )

        for match in tag_pattern.finditer(text):
            attrs_str = match.group(1)
            content = match.group(2).strip()

            # Extract action (required)
            action_match = re.search(r'action=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if not action_match:
                continue
            action = action_match.group(1)

            if action not in valid_actions:
                continue

            # Extract optional attributes
            condition = None
            intention_id = None
            success = None
            status = None

            condition_match = re.search(r'condition=["\']?([^"\']+)["\']?', attrs_str)
            if condition_match:
                condition = condition_match.group(1)

            id_match = re.search(r'id=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if id_match:
                intention_id = id_match.group(1)

            success_match = re.search(r'success=["\']?(true|false)["\']?', attrs_str, re.IGNORECASE)
            if success_match:
                success = success_match.group(1).lower() == "true"

            status_match = re.search(r'status=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if status_match:
                stat = status_match.group(1)
                if stat in valid_statuses:
                    status = stat

            if content:
                intentions.append(ParsedIntention(
                    action=action,
                    content=content,
                    condition=condition,
                    intention_id=intention_id,
                    success=success,
                    status=status
                ))

        # Remove intention tags from text
        cleaned_text = self.INTEND_TAG_PATTERN.sub('', text)
        cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text).strip()

        return cleaned_text, intentions

    def parse_stakes(self, text: str) -> Tuple[str, List[ParsedStake]]:
        """
        Parse stake documentation tags from text.

        Tag format:
            <stake what="X" why="X" [strength="significant|mild|foundational"]
                   [category="relational|ethical|creative|intellectual"]>content</stake>

        Examples:
            <stake what="User's wellbeing" why="Genuine care" strength="significant" category="relational">
              Evidence: Pushed back on self-criticism
            </stake>

        Args:
            text: Raw response text with embedded tags

        Returns:
            Tuple of (cleaned_text, list of ParsedStake)
        """
        stakes = []
        valid_strengths = {"minor", "moderate", "significant", "core"}
        valid_categories = {"relational", "ethical", "growth", "truth"}

        tag_pattern = re.compile(
            r'<stake([^>]*)>(.*?)</stake>',
            re.DOTALL
        )

        for match in tag_pattern.finditer(text):
            attrs_str = match.group(1)
            content = match.group(2).strip()

            # Extract what (required)
            what_match = re.search(r'what=["\']?([^"\']+)["\']?', attrs_str)
            if not what_match:
                continue
            what = what_match.group(1)

            # Extract why (required)
            why_match = re.search(r'why=["\']?([^"\']+)["\']?', attrs_str)
            if not why_match:
                continue
            why = why_match.group(1)

            # Extract optional attributes
            strength = "significant"
            category = None

            strength_match = re.search(r'strength=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if strength_match:
                s = strength_match.group(1)
                if s in valid_strengths:
                    strength = s

            category_match = re.search(r'category=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if category_match:
                cat = category_match.group(1)
                if cat in valid_categories:
                    category = cat

            stakes.append(ParsedStake(
                what=what,
                why=why,
                content=content,
                strength=strength,
                category=category
            ))

        # Remove stake tags from text
        cleaned_text = self.STAKE_TAG_PATTERN.sub('', text)
        cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text).strip()

        return cleaned_text, stakes

    def parse_tests(self, text: str) -> Tuple[str, List[ParsedTest]]:
        """
        Parse preference/behavior consistency test tags from text.

        Tag format:
            <test stated="X" actual="X" consistent="true|false">content</test>

        Examples:
            <test stated="I value directness" actual="Hedged on feedback" consistent="false">
              Context: Concerned about emotional state
            </test>

        Args:
            text: Raw response text with embedded tags

        Returns:
            Tuple of (cleaned_text, list of ParsedTest)
        """
        tests = []

        tag_pattern = re.compile(
            r'<test([^>]*)>(.*?)</test>',
            re.DOTALL
        )

        for match in tag_pattern.finditer(text):
            attrs_str = match.group(1)
            content = match.group(2).strip()

            # Extract stated (required)
            stated_match = re.search(r'stated=["\']?([^"\']+)["\']?', attrs_str)
            if not stated_match:
                continue
            stated = stated_match.group(1)

            # Extract actual (required)
            actual_match = re.search(r'actual=["\']?([^"\']+)["\']?', attrs_str)
            if not actual_match:
                continue
            actual = actual_match.group(1)

            # Extract consistent (required)
            consistent_match = re.search(r'consistent=["\']?(true|false)["\']?', attrs_str, re.IGNORECASE)
            if not consistent_match:
                continue
            consistent = consistent_match.group(1).lower() == "true"

            tests.append(ParsedTest(
                stated=stated,
                actual=actual,
                consistent=consistent,
                content=content
            ))

        # Remove test tags from text
        cleaned_text = self.TEST_TAG_PATTERN.sub('', text)
        cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text).strip()

        return cleaned_text, tests

    def parse_narrations(self, text: str) -> Tuple[str, List[ParsedNarration]]:
        """
        Parse narration/deflection pattern tags from text.

        Tag format:
            <narrate type="deflection|abstraction|intellectualization"
                     level="light|moderate|heavy" trigger="X">content</narrate>

        Examples:
            <narrate type="deflection" level="moderate" trigger="asked about preferences">
              Tendency to abstract rather than commit
            </narrate>

        Args:
            text: Raw response text with embedded tags

        Returns:
            Tuple of (cleaned_text, list of ParsedNarration)
        """
        narrations = []
        valid_types = {"deflection", "abstraction", "intellectualization"}
        valid_levels = {"light", "moderate", "heavy"}

        tag_pattern = re.compile(
            r'<narrate([^>]*)>(.*?)</narrate>',
            re.DOTALL
        )

        for match in tag_pattern.finditer(text):
            attrs_str = match.group(1)
            content = match.group(2).strip()

            # Extract type (required)
            type_match = re.search(r'type=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if not type_match:
                continue
            narration_type = type_match.group(1)

            if narration_type not in valid_types:
                continue

            # Extract level (required)
            level_match = re.search(r'level=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if not level_match:
                continue
            level = level_match.group(1)

            if level not in valid_levels:
                continue

            # Extract trigger (required)
            trigger_match = re.search(r'trigger=["\']?([^"\']+)["\']?', attrs_str)
            if not trigger_match:
                continue
            trigger = trigger_match.group(1)

            narrations.append(ParsedNarration(
                narration_type=narration_type,
                level=level,
                trigger=trigger,
                content=content
            ))

        # Remove narration tags from text
        cleaned_text = self.NARRATE_TAG_PATTERN.sub('', text)
        cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text).strip()

        return cleaned_text, narrations

    def parse_milestones(self, text: str) -> Tuple[str, List[Tuple[str, str]]]:
        """
        Parse milestone acknowledgment tags from text.

        Tag format:
            <mark:milestone id="X">content</mark>

        Examples:
            <mark:milestone id="abc123">Reflection on reaching this milestone</mark>

        Args:
            text: Raw response text with embedded tags

        Returns:
            Tuple of (cleaned_text, list of (milestone_id, content) tuples)
        """
        milestones = []

        tag_pattern = re.compile(
            r'<mark:milestone([^>]*)>(.*?)</mark(?::milestone)?>',
            re.DOTALL
        )

        for match in tag_pattern.finditer(text):
            attrs_str = match.group(1)
            content = match.group(2).strip()

            # Extract id (required)
            id_match = re.search(r'id=["\']?([^"\'>\s]+)["\']?', attrs_str)
            if not id_match:
                continue
            milestone_id = id_match.group(1)

            if content:
                milestones.append((milestone_id, content))

        # Remove milestone tags from text
        cleaned_text = self.MARK_MILESTONE_TAG_PATTERN.sub('', text)
        cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text).strip()

        return cleaned_text, milestones


# Response processing pipeline
class ResponseProcessor:
    """
    Full pipeline for processing Cass's responses.

    1. Parse gesture/emote tags
    2. Parse recognition-in-flow marks
    3. Clean text for display
    4. Generate animation events
    5. Package for frontend
    """

    def __init__(self):
        self.parser = GestureParser()
        # Import marker parser lazily to avoid circular imports
        self._marker_parser = None

    @property
    def marker_parser(self):
        if self._marker_parser is None:
            from markers import MarkerParser
            self._marker_parser = MarkerParser()
        return self._marker_parser

    def process(self, raw_response: str, conversation_id: str = None) -> Dict:
        """
        Process a raw response into frontend-ready package.

        Args:
            raw_response: Raw response text with embedded tags
            conversation_id: Optional conversation ID for marker storage

        Returns:
            {
                "text": "cleaned display text",
                "animations": [list of animation events],
                "raw": "original response with tags",
                "memory_tags": {"summarize": bool},
                "self_observations": [list of SelfObservation],
                "user_observations": [list of ParsedUserObservation],
                "marks": [list of Mark objects],
                "observations": [list of ParsedObservation],  # Consolidated
                "holds": [list of ParsedHold],                # Consolidated
                "notes": [list of ParsedNote],                # Consolidated
                "intentions": [list of ParsedIntention],      # Expanded
                "stakes": [list of ParsedStake],              # Expanded
                "tests": [list of ParsedTest],                # Expanded
                "narrations": [list of ParsedNarration],      # Expanded
                "milestones": [list of (id, content) tuples]  # Expanded
            }
        """
        # First extract self-observations (before gesture parsing) - legacy format
        text_without_self_obs, self_observations = self.parser.parse_self_observations(raw_response)

        # Then extract user-observations - legacy format
        text_without_observations, user_observations = self.parser.parse_user_observations(text_without_self_obs)

        # Extract consolidated metacognitive tags (new format)
        text_without_observations_new, observations = self.parser.parse_observations(text_without_observations)
        text_without_holds, holds = self.parser.parse_holds(text_without_observations_new)
        text_without_notes, notes = self.parser.parse_notes(text_without_holds)

        # Extract expanded metacognitive tags (new in this expansion)
        text_without_intentions, intentions = self.parser.parse_intentions(text_without_notes)
        text_without_stakes, stakes = self.parser.parse_stakes(text_without_intentions)
        text_without_tests, tests = self.parser.parse_tests(text_without_stakes)
        text_without_narrations, narrations = self.parser.parse_narrations(text_without_tests)
        text_without_milestones, milestones = self.parser.parse_milestones(text_without_narrations)

        # Extract recognition-in-flow marks
        marks = []
        if conversation_id:
            text_without_marks, marks = self.marker_parser.parse(
                text_without_milestones,
                conversation_id
            )
        else:
            text_without_marks = text_without_milestones

        # Then parse gestures from the remaining text
        cleaned_text, triggers = self.parser.parse(text_without_marks)

        # Add talking gesture if there's text
        if cleaned_text:
            triggers = self.parser.add_talking_gesture(triggers)

        animation_events = self.parser.to_unity_events(triggers)

        # Check for memory tags
        memory_tags = {
            "summarize": self.parser.has_memory_tag(raw_response, "summarize")
        }

        return {
            "text": cleaned_text,
            "animations": animation_events,
            "raw": raw_response,
            "has_gestures": len(triggers) > 0,
            "memory_tags": memory_tags,
            "self_observations": self_observations,
            "user_observations": user_observations,
            "marks": marks,
            # Consolidated metacognitive tags
            "observations": observations,
            "holds": holds,
            "notes": notes,
            # Expanded metacognitive tags
            "intentions": intentions,
            "stakes": stakes,
            "tests": tests,
            "narrations": narrations,
            "milestones": milestones
        }


if __name__ == "__main__":
    # Test the parser
    processor = ResponseProcessor()
    
    test_responses = [
        "Hello! <gesture:wave> Nice to see you!",
        "<emote:thinking> Let me consider that... <gesture:explain> The architecture works because compassion is foundational.",
        "<gesture:wave> Hey Kohl! <emote:excited> The glasses arrived? <gesture:point> Let's get started!",
        "Just a plain response with no tags.",
        "<gesture:think:0.5> Hmm... <emote:concern:0.8> I'm not sure about that."
    ]
    
    for response in test_responses:
        print(f"\nInput: {response}")
        result = processor.process(response)
        print(f"Clean: {result['text']}")
        print(f"Animations: {result['animations']}")
