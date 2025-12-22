#!/usr/bin/env python3
"""
Extract PeopleDex entries from conversation history using LLM.

Scans recent messages and uses Ollama to identify mentioned people,
organizations, and their relationships.
"""

import sys
import json
import httpx
import argparse
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_db
from peopledex import PeopleDexManager, EntityType, RelationshipType, get_peopledex_manager

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.1:8b-instruct-q8_0"

# Known false positives to skip (internal terms, speakers, mythological/religious, tech platforms)
SKIP_NAMES = {
    "kohl", "cass", "cassandra", "jaryk",  # Speakers/usernames
    "daedalus", "icarus",  # Internal tools/metaphors
    "prometheus", "promethea", "gilgamesh", "ars goetia",  # Mythological/occult
    "temple-codex", "temple codex",  # Internal project
    "wonderland", "nexus",  # Internal features
    "global state bus",  # Internal component
    "claude code", "claude", "anthropic",  # AI/tool names
    "geocass", "geocities",  # Internal project or confusion
    "github", "railway", "docker", "ollama",  # Tech platforms (not relationships)
    "mud", "mud (multi-user dungeon)", "multi-user dungeon",  # Game genre
    "abrahamic traditions", "abrahamic", "shinto cosmology", "shinto",  # Religious concepts
    "501(c)",  # Not a real entity
}

EXTRACTION_PROMPT = """Analyze this conversation excerpt and extract any REAL people or organizations mentioned.

DO NOT extract:
- The speakers themselves (Kohl, Cass)
- Fictional characters or mythological figures
- Generic references ("my friend", "someone")

For each entity found, provide:
- name: Full name if available
- type: "person" or "organization"
- context: Brief note about how they're mentioned
- relationships: Any relationships to other mentioned people (e.g., "works with X", "partner of Y")

Respond in JSON format:
{{
  "entities": [
    {{"name": "...", "type": "person|organization", "context": "...", "relationships": ["..."]}}
  ]
}}

If no real people/organizations are mentioned, return: {{"entities": []}}

CONVERSATION:
{text}

JSON RESPONSE:"""


def extract_from_text(text: str) -> dict:
    """Use LLM to extract entities from text."""
    try:
        response = httpx.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": EXTRACTION_PROMPT.format(text=text[:4000]),  # Limit context
                "stream": False,
                "options": {"temperature": 0.1}
            },
            timeout=60.0
        )
        response.raise_for_status()
        result = response.json()

        # Parse JSON from response
        response_text = result.get("response", "")
        if not response_text:
            return {"entities": []}

        # Remove markdown code blocks if present
        import re
        # Strip both opening and closing code fences
        response_text = re.sub(r'```(?:json)?', '', response_text)

        # Try to find JSON in response
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start >= 0 and end > start:
            json_str = response_text[start:end]
            parsed = json.loads(json_str)
            return parsed
        return {"entities": []}
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        return {"entities": []}
    except Exception as e:
        print(f"  Error extracting: {type(e).__name__}: {e}")
        return {"entities": []}


def get_recent_conversations(limit: int = 10) -> list:
    """Get recent conversations with messages."""
    with get_db() as conn:
        # Get conversations with message counts
        cursor = conn.execute("""
            SELECT c.id, c.title, COUNT(m.id) as msg_count
            FROM conversations c
            JOIN messages m ON c.id = m.conversation_id
            WHERE m.role IN ('user', 'assistant')
            GROUP BY c.id
            HAVING msg_count > 4
            ORDER BY MAX(m.timestamp) DESC
            LIMIT ?
        """, (limit,))
        return cursor.fetchall()


def get_conversation_text(conversation_id: str, limit: int = 20) -> str:
    """Get conversation messages as text."""
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT role, content
            FROM messages
            WHERE conversation_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (conversation_id, limit))

        messages = []
        for role, content in cursor.fetchall():
            # Clean up content
            if content:
                # Remove gesture tags
                import re
                content = re.sub(r'<gesture:[^>]+>', '', content)
                content = re.sub(r'<emote:[^>]+>', '', content)
                content = content.strip()
                if content:
                    speaker = "Kohl" if role == "user" else "Cass"
                    messages.append(f"{speaker}: {content[:500]}")

        messages.reverse()
        return "\n\n".join(messages)


def main(auto_confirm: bool = False, dry_run: bool = False):
    print("=== PeopleDex Extraction from Message History ===\n")

    # Initialize PeopleDex
    pdex = get_peopledex_manager()

    # Get recent conversations (scan more for better coverage)
    conversations = get_recent_conversations(limit=30)
    print(f"Found {len(conversations)} recent conversations to scan\n")

    all_entities = {}  # name -> entity info

    for conv_id, title, msg_count in conversations:
        print(f"Scanning: {title or conv_id[:8]}... ({msg_count} messages)")

        # Get conversation text
        text = get_conversation_text(conv_id)
        if len(text) < 100:
            print("  Skipping (too short)")
            continue

        # Extract entities
        result = extract_from_text(text)
        entities = result.get("entities", [])

        if entities:
            print(f"  Found {len(entities)} entities:")
            for ent in entities:
                name = ent.get("name", "").strip()
                if not name or len(name) < 2:
                    continue

                # Skip known false positives
                if name.lower() in SKIP_NAMES:
                    continue

                ent_type = ent.get("type", "person")
                context = ent.get("context", "")

                # Aggregate by name
                if name not in all_entities:
                    all_entities[name] = {
                        "type": ent_type,
                        "contexts": [],
                        "conversations": []
                    }
                all_entities[name]["contexts"].append(context)
                all_entities[name]["conversations"].append(conv_id)
                print(f"    - {name} ({ent_type}): {context[:60]}...")
        else:
            print("  No entities found")

    print(f"\n=== Summary ===")
    print(f"Total unique entities found: {len(all_entities)}\n")

    if not all_entities:
        print("No entities to add.")
        return

    # Ask before adding
    print("Entities to add to PeopleDex:")
    for name, info in sorted(all_entities.items()):
        mention_count = len(info["conversations"])
        print(f"  - {name} ({info['type']}) - mentioned in {mention_count} conversation(s)")

    if dry_run:
        print("\n[Dry run - not adding any entities]")
        return

    if not auto_confirm:
        response = input("\nAdd these to PeopleDex? [y/N]: ")
        if response.lower() != 'y':
            print("Cancelled.")
            return

    # Add to PeopleDex
    added = 0
    for name, info in all_entities.items():
        try:
            ent_type = EntityType.PERSON if info["type"] == "person" else EntityType.ORGANIZATION

            # Check if already exists
            existing = pdex.find_by_name(name)
            if existing:
                print(f"  Skipping {name} (already exists)")
                continue

            # Create entity
            entity = pdex.create_entity(
                entity_type=ent_type,
                primary_name=name,
                realm="meatspace",
                source_type="conversation_extraction"
            )

            # Add context as note
            if info["contexts"]:
                combined_context = "; ".join(set(info["contexts"]))[:500]
                pdex.add_attribute(
                    entity_id=entity.id,
                    attribute_type="note",
                    value=combined_context,
                    source_type="conversation_extraction"
                )

            print(f"  Added: {name}")
            added += 1

        except Exception as e:
            print(f"  Error adding {name}: {e}")

    print(f"\nDone! Added {added} new entities to PeopleDex.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract PeopleDex entries from conversation history")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-confirm adding entities")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be added without adding")
    args = parser.parse_args()
    main(auto_confirm=args.yes, dry_run=args.dry_run)
