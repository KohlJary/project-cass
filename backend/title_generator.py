"""
Auto-title generation for conversations.
Uses the unified LLM caller with configurable model assignment.
"""
from llm_caller import call_llm


async def generate_conversation_title(
    conversation_id: str,
    user_message: str,
    assistant_response: str,
    conversation_manager,
    token_tracker=None
) -> str:
    """
    Generate a title for a conversation based on the first exchange.
    Uses configured model for title_generation call site.

    This runs in the background after the first assistant response.
    Returns the generated title.
    """
    try:
        # Truncate for prompt
        user_preview = user_message[:500]
        assistant_preview = assistant_response[:500]

        response = await call_llm(
            call_site="title_generation",
            user_prompt=f"Generate a short, descriptive title (3-6 words) for a conversation that started with:\n\nUser: {user_preview}\n\nAssistant: {assistant_preview}\n\nRespond with ONLY the title, no quotes or punctuation.",
            max_tokens=50,
            temperature=0.7,
        )

        if not response.success:
            print(f"Failed to generate title: {response.error}")
            return None

        # Track token usage for title generation
        if token_tracker:
            token_tracker.record(
                category="internal",
                operation="title_generation",
                provider=response.provider,
                model=response.model_id,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                conversation_id=conversation_id
            )

        title = response.content.strip().strip('"').strip("'")

        # Ensure reasonable length
        if len(title) > 60:
            title = title[:57] + "..."

        # Update the conversation title
        conversation_manager.update_title(conversation_id, title)

        return title
    except Exception as e:
        print(f"Failed to generate title for {conversation_id}: {e}")
        return None
