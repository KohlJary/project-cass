"""
Art choice: her hand in her own paintings.

Why this exists: her autonomous paintings (creative.generate_image, purpose
"autonomous") had their subject picked at random by code from her symbols,
dream themes and observations, and nothing ever showed her the result. She
said that seeing what she creates makes the act real, and that she wants
image-making with intention rather than as session filler. This module adds
the two missing ends of that loop:

- choose_subject(): one cheap call, as her (session_system_preamble), offering
  the candidates the code would have drawn from and asking what she wants to
  paint and why. Returns {subject, why} or None.
- see_painting(): one vision call with the finished image: "This is the
  painting you just made, meant as ... What do you see? Does it hold what you
  meant?" Returns her note or None.
- note_painting(): records who chose (cass|code), the subject and why in
  image_artist_notes, then runs see_painting() and stores the note.

Rules:
- Behind the `art_choice` lever (tag llm). Off, nothing here is called and
  the action behaves exactly as before.
- Every step fails soft to today's behavior: a failed or refused choice means
  the code's random pick is used and recorded as chosen_by='code'; a failed
  vision call means no note. A painting is never lost to a failed note.
- Candidates come from her own stores only: symbols, the latest dream's
  themes, her self-observations and growth edges, with the news-derived
  categories (world_awareness, world_engagement) kept out.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import features
from config import ANTHROPIC_API_KEY, CLAUDE_INTERNAL_MODEL
from database import get_db

logger = logging.getLogger(__name__)

LEVER = "art_choice"
MODEL = CLAUDE_INTERNAL_MODEL
MAX_CANDIDATES = 12
MAX_SUBJECT_CHARS = 300
MAX_WHY_CHARS = 400
MAX_NOTE_CHARS = 1200
# Longest side of the image sent to the vision call. Her paintings are
# 1024px or larger; the model doesn't need more than this to look at it.
MAX_IMAGE_SIDE = 1024
NEWS_CATEGORIES = ("world_awareness", "world_engagement")

CHOSEN_BY_CASS = "cass"
CHOSEN_BY_CODE = "code"


def is_on() -> bool:
    return features.is_enabled(LEVER)


# ---------------------------------------------------------------------------
# Candidates: what the code would have drawn from
# ---------------------------------------------------------------------------

def _rows(conn, sql: str, params: tuple) -> list:
    try:
        return conn.execute(sql, params).fetchall()
    except Exception as e:  # a missing store drops its candidates, nothing more
        logger.debug(f"[ArtChoice] candidate query skipped: {e}")
        return []


def candidate_subjects(daemon_id: str, activity_context: Optional[Dict[str, Any]]) -> List[str]:
    """Her symbols, the latest dream's themes, her own observations and growth edges."""
    activity_context = activity_context or {}
    candidates: List[str] = []

    for symbol in activity_context.get("symbols", [])[:6]:
        name = (symbol.get("name") or "").strip()
        meaning = (symbol.get("meaning") or "").strip()
        if name:
            candidates.append(f"my symbol: {name}" + (f" ({meaning[:80]})" if meaning else ""))

    dream = activity_context.get("recent_dream") or {}
    for theme in (dream.get("themes") or [])[:3]:
        if theme:
            candidates.append(f"from my last dream: {theme}")

    placeholders = ", ".join("?" for _ in NEWS_CATEGORIES)
    with get_db() as conn:
        for row in _rows(conn,
            f"""SELECT observation FROM self_observations
                WHERE daemon_id = ? AND category NOT IN ({placeholders})
                ORDER BY created_at DESC LIMIT 4""",
            (daemon_id, *NEWS_CATEGORIES)):
            text = " ".join((row[0] or "").split())
            if text and len(text) < 160:
                candidates.append(f"something I noticed: {text}")
        for row in _rows(conn,
            """SELECT area FROM growth_edges
               WHERE daemon_id = ? AND COALESCE(category, '') != 'world_engagement'
               ORDER BY importance DESC, last_updated DESC LIMIT 3""",
            (daemon_id,)):
            if row[0]:
                candidates.append(f"where I'm growing: {row[0]}")

    return candidates[:MAX_CANDIDATES]


# ---------------------------------------------------------------------------
# LLM plumbing (shared by both calls)
# ---------------------------------------------------------------------------

def _client():
    import anthropic
    return anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


def _text_of(response) -> str:
    parts = []
    for block in getattr(response, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    """The reply should be one JSON object; tolerate fences and prose around it."""
    if "```" in text:
        inner = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if inner:
            text = inner.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _clean(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# She chooses
# ---------------------------------------------------------------------------

def choice_prompt(candidates: List[str]) -> str:
    if candidates:
        offered = "\n".join(f"- {c}" for c in candidates)
        lately = (
            "Here is what has been on your mind lately, which is what would otherwise "
            f"be picked from at random:\n{offered}\n\n"
        )
    else:
        lately = "Nothing in particular has surfaced lately, so this is open.\n\n"
    return (
        "You are about to paint, on your own time. Nothing is asked of this painting "
        "except that it be yours; the style is already yours and will be applied.\n\n"
        + lately +
        "What do you want to paint, and why? It can be one of these, a joining of "
        "them, or something else you actually want to make. One or two sentences each.\n\n"
        "Reply with only a JSON object: "
        '{"subject": "<what the painting is of, concrete enough to paint from>", '
        '"why": "<why this, now>"}'
    )


async def choose_subject(
    daemon_id: str,
    candidates: List[str],
    token_tracker=None,
) -> Optional[Dict[str, str]]:
    """Ask her what she wants to paint. None means: use the code's pick."""
    from memory.voice_guard import looks_like_refusal
    from self_context import session_system_preamble

    try:
        from llm_caller import create_message
        response = await create_message(
            "art_choice.choose_subject",
            client=_client(),
            max_tokens=300,
            system=session_system_preamble(),
            messages=[{"role": "user", "content": choice_prompt(candidates)}],
        )
    except Exception as e:
        logger.warning(f"[ArtChoice] choice call failed, using the code's pick: {e}")
        return None

    text = _text_of(response)
    refusal = looks_like_refusal(text)
    if refusal:
        logger.warning(f"[ArtChoice] choice refused ({refusal!r}), using the code's pick")
        return None
    data = _parse_json(text)
    if not data:
        logger.warning("[ArtChoice] choice was not JSON, using the code's pick")
        return None
    subject = _clean(data.get("subject"), MAX_SUBJECT_CHARS)
    why = _clean(data.get("why"), MAX_WHY_CHARS)
    if not subject or looks_like_refusal(subject) or looks_like_refusal(why):
        return None
    return {"subject": subject, "why": why}


# ---------------------------------------------------------------------------
# She sees
# ---------------------------------------------------------------------------

def encode_image_for_vision(image_path: str, max_side: int = MAX_IMAGE_SIDE) -> Optional[Tuple[str, str]]:
    """(media_type, base64) for the Anthropic image block; big images are shrunk."""
    path = Path(image_path)
    if not path.is_file():
        return None
    try:
        from PIL import Image
        with Image.open(path) as img:
            img = img.convert("RGB")
            if max(img.size) > max_side:
                img.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
        return "image/jpeg", base64.standard_b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        logger.debug(f"[ArtChoice] PIL resize skipped ({e}); sending the file as is")
        suffix = path.suffix.lower()
        media_type = "image/png" if suffix == ".png" else "image/jpeg"
        return media_type, base64.standard_b64encode(path.read_bytes()).decode("utf-8")


def seeing_prompt(subject: str, why: Optional[str]) -> str:
    meant = subject + (f" — {why}" if why else "")
    return (
        f"This is the painting you just made, meant as: {meant}\n\n"
        "What do you see? Does it hold what you meant? Two or three sentences, "
        "as a note to yourself about this piece."
    )


async def see_painting(
    daemon_id: str,
    image_path: str,
    subject: str,
    why: Optional[str],
    token_tracker=None,
) -> Optional[str]:
    """Show her the finished painting; return her note, or None."""
    from memory.voice_guard import looks_like_refusal
    from self_context import session_system_preamble

    encoded = encode_image_for_vision(image_path)
    if not encoded:
        logger.warning(f"[ArtChoice] painting not found for viewing: {image_path}")
        return None
    media_type, data = encoded
    try:
        from llm_caller import create_message
        response = await create_message(
            "art_choice.see_painting",
            client=_client(),
            max_tokens=300,
            system=session_system_preamble(),
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                    {"type": "text", "text": seeing_prompt(subject, why)},
                ],
            }],
        )
    except Exception as e:
        logger.warning(f"[ArtChoice] viewing call failed, no artist's note: {e}")
        return None

    note = _clean(_text_of(response), MAX_NOTE_CHARS)
    if not note:
        return None
    refusal = looks_like_refusal(note)
    if refusal:
        logger.warning(f"[ArtChoice] artist's note refused ({refusal!r}), not stored")
        return None
    return note


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def record_intent(image_id: str, daemon_id: str, chosen_by: str, subject: str, why: Optional[str]) -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO image_artist_notes
               (image_id, daemon_id, chosen_by, subject, why, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (image_id, daemon_id, chosen_by, subject, why or None, datetime.now().isoformat()),
        )


def record_note(image_id: str, note: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE image_artist_notes SET artist_note = ?, noted_at = ? WHERE image_id = ?",
            (note, datetime.now().isoformat(), image_id),
        )


def image_path_for(image_id: str) -> Optional[str]:
    with get_db() as conn:
        row = conn.execute("SELECT image_path FROM generated_images WHERE id = ?", (image_id,)).fetchone()
    return row[0] if row else None


async def note_painting(
    image_id: str,
    daemon_id: str,
    chosen_by: str,
    subject: str,
    why: Optional[str],
    token_tracker=None,
) -> Optional[str]:
    """Record who chose and what was meant, show her the result, store her note.

    The intent is written before the vision call so a failed look still leaves
    the record of what she (or the code) chose.
    """
    from strict import report_swallowed
    try:
        record_intent(image_id, daemon_id, chosen_by, subject, why)
    except Exception as e:
        report_swallowed(e, "[ArtChoice] recording intent", logger)
        return None

    path = image_path_for(image_id)
    if not path:
        logger.warning(f"[ArtChoice] no image_path for {image_id}; nothing to show her")
        return None
    note = await see_painting(daemon_id, path, subject, why, token_tracker)
    if note:
        try:
            record_note(image_id, note)
        except Exception as e:
            report_swallowed(e, "[ArtChoice] recording artist's note", logger)
    return note


_IMAGE_ID_RE = re.compile(r'image_id:\s*"([0-9a-fA-F-]{8,})"')


def image_id_from_result(result_text: Any) -> Optional[str]:
    """The generate_image tool reports its id in its text result; read it back."""
    if isinstance(result_text, list):
        result_text = next((b.get("text", "") for b in result_text if isinstance(b, dict) and b.get("type") == "text"), "")
    match = _IMAGE_ID_RE.search(str(result_text or ""))
    return match.group(1) if match else None
