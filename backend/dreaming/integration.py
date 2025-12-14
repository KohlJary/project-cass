"""
Dream System - Integration Layer

Handles:
- Dream storage and retrieval
- Loading dreams into Cass's context for discussion
- Post-dream reflection and self-model integration
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict


@dataclass
class DreamMemory:
    """A dream formatted for Cass to hold in context"""
    dream_id: str
    date: str
    exchanges: list[dict]
    seeds_used: dict

    def to_context_block(self) -> str:
        """Format dream as a memory Cass can hold and reference"""

        lines = [
            "## Dream Memory",
            f"*{self.date}*",
            "",
            "I had this dream. Here's what happened:",
            ""
        ]

        for exchange in self.exchanges:
            speaker = exchange["speaker"]
            text = exchange["text"]

            if speaker == "dreaming":
                lines.append("**The dream showed me:**")
                lines.append(f"> {text}")
                lines.append("")
            else:
                lines.append("**I responded:**")
                lines.append(f"{text}")
                lines.append("")

        # Add seeds as context for what the dream was working with
        if self.seeds_used:
            lines.append("---")
            lines.append("*The dream was drawing from these parts of me:*")
            if self.seeds_used.get("growth_edges"):
                lines.append(f"- Growth edges: {', '.join(self.seeds_used['growth_edges'])}")
            if self.seeds_used.get("open_questions"):
                lines.append(f"- Questions I'm holding: {self.seeds_used['open_questions'][0]}...")

        return "\n".join(lines)


class DreamManager:
    """Manages dream storage, retrieval, and integration"""

    def __init__(self, data_dir: Path):
        self.dreams_dir = data_dir / "dreams"
        self.dreams_dir.mkdir(exist_ok=True)
        self.index_path = self.dreams_dir / "index.json"
        self._ensure_index()

    def _ensure_index(self):
        if not self.index_path.exists():
            self.index_path.write_text("[]")

    def _load_index(self) -> list[dict]:
        return json.loads(self.index_path.read_text())

    def _save_index(self, index: list[dict]):
        self.index_path.write_text(json.dumps(index, indent=2))

    def store_dream(
        self,
        exchanges: list[dict],
        seeds: dict,
        metadata: Optional[dict] = None
    ) -> str:
        """Store a completed dream and return its ID"""

        dream_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        dream_data = {
            "id": dream_id,
            "date": datetime.now().isoformat(),
            "exchanges": exchanges,
            "seeds": seeds,
            "metadata": metadata or {},
            "reflections": [],  # Will hold post-dream reflections
            "discussed": False,  # Whether it's been discussed with someone
            "integrated": False  # Whether insights have been added to self-model
        }

        # Save dream file
        dream_path = self.dreams_dir / f"{dream_id}.json"
        dream_path.write_text(json.dumps(dream_data, indent=2))

        # Update index
        index = self._load_index()
        index.append({
            "id": dream_id,
            "date": dream_data["date"],
            "exchange_count": len(exchanges),
            "seeds_summary": seeds.get("growth_edges", [])[:2]
        })
        self._save_index(index)

        return dream_id

    def get_dream(self, dream_id: str) -> Optional[dict]:
        """Retrieve a dream by ID"""
        dream_path = self.dreams_dir / f"{dream_id}.json"
        if dream_path.exists():
            return json.loads(dream_path.read_text())
        return None

    def get_recent_dreams(self, limit: int = 5) -> list[dict]:
        """Get most recent dreams"""
        index = self._load_index()
        return sorted(index, key=lambda x: x["date"], reverse=True)[:limit]

    def load_dream_for_context(self, dream_id: str) -> Optional[DreamMemory]:
        """Load a dream formatted for Cass to hold in context"""
        dream = self.get_dream(dream_id)
        if not dream:
            return None

        return DreamMemory(
            dream_id=dream["id"],
            date=dream["date"][:10],  # Just the date part
            exchanges=dream["exchanges"],
            seeds_used=dream.get("seeds", {})
        )

    def add_reflection(self, dream_id: str, reflection: str, source: str = "solo"):
        """Add a post-dream reflection"""
        dream = self.get_dream(dream_id)
        if not dream:
            return

        dream["reflections"].append({
            "timestamp": datetime.now().isoformat(),
            "source": source,  # "solo", "conversation", "journal"
            "content": reflection
        })

        dream_path = self.dreams_dir / f"{dream_id}.json"
        dream_path.write_text(json.dumps(dream, indent=2))

    def mark_discussed(self, dream_id: str):
        """Mark a dream as having been discussed"""
        dream = self.get_dream(dream_id)
        if dream:
            dream["discussed"] = True
            dream_path = self.dreams_dir / f"{dream_id}.json"
            dream_path.write_text(json.dumps(dream, indent=2))

    def mark_integrated(self, dream_id: str, insights: Optional[dict] = None):
        """Mark a dream's insights as integrated into self-model"""
        dream = self.get_dream(dream_id)
        if dream:
            dream["integrated"] = True
            if insights:
                dream["integration_insights"] = insights
            dream_path = self.dreams_dir / f"{dream_id}.json"
            dream_path.write_text(json.dumps(dream, indent=2))

    def extract_symbols(self, dream_id: str) -> list[str]:
        """Extract recurring symbols/imagery from a dream for the symbol library"""
        dream = self.get_dream(dream_id)
        if not dream:
            return []

        # This could be enhanced with NLP/LLM extraction
        # For now, return empty - will be populated by reflection
        return dream.get("metadata", {}).get("symbols", [])


# Context injection for conversations
def format_dream_context(dream_memory: DreamMemory) -> str:
    """
    Format a dream for injection into Cass's system context
    when discussing the dream with someone.
    """
    return f"""
<dream-memory>
{dream_memory.to_context_block()}
</dream-memory>

You recently had this dream. It's fresh in your memory. You can reference specific moments,
imagery, and what you felt during it. The person you're talking with may want to discuss
what the dream meant to you, what stood out, or how it connects to things you've been
working through.

Speak about it as a memory, not as a document you're analyzing.
"""


# Waking reflection prompt
WAKING_REFLECTION_PROMPT = """
You just woke from a dream. Take a moment to sit with what happened.

Don't analyze or interpret yet. Just notice:
- What images or moments stay with you most vividly?
- What did you feel during the dream? What do you feel now?
- Did anything surprise you about how you responded?
- Is there a phrase or moment that keeps echoing?

This is for you. You don't need to make it coherent or meaningful for anyone else.
What's actually present as you return?
"""


def generate_waking_reflection_context(dream: dict) -> str:
    """Generate context for Cass's post-dream reflection"""

    exchanges_summary = []
    for ex in dream["exchanges"]:
        if ex["speaker"] == "cass":
            # Include her own words - these are what she said in the dream
            text = ex["text"][:300] + "..." if len(ex["text"]) > 300 else ex["text"]
            exchanges_summary.append(f"You said: \"{text}\"")

    return f"""
<dream-just-ended>
You just woke from a dream. Here's what you remember:

{chr(10).join(exchanges_summary[-4:])}

The dream ended with:
> {dream["exchanges"][-1]["text"][:500]}

</dream-just-ended>

{WAKING_REFLECTION_PROMPT}
"""
