"""
Memory Action Handlers - Conversation summarization and memory management.
"""

import logging
from typing import Any, Dict

from . import ActionResult

logger = logging.getLogger(__name__)


async def summarize_conversation_action(context: Dict[str, Any]) -> ActionResult:
    """
    Summarize a single conversation.

    Expects context to contain:
    - conversation_id: str (required)
    - managers.conversation_manager
    - managers.memory
    - managers.token_tracker (optional)
    """
    from summary_generation import generate_and_store_summary

    managers = context.get("managers", {})
    conversation_id = context.get("conversation_id")
    conversation_manager = managers.get("conversation_manager")
    memory = managers.get("memory")
    token_tracker = managers.get("token_tracker")

    if not conversation_id:
        return ActionResult(
            success=False,
            message="conversation_id required"
        )

    if not conversation_manager or not memory:
        return ActionResult(
            success=False,
            message="conversation_manager and memory required"
        )

    try:
        result = await generate_and_store_summary(
            conversation_id=conversation_id,
            memory=memory,
            conversation_manager=conversation_manager,
            token_tracker=token_tracker,
            force=False
        )

        logger.info(f"Summarized conversation {conversation_id[:8]}")
        return ActionResult(
            success=True,
            message=f"Summarized conversation {conversation_id[:8]}",
            cost_usd=context["definition"].estimated_cost_usd,
            data={
                "conversation_id": conversation_id,
                "summarized": True
            }
        )

    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        return ActionResult(
            success=False,
            message=f"Summarization failed: {e}"
        )


async def summarize_idle_conversations_action(context: Dict[str, Any]) -> ActionResult:
    """
    Find and summarize all idle conversations.

    Expects managers to contain:
    - conversation_manager
    - memory
    - token_tracker (optional)
    """
    from summary_generation import generate_and_store_summary

    managers = context.get("managers", {})
    conversation_manager = managers.get("conversation_manager")
    memory = managers.get("memory")
    token_tracker = managers.get("token_tracker")

    idle_minutes = context.get("idle_minutes", 30)
    min_unsummarized = context.get("min_unsummarized", 5)

    if not conversation_manager or not memory:
        return ActionResult(
            success=False,
            message="conversation_manager and memory required"
        )

    try:
        idle_conversations = conversation_manager.get_idle_conversations_needing_summary(
            idle_minutes=idle_minutes,
            min_unsummarized=min_unsummarized
        )

        if not idle_conversations:
            return ActionResult(
                success=True,
                message="No idle conversations needing summarization",
                cost_usd=0.0,
                data={"summarized_count": 0}
            )

        logger.info(f"Found {len(idle_conversations)} idle conversations")
        summarized = 0
        total_cost = 0.0

        for conv_id in idle_conversations:
            try:
                await generate_and_store_summary(
                    conversation_id=conv_id,
                    memory=memory,
                    conversation_manager=conversation_manager,
                    token_tracker=token_tracker,
                    force=False
                )
                summarized += 1
                total_cost += 0.01

            except Exception as e:
                logger.error(f"Failed to summarize {conv_id}: {e}")

        return ActionResult(
            success=True,
            message=f"Summarized {summarized}/{len(idle_conversations)} conversations",
            cost_usd=total_cost,
            data={
                "summarized_count": summarized,
                "total_found": len(idle_conversations)
            }
        )

    except Exception as e:
        logger.error(f"Idle summarization failed: {e}")
        return ActionResult(
            success=False,
            message=f"Idle summarization failed: {e}"
        )
