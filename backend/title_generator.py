"""
Auto-title generation for conversations.
Uses a fast, cheap API call to create concise titles.
"""
import anthropic
from config import ANTHROPIC_API_KEY


async def generate_conversation_title(
    conversation_id: str,
    user_message: str,
    assistant_response: str,
    conversation_manager
) -> str:
    """
    Generate a title for a conversation based on the first exchange.
    Uses Claude haiku for fast, cheap title generation.

    This runs in the background after the first assistant response.
    Returns the generated title.
    """
    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

        # Truncate for prompt
        user_preview = user_message[:500]
        assistant_preview = assistant_response[:500]

        response = await client.messages.create(
            model="claude-3-5-haiku-latest",
            max_tokens=50,
            messages=[{
                "role": "user",
                "content": f"""Generate a short, descriptive title (3-6 words) for a conversation that started with:

User: {user_preview}
