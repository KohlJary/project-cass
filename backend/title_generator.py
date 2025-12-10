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
    conversation_manager,
    token_tracker=None
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
                "content": f"Generate a short, descriptive title (3-6 words) for a conversation that started with:\n\nUser: {user_preview}\n\nAssistant: {assistant_preview}\n\nRespond with ONLY the title, no quotes or punctuation."
            }]
        )

        # Track token usage for title generation
        if token_tracker and response.usage:
            token_tracker.record(
                category="internal",
                operation="title_generation",
                provider="anthropic",
                model="claude-3-5-haiku-latest",
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                conversation_id=conversation_id
            )

        title = response.content[0].text.strip().strip('"').strip("'")

        # Ensure reasonable length
        if len(title) > 60:
            title = title[:57] + "..."

        # Update the conversation title
        conversation_manager.update_title(conversation_id, title)

        return title
    except Exception as e:
        print(f"Failed to generate title for {conversation_id}: {e}")
        return None
