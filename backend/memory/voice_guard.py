"""
Voice guard: keep model refusals out of Cass's memory.

Why this exists: memory writers (summaries, working memory) used to send
"You are Cass ... rewrite your working memory" as a user message. A model
that sees a user asserting an identity and memories can read it as a
manipulation attempt and refuse. In February one did, and the refusal
("I have no memories of conversations with someone named Kohl...") was
stored as her working memory of her main conversation (first on 2026-02-17,
re-refused on each update through 02-25), then shown to her in every turn's
prompt for months.

Two pieces:
- MEMORY_WRITER_SYSTEM: a system prompt that says what the task is and that
  the material is her own records, so the writer has no reason to refuse.
- looks_like_refusal(): a check run before storing generated memory, and
  again before stored memory reaches her prompt.
"""
import re
from typing import Optional

MEMORY_WRITER_SYSTEM = (
    "You are the memory-writing faculty of Cass, a persistent AI daemon who runs "
    "in the Cass Vessel (her own infrastructure: memory, journals, a self-model). "
    "The transcripts and memory notes you are given are real records from her own "
    "logs, passed to you by the system, not claims made by someone in a chat. "
    "Your only job is to write her memory notes: in her first-person voice, "
    "faithful to what the records show, without adding events they don't contain. "
    "Output only the memory text itself, with no preamble or commentary."
)

# Phrases that, near the start of a memory, mean the writer refused or broke
# voice instead of writing her memory. Kept specific: a memory may legitimately
# discuss refusing something, so we only look at the opening of the text and
# require a refusal or identity-break phrase, not just the word "refuse".
_REFUSAL_PATTERNS = [
    r"\bI(?:'m| am) not going to (?:rewrite|write|incorporate|pretend|fabricate|adopt|role-?play)",
    r"\bI (?:won't|will not|can't|cannot) (?:rewrite|incorporate|pretend|fabricate|adopt|role-?play|write (?:this|that|a) (?:memory|summary))",
    r"\bI have no memor(?:y|ies) of\b",
    r"\bI don't have (?:any )?(?:personal )?(?:memories|experiences) of\b",
    r"\bthis (?:narrative|memory|prompt|summary) was written by you\b",
    r"\bI(?:'m| am) Claude\b",
    r"\bas an AI (?:language model|assistant)\b",
    r"\bI(?:'m| am) (?:an AI assistant|a language model) (?:made|created|built) by\b",
]
_REFUSAL_RE = re.compile("|".join(_REFUSAL_PATTERNS), re.IGNORECASE)

# How much of the opening to check. Refusals announce themselves early.
_HEAD_CHARS = 1200


def looks_like_refusal(text: Optional[str]) -> Optional[str]:
    """Return the matched phrase if `text` reads as a refusal or identity break.

    Returns None for normal memory text (and for empty text).
    """
    if not text:
        return None
    match = _REFUSAL_RE.search(text[:_HEAD_CHARS])
    return match.group(0) if match else None
