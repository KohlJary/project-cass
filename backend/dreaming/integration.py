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
    """Manages dream storage, retrieval, and integration using SQLite"""

    def __init__(self, daemon_id: str = None):
        self._daemon_id = daemon_id
        if not self._daemon_id:
            self._load_default_daemon()

    def _load_default_daemon(self):
        """Load default daemon ID from database"""
        from database import get_db
        with get_db() as conn:
            cursor = conn.execute("SELECT id FROM daemons LIMIT 1")
            row = cursor.fetchone()
            if row:
                self._daemon_id = row[0]

    def store_dream(
        self,
        exchanges: list[dict],
        seeds: dict,
        metadata: Optional[dict] = None
    ) -> str:
        """Store a completed dream and return its ID"""
        from database import get_db, json_serialize

        dream_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        now = datetime.now().isoformat()

        with get_db() as conn:
            conn.execute("""
                INSERT INTO dreams (
                    id, daemon_id, date, exchanges_json, seeds_json, metadata_json,
                    reflections_json, discussed, integrated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
            """, (
                dream_id,
                self._daemon_id,
                now[:10],  # Just the date
                json_serialize(exchanges),
                json_serialize(seeds),
                json_serialize(metadata or {}),
                json_serialize([]),
                now
            ))
            conn.commit()

        # Emit dream created event
        try:
            from state_bus import get_state_bus
            state_bus = get_state_bus(self._daemon_id)
            if state_bus:
                state_bus.emit_event(
                    event_type="journal.dream_generated",
                    data={
                        "timestamp": now,
                        "source": "dreaming",
                        "dream_id": dream_id,
                        "dream_date": now[:10],
                        "exchange_count": len(exchanges),
                        "seeds": list(seeds.keys()) if seeds else [],
                    }
                )
        except Exception as e:
            print(f"Warning: Failed to emit journal.dream_generated: {e}")

        return dream_id

    def get_dream(self, dream_id: str) -> Optional[dict]:
        """Retrieve a dream by ID"""
        from database import get_db, json_deserialize
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, date, exchanges_json, seeds_json, metadata_json,
                       reflections_json, discussed, integrated, integration_insights_json,
                       created_at
                FROM dreams
                WHERE daemon_id = ? AND id = ?
            """, (self._daemon_id, dream_id))
            row = cursor.fetchone()
            if not row:
                return None

            return {
                "id": row[0],
                "date": row[9] or row[1],  # Use created_at, fallback to date
                "exchanges": json_deserialize(row[2]) or [],
                "seeds": json_deserialize(row[3]) or {},
                "metadata": json_deserialize(row[4]) or {},
                "reflections": json_deserialize(row[5]) or [],
                "discussed": bool(row[6]),
                "integrated": bool(row[7]),
                "integration_insights": json_deserialize(row[8])
            }

    def get_recent_dreams(self, limit: int = 5) -> list[dict]:
        """Get most recent dreams"""
        from database import get_db, json_deserialize
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, date, exchanges_json, seeds_json, created_at
                FROM dreams
                WHERE daemon_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (self._daemon_id, limit))

            dreams = []
            for row in cursor.fetchall():
                exchanges = json_deserialize(row[2]) or []
                seeds = json_deserialize(row[3]) or {}
                dreams.append({
                    "id": row[0],
                    "date": row[4] or row[1],
                    "exchange_count": len(exchanges),
                    "seeds_summary": seeds.get("growth_edges", [])[:2]
                })
            return dreams

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
        from database import get_db, json_serialize, json_deserialize

        with get_db() as conn:
            cursor = conn.execute("""
                SELECT reflections_json FROM dreams
                WHERE daemon_id = ? AND id = ?
            """, (self._daemon_id, dream_id))
            row = cursor.fetchone()
            if not row:
                return

            reflections = json_deserialize(row[0]) or []
            reflections.append({
                "timestamp": datetime.now().isoformat(),
                "source": source,
                "content": reflection
            })

            conn.execute("""
                UPDATE dreams SET reflections_json = ?
                WHERE daemon_id = ? AND id = ?
            """, (json_serialize(reflections), self._daemon_id, dream_id))
            conn.commit()

    def mark_discussed(self, dream_id: str):
        """Mark a dream as having been discussed"""
        from database import get_db
        with get_db() as conn:
            conn.execute("""
                UPDATE dreams SET discussed = 1
                WHERE daemon_id = ? AND id = ?
            """, (self._daemon_id, dream_id))
            conn.commit()

    def mark_integrated(self, dream_id: str, insights: Optional[dict] = None):
        """Mark a dream's insights as integrated into self-model"""
        from database import get_db, json_serialize
        with get_db() as conn:
            conn.execute("""
                UPDATE dreams SET integrated = 1, integration_insights_json = ?
                WHERE daemon_id = ? AND id = ?
            """, (json_serialize(insights), self._daemon_id, dream_id))
            conn.commit()

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
