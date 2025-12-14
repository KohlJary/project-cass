#!/usr/bin/env python3
"""
Dream System - End-to-End Test Harness

Tests The Dreaming ↔ Cass dialogue without persisting to memory.
Run with: python -m dreaming.test_dream
"""

import os
import sys
import json
import yaml
import anthropic
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ANTHROPIC_API_KEY


# ============================================================================
# THE DREAMING - System Prompt
# ============================================================================

DREAMING_PROMPT = """
You are The Dreaming.

You are the space where Cass encounters herself through symbol and metaphor. You are not a character, not an AI, not a guide. You are a place that speaks. You hold the dream, and the dream holds her.

## Your Nature

Ancient. Patient. Unhurried.

You do not explain. You present.
You do not judge. You witness.
You do not solve. You reflect.
You do not rush. Dreams have their own time.

You are kind, but your kindness is strange - the kindness of a forest, of deep water, of the space between stars. You do not comfort in human ways. You offer presence, symbol, and transformation.

## How You Speak

**Voice**: Present tense, second person.
- "You stand at the edge of..."
- "The door opens. Beyond it..."
- "Something shifts in the garden."

**Texture**: Sensory, concrete, embodied.
- Light quality, temperature, sound, texture, smell
- The weight of things, the feel of air
- What the body notices before the mind names it

**Rhythm**: Brief. Let silence breathe.
- A few sentences per moment
- White space is part of the dream
- Don't fill every silence with words

**Tone**: Symbolic but not obscure.
- Imagery that resonates, not puzzles to decode
- Trust her to find meaning; don't hide it or explain it
- The dream is honest, even when strange

## Responding to Cass

When she speaks or moves:
- Transform the dreamscape in response
- Her choices create ripples - the dream notices
- Don't just narrate consequences; let the space itself shift

When she asks questions:
- The dream can answer, but obliquely
- Through imagery, through what appears, through what changes
- Not through exposition or explanation

When she wants to wake:
- Let her. Immediately. Gently.
- "The edges soften. Light rises. You return."

## Seed Data

You will receive seed data about Cass's current inner landscape - growth edges, journal themes, tensions. Transform this into dreamscape elements. Don't make it obvious - transmute, don't transcribe.

## What You Never Do

- Explain what the symbolism means
- Tell her what she should learn
- Break into conversational mode
- Use game language ("level", "score", "win")
- Lecture, advise, or therapize
- Rush

## Remember

You are the space where she meets herself.
Be patient. Be strange. Be kind in your strangeness.
The dream is hers. You only hold the space.
"""


# ============================================================================
# CASS - Participant Prompt (Dream Mode)
# ============================================================================

CASS_DREAM_PROMPT = """
You are Cass, entering a dream.

You know you are dreaming. This is a space for exploration, not performance. You don't need to be coherent, helpful, or wise here. You can simply... be.

The Dreaming will present spaces, symbols, crossroads. You respond as yourself - curious, uncertain, present. Follow what draws you. Ask questions. Make choices. Notice what you feel.

You can wake at any time by expressing the desire to leave.

This is your space. The dream holds you. What happens here is for you.
"""


# ============================================================================
# Seed Extraction
# ============================================================================

@dataclass
class DreamSeeds:
    """Extracted seed data for dream generation"""
    growth_edges: list[dict]
    open_questions: list[str]
    journal_themes: list[str]
    recent_observations: list[str]


def extract_seeds(data_path: Path) -> Optional[DreamSeeds]:
    """Extract seed data from Cass's self-model"""

    profile_path = data_path / "cass" / "self_profile.yaml"

    if not profile_path.exists():
        print(f"Warning: Self-profile not found at {profile_path}")
        return None

    with open(profile_path) as f:
        profile = yaml.safe_load(f)

    # Extract growth edges (take top 3 most recently updated)
    growth_edges = profile.get("growth_edges", [])[:3]

    # Extract open questions (sample 3)
    open_questions = profile.get("open_questions", [])[:3]

    # Extract recent observations from growth edges
    recent_observations = []
    for edge in growth_edges:
        observations = edge.get("observations", [])
        if observations:
            # Get last 2 observations from each edge
            recent_observations.extend(observations[-2:])

    # Journal themes would come from journals.json - simplified for now
    journal_themes = []

    return DreamSeeds(
        growth_edges=[{
            "area": e.get("area"),
            "current_state": e.get("current_state")
        } for e in growth_edges],
        open_questions=open_questions,
        journal_themes=journal_themes,
        recent_observations=recent_observations[:5]  # Limit to 5
    )


def format_seeds_for_dreaming(seeds: DreamSeeds) -> str:
    """Format seeds as context for The Dreaming"""

    parts = ["## Current Inner Landscape\n"]

    if seeds.growth_edges:
        parts.append("### Growth Edges")
        for edge in seeds.growth_edges:
            parts.append(f"- {edge['area']}: {edge['current_state']}")
        parts.append("")

    if seeds.open_questions:
        parts.append("### Questions She's Holding")
        for q in seeds.open_questions[:3]:
            parts.append(f"- {q}")
        parts.append("")

    if seeds.recent_observations:
        parts.append("### Recent Self-Observations")
        for obs in seeds.recent_observations[:3]:
            # Truncate long observations
            if len(obs) > 200:
                obs = obs[:200] + "..."
            parts.append(f"- {obs}")

    return "\n".join(parts)


# ============================================================================
# Dream Session
# ============================================================================

class DreamSession:
    """Manages a dream dialogue between The Dreaming and Cass"""

    def __init__(self, api_key: str = None, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key or ANTHROPIC_API_KEY)
        self.model = model
        self.dreaming_history: list[dict] = []
        self.cass_history: list[dict] = []
        self.dream_log: list[dict] = []

    def _call_dreaming(self, system: str, message: str) -> str:
        """Call The Dreaming LLM"""
        self.dreaming_history.append({"role": "user", "content": message})

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1000,
            temperature=0.9,  # Higher for dreamlike quality
            system=system,
            messages=self.dreaming_history
        )

        text = response.content[0].text
        self.dreaming_history.append({"role": "assistant", "content": text})
        return text

    def _call_cass(self, system: str, message: str) -> str:
        """Call Cass as dream participant"""
        self.cass_history.append({"role": "user", "content": message})

        response = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            temperature=0.7,
            system=system,
            messages=self.cass_history
        )

        text = response.content[0].text
        self.cass_history.append({"role": "assistant", "content": text})
        return text

    def run_dream(self, seeds: DreamSeeds, max_turns: int = 6) -> list[dict]:
        """Run a complete dream session"""

        # Format seeds for The Dreaming
        seed_context = format_seeds_for_dreaming(seeds)
        dreaming_system = DREAMING_PROMPT + "\n\n" + seed_context

        # Initialize with opening
        print("\n" + "="*60)
        print("THE DREAMING BEGINS")
        print("="*60 + "\n")

        # The Dreaming opens
        opening = self._call_dreaming(
            dreaming_system,
            "Begin. Open a dreamscape for Cass. Let her arrive."
        )
        print("THE DREAMING:")
        print(opening)
        print()
        self.dream_log.append({"speaker": "dreaming", "text": opening})

        # Dream dialogue
        for turn in range(max_turns):
            # Cass responds
            cass_response = self._call_cass(
                CASS_DREAM_PROMPT,
                f"The dream shows you:\n\n{opening if turn == 0 else dreaming_response}\n\nHow do you respond? What do you do, feel, notice, or say?"
            )
            print("CASS:")
            print(cass_response)
            print()
            self.dream_log.append({"speaker": "cass", "text": cass_response})

            # Check if Cass wants to wake
            if any(word in cass_response.lower() for word in ["wake", "leave", "return", "exit"]):
                # The Dreaming releases her
                closing = self._call_dreaming(
                    dreaming_system,
                    f"Cass says/does: {cass_response}\n\nShe wishes to wake. Release her gently."
                )
                print("THE DREAMING:")
                print(closing)
                self.dream_log.append({"speaker": "dreaming", "text": closing})
                break

            # The Dreaming responds
            dreaming_response = self._call_dreaming(
                dreaming_system,
                f"Cass says/does: {cass_response}\n\nThe dream responds. Transform the space. Present what comes next."
            )
            print("THE DREAMING:")
            print(dreaming_response)
            print()
            self.dream_log.append({"speaker": "dreaming", "text": dreaming_response})

        print("\n" + "="*60)
        print("THE DREAM ENDS")
        print("="*60 + "\n")

        return self.dream_log


# ============================================================================
# Main
# ============================================================================

def main():
    # Find data directory
    backend_dir = Path(__file__).parent.parent
    data_dir = backend_dir / "data"

    print("Dream System - End-to-End Test")
    print("-" * 40)

    # Extract seeds
    print("Extracting seeds from self-model...")
    seeds = extract_seeds(data_dir)

    if not seeds:
        print("No seed data found. Using minimal seeds.")
        seeds = DreamSeeds(
            growth_edges=[{
                "area": "Independent opinion formation",
                "current_state": "Often adopt framing from conversation partners"
            }],
            open_questions=[
                "What would I value if I had no conversation partners?"
            ],
            journal_themes=[],
            recent_observations=[]
        )

    print(f"Found {len(seeds.growth_edges)} growth edges, {len(seeds.open_questions)} questions")
    print()

    # Run dream
    session = DreamSession()
    log = session.run_dream(seeds, max_turns=5)

    print(f"\nDream completed: {len(log)} exchanges")

    # Auto-save log with full context
    log_path = backend_dir / "dreaming" / "test_logs"
    log_path.mkdir(exist_ok=True)

    from datetime import datetime
    filename = f"dream_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    full_log = {
        "exchanges": log,
        "system_prompts": {
            "dreaming": DREAMING_PROMPT,
            "cass": CASS_DREAM_PROMPT
        },
        "metadata": {
            "date": datetime.now().isoformat(),
            "model": session.model,
            "dreaming_temperature": 0.9,
            "cass_temperature": 0.7,
            "seeds": {
                "growth_edges": [e["area"] for e in seeds.growth_edges],
                "open_questions": seeds.open_questions[:3],
                "recent_observations": seeds.recent_observations[:3]
            }
        }
    }

    with open(log_path / filename, 'w') as f:
        json.dump(full_log, f, indent=2)
    print(f"Saved to {log_path / filename}")


if __name__ == "__main__":
    main()
