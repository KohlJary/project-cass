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
                "marks": [list of Mark objects]
            }
        """
        # First extract self-observations (before gesture parsing)
        text_without_self_obs, self_observations = self.parser.parse_self_observations(raw_response)

        # Then extract user-observations
        text_without_observations, user_observations = self.parser.parse_user_observations(text_without_self_obs)

        # Extract recognition-in-flow marks
        marks = []
        if conversation_id:
            text_without_marks, marks = self.marker_parser.parse(
                text_without_observations,
                conversation_id
            )
        else:
            text_without_marks = text_without_observations

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
            "marks": marks
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
