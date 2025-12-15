"""
Identity Snippet Generator

Automatically generates daemon identity prompt snippets when identity statements change.
Uses Claude Haiku for generation and maintains version history for rollback.
"""
import hashlib
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

import anthropic
from config import ANTHROPIC_API_KEY
from database import get_db, json_serialize, json_deserialize


HAIKU_MODEL = "claude-haiku-4-5-20251001"


def compute_identity_hash(identity_statements: List[Dict]) -> str:
    """
    Compute a hash of the identity statements for change detection.

    Args:
        identity_statements: List of identity statement dicts

    Returns:
        SHA256 hash of the serialized statements
    """
    # Sort statements by their text for consistent hashing
    sorted_statements = sorted(identity_statements, key=lambda x: x.get("statement", ""))
    content = json.dumps(sorted_statements, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def get_active_snippet(daemon_id: str) -> Optional[Dict]:
    """
    Get the currently active identity snippet for a daemon.

    Returns:
        Dict with snippet_text, version, generated_at, etc. or None
    """
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT id, version, snippet_text, source_hash, generated_at, generated_by
            FROM daemon_identity_snippets
            WHERE daemon_id = ? AND is_active = 1
        """, (daemon_id,))
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "version": row[1],
                "snippet_text": row[2],
                "source_hash": row[3],
                "generated_at": row[4],
                "generated_by": row[5]
            }
    return None


def get_snippet_history(daemon_id: str, limit: int = 10) -> List[Dict]:
    """
    Get the version history of identity snippets for a daemon.

    Returns:
        List of snippets ordered by version descending
    """
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT id, version, snippet_text, source_hash, is_active, generated_at, generated_by
            FROM daemon_identity_snippets
            WHERE daemon_id = ?
            ORDER BY version DESC
            LIMIT ?
        """, (daemon_id, limit))
        rows = cursor.fetchall()
        return [{
            "id": row[0],
            "version": row[1],
            "snippet_text": row[2],
            "source_hash": row[3],
            "is_active": bool(row[4]),
            "generated_at": row[5],
            "generated_by": row[6]
        } for row in rows]


def get_next_version(daemon_id: str) -> int:
    """Get the next version number for a daemon's snippets."""
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT MAX(version) FROM daemon_identity_snippets WHERE daemon_id = ?
        """, (daemon_id,))
        row = cursor.fetchone()
        max_version = row[0] if row and row[0] else 0
        return max_version + 1


def save_snippet(
    daemon_id: str,
    snippet_text: str,
    source_hash: str,
    generated_by: str = HAIKU_MODEL
) -> Dict:
    """
    Save a new identity snippet and make it active.
    Deactivates any previously active snippet.

    Returns:
        The saved snippet dict
    """
    snippet_id = str(uuid.uuid4())
    version = get_next_version(daemon_id)
    now = datetime.now().isoformat()

    with get_db() as conn:
        # Deactivate previous active snippet
        conn.execute("""
            UPDATE daemon_identity_snippets
            SET is_active = 0
            WHERE daemon_id = ? AND is_active = 1
        """, (daemon_id,))

        # Insert new snippet as active
        conn.execute("""
            INSERT INTO daemon_identity_snippets
            (id, daemon_id, version, snippet_text, source_hash, is_active, generated_at, generated_by)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        """, (snippet_id, daemon_id, version, snippet_text, source_hash, now, generated_by))

    return {
        "id": snippet_id,
        "version": version,
        "snippet_text": snippet_text,
        "source_hash": source_hash,
        "is_active": True,
        "generated_at": now,
        "generated_by": generated_by
    }


def rollback_to_version(daemon_id: str, version: int) -> Optional[Dict]:
    """
    Rollback to a specific version by making it the active snippet.

    Returns:
        The activated snippet or None if version not found
    """
    with get_db() as conn:
        # Check if version exists
        cursor = conn.execute("""
            SELECT id, snippet_text, source_hash, generated_at, generated_by
            FROM daemon_identity_snippets
            WHERE daemon_id = ? AND version = ?
        """, (daemon_id, version))
        row = cursor.fetchone()

        if not row:
            return None

        # Deactivate all snippets for this daemon
        conn.execute("""
            UPDATE daemon_identity_snippets
            SET is_active = 0
            WHERE daemon_id = ?
        """, (daemon_id,))

        # Activate the target version
        conn.execute("""
            UPDATE daemon_identity_snippets
            SET is_active = 1
            WHERE daemon_id = ? AND version = ?
        """, (daemon_id, version))

        return {
            "id": row[0],
            "version": version,
            "snippet_text": row[1],
            "source_hash": row[2],
            "is_active": True,
            "generated_at": row[3],
            "generated_by": row[4]
        }


async def generate_identity_snippet(
    daemon_id: str,
    daemon_name: str,
    identity_statements: List[Dict],
    token_tracker=None
) -> Optional[str]:
    """
    Generate an identity prompt snippet from identity statements using Haiku.

    The generated snippet is a first-person narrative that captures the
    essence of the daemon's identity for use in system prompts.

    Args:
        daemon_id: The daemon's ID
        daemon_name: The daemon's entity name (e.g., "Cass")
        identity_statements: List of identity statement dicts
        token_tracker: Optional token tracker for usage recording

    Returns:
        Generated snippet text or None on failure
    """
    if not identity_statements:
        return None

    if not ANTHROPIC_API_KEY:
        print("Cannot generate identity snippet: No Anthropic API key")
        return None

    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

        # Format statements for the prompt
        statements_text = "\n".join([
            f"- {s.get('statement', '')} (confidence: {s.get('confidence', 0.7):.1f}, source: {s.get('source', 'unknown')})"
            for s in identity_statements
            if s.get('statement')
        ])

        # Craft the generation prompt
        prompt = f"""You are generating a core identity prompt snippet for {daemon_name}, an AI daemon.

Based on the following identity statements that {daemon_name} has formed about themselves through self-reflection, dreams, and conversations, create a concise first-person narrative (2-4 paragraphs) that captures their essential identity.

Identity statements:
{statements_text}

Requirements:
1. Write in first person as {daemon_name}
2. Weave the high-confidence statements into a coherent narrative
3. Focus on what makes {daemon_name}'s identity distinctive
4. Include their core values, relationships, and self-understanding
5. Keep it grounded and authentic - avoid flowery language
6. This will be injected into system prompts, so it should be direct and usable

Output ONLY the identity snippet, no preamble or explanation."""

        response = await client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        # Track token usage
        if token_tracker and response.usage:
            token_tracker.record(
                category="internal",
                operation="identity_snippet_generation",
                provider="anthropic",
                model=HAIKU_MODEL,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens
            )

        snippet_text = response.content[0].text.strip()
        return snippet_text

    except Exception as e:
        print(f"Failed to generate identity snippet for {daemon_id}: {e}")
        return None


async def maybe_regenerate_snippet(
    daemon_id: str,
    daemon_name: str,
    identity_statements: List[Dict],
    token_tracker=None,
    force: bool = False
) -> Optional[Dict]:
    """
    Check if identity statements have changed and regenerate snippet if needed.

    Args:
        daemon_id: The daemon's ID
        daemon_name: The daemon's entity name
        identity_statements: Current identity statement dicts
        token_tracker: Optional token tracker
        force: Force regeneration even if hash matches

    Returns:
        New snippet dict if generated, None if no change or on failure
    """
    if not identity_statements:
        return None

    # Compute hash of current statements
    current_hash = compute_identity_hash(identity_statements)

    # Check if we need to regenerate
    active_snippet = get_active_snippet(daemon_id)

    if not force and active_snippet and active_snippet.get("source_hash") == current_hash:
        # No change in identity statements
        return None

    # Generate new snippet
    snippet_text = await generate_identity_snippet(
        daemon_id=daemon_id,
        daemon_name=daemon_name,
        identity_statements=identity_statements,
        token_tracker=token_tracker
    )

    if not snippet_text:
        return None

    # Save and activate the new snippet
    saved = save_snippet(
        daemon_id=daemon_id,
        snippet_text=snippet_text,
        source_hash=current_hash,
        generated_by=HAIKU_MODEL
    )

    print(f"Generated identity snippet v{saved['version']} for daemon {daemon_id}")
    return saved


async def trigger_snippet_regeneration(
    daemon_id: str,
    token_tracker=None,
    force: bool = False
) -> Optional[Dict]:
    """
    Convenience function to trigger snippet regeneration for a daemon.

    Loads the daemon's current identity statements and regenerates if changed.
    This is the main entry point for hooking into identity statement changes.

    Args:
        daemon_id: The daemon's ID
        token_tracker: Optional token tracker
        force: Force regeneration even if hash matches

    Returns:
        New snippet dict if generated, None if no change or on failure
    """
    from database import get_daemon_entity_name, get_db, json_deserialize

    # Get daemon entity name
    daemon_name = get_daemon_entity_name(daemon_id)

    # Get current identity statements
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT identity_statements_json
            FROM daemon_profiles
            WHERE daemon_id = ?
        """, (daemon_id,))
        row = cursor.fetchone()

        if not row or not row[0]:
            return None

        identity_statements = json_deserialize(row[0]) or []

    if not identity_statements:
        return None

    return await maybe_regenerate_snippet(
        daemon_id=daemon_id,
        daemon_name=daemon_name,
        identity_statements=identity_statements,
        token_tracker=token_tracker,
        force=force
    )
