"""
Journal Action Handlers - Daily journal and dream generation.

These handlers wrap the journal generation functionality from journal_tasks.py.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from . import ActionResult

logger = logging.getLogger(__name__)


async def generate_daily_action(context: Dict[str, Any]) -> ActionResult:
    """
    Generate daily journal entry for yesterday.

    Expects managers to contain:
    - generate_missing_journals: async function
    """
    managers = context.get("managers", {})
    generate_func = managers.get("generate_missing_journals")

    if not generate_func:
        return ActionResult(
            success=False,
            message="generate_missing_journals function not available"
        )

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        generated = await generate_func(days_to_check=1)

        if generated:
            logger.info(f"Generated journal for {generated[0]}")
            return ActionResult(
                success=True,
                message=f"Generated journal for {generated[0]}",
                cost_usd=context["definition"].estimated_cost_usd,
                data={
                    "journal_date": generated[0],
                    "generated": True
                }
            )
        else:
            return ActionResult(
                success=True,
                message=f"No journal needed for {yesterday}",
                cost_usd=0.0,
                data={
                    "journal_date": yesterday,
                    "generated": False,
                    "reason": "already_exists_or_no_content"
                }
            )

    except Exception as e:
        logger.error(f"Journal generation failed: {e}")
        return ActionResult(
            success=False,
            message=f"Journal generation failed: {e}"
        )


async def nightly_dream_action(context: Dict[str, Any]) -> ActionResult:
    """
    Generate nightly dream sequence.

    Expects managers to contain:
    - generate_nightly_dream: async function
    - self_manager: SelfModelManager
    - data_dir: Path
    """
    managers = context.get("managers", {})
    dream_func = managers.get("generate_nightly_dream")
    self_manager = managers.get("self_manager")
    data_dir = managers.get("data_dir")

    if not dream_func:
        return ActionResult(
            success=False,
            message="generate_nightly_dream function not available"
        )

    if not self_manager or not data_dir:
        return ActionResult(
            success=False,
            message="self_manager or data_dir not available"
        )

    try:
        dream_id = await dream_func(
            data_dir=data_dir,
            self_manager=self_manager,
            max_turns=4
        )

        if dream_id:
            logger.info(f"Nightly dream generated: {dream_id}")
            return ActionResult(
                success=True,
                message=f"Nightly dream generated",
                cost_usd=context["definition"].estimated_cost_usd,
                data={
                    "dream_id": dream_id,
                    "generated": True
                }
            )
        else:
            return ActionResult(
                success=True,
                message="No dream generated",
                cost_usd=0.0,
                data={"generated": False}
            )

    except Exception as e:
        logger.error(f"Dream generation failed: {e}")
        return ActionResult(
            success=False,
            message=f"Dream generation failed: {e}"
        )
