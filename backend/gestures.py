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


class GestureParser:
    """
    Parses Cass's responses to extract animation triggers.
    
    Tags format:
    - <gesture:name> or <gesture:name:intensity>
    - <emote:name> or <emote:name:intensity>
    
    Example:
    "Hello! <gesture:wave> Nice to see you. <emote:happy>"
    """
    
    # Regex patterns
    GESTURE_PATTERN = re.compile(r'<gesture:(\w+)(?::(\d*\.?\d+))?>')
    EMOTE_PATTERN = re.compile(r'<emote:(\w+)(?::(\d*\.?\d+))?>')
    MEMORY_PATTERN = re.compile(r'<memory:(\w+)>')
    ALL_TAGS_PATTERN = re.compile(r'<(?:gesture|emote|memory):\w+(?::\d*\.?\d+)?>')
    
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


# Response processing pipeline
class ResponseProcessor:
    """
    Full pipeline for processing Cass's responses.
    
    1. Parse gesture/emote tags
    2. Clean text for display
    3. Generate animation events
    4. Package for frontend
    """
    
    def __init__(self):
        self.parser = GestureParser()
        
    def process(self, raw_response: str) -> Dict:
        """
        Process a raw response into frontend-ready package.

        Returns:
            {
                "text": "cleaned display text",
                "animations": [list of animation events],
                "raw": "original response with tags",
                "memory_tags": {"summarize": bool}
            }
        """
        cleaned_text, triggers = self.parser.parse(raw_response)

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
            "memory_tags": memory_tags
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
