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
    Generate nightly dream sequence using readiness-based seed selection.

    Expects managers to contain:
    - generate_nightly_dream: async function
    - self_manager: SelfModelManager
    - daemon_id: str (optional, will be detected if not provided)
    - data_dir: Path (legacy, kept for compatibility)
    """
    managers = context.get("managers", {})
    dream_func = managers.get("generate_nightly_dream")
    self_manager = managers.get("self_manager")
    daemon_id = managers.get("daemon_id")
    data_dir = managers.get("data_dir")

    if not dream_func:
        return ActionResult(
            success=False,
            message="generate_nightly_dream function not available"
        )

    if not self_manager:
        return ActionResult(
            success=False,
            message="self_manager not available"
        )

    try:
        dream_id = await dream_func(
            data_dir=data_dir,  # Kept for signature compatibility
            self_manager=self_manager,
            max_turns=4,
            daemon_id=daemon_id,
            selection_mode="resolution_ready",  # Use new readiness-based selection
        )

        if dream_id:
            logger.info(f"Nightly dream generated: {dream_id}")
            return ActionResult(
                success=True,
                message=f"Nightly dream generated",
                cost_usd=context["definition"].estimated_cost_usd,
                data={
                    "dream_id": dream_id,
                    "generated": True,
                    "selection_mode": "resolution_ready"
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


async def integrate_dream_action(context: Dict[str, Any]) -> ActionResult:
    """
    Integrate insights from the most recent unintegrated dream.

    This is a follow-up action to dream.nightly. It extracts insights
    from the dream and integrates them into the self-model.

    Expects managers to contain:
    - self_manager: SelfModelManager
    - daemon_id: str
    """
    managers = context.get("managers", {})
    self_manager = managers.get("self_manager")
    daemon_id = managers.get("daemon_id")

    if not self_manager:
        return ActionResult(
            success=False,
            message="self_manager not available"
        )

    # Resolve daemon_id if not provided
    if not daemon_id:
        daemon_id = getattr(self_manager, 'daemon_id', None)
    if not daemon_id:
        from database import get_db
        with get_db() as conn:
            cursor = conn.execute("SELECT id FROM daemons LIMIT 1")
            row = cursor.fetchone()
            daemon_id = row[0] if row else None

    if not daemon_id:
        return ActionResult(
            success=False,
            message="daemon_id not available"
        )

    try:
        from dreaming.integration import DreamManager
        from dreaming.insight_extractor import (
            DreamInsightExtractor,
            integrate_dream_insights
        )

        dream_manager = DreamManager(daemon_id)

        # Get most recent unintegrated dream
        recent_dreams = dream_manager.get_recent_dreams(limit=5)

        # Find first unintegrated dream
        dream_to_integrate = None
        for dream_summary in recent_dreams:
            dream_full = dream_manager.get_dream(dream_summary["id"])
            if dream_full and not dream_full.get("integrated"):
                dream_to_integrate = dream_full
                break

        if not dream_to_integrate:
            return ActionResult(
                success=True,
                message="No unintegrated dreams to process",
                cost_usd=0.0,
                data={"integrated": False, "reason": "no_unintegrated_dreams"}
            )

        dream_id = dream_to_integrate["id"]

        # Extract insights using the existing extractor
        extractor = DreamInsightExtractor()
        insights = extractor.extract_insights(dream_to_integrate)

        if not insights:
            logger.warning(f"Failed to extract insights from dream {dream_id}")
            return ActionResult(
                success=True,
                message=f"Could not extract insights from dream {dream_id}",
                cost_usd=context["definition"].estimated_cost_usd,
                data={"integrated": False, "reason": "extraction_failed"}
            )

        # Integrate insights into self-model
        updates = integrate_dream_insights(
            dream_id=dream_id,
            insights=insights,
            self_manager=self_manager,
            dry_run=False
        )

        # Mark dream as integrated
        from dataclasses import asdict
        dream_manager.mark_integrated(dream_id, insights=asdict(insights))

        logger.info(f"Integrated insights from dream {dream_id}")

        return ActionResult(
            success=True,
            message=f"Integrated insights from dream {dream_id}",
            cost_usd=context["definition"].estimated_cost_usd,
            data={
                "dream_id": dream_id,
                "integrated": True,
                "identity_statements_added": len(updates.get("identity_statements_added", [])),
                "growth_observations_added": len(updates.get("growth_observations_added", [])),
                "emerging_questions": len(insights.emerging_questions),
            }
        )

    except ImportError as e:
        logger.warning(f"insight_extractor not available: {e}")
        return ActionResult(
            success=True,
            message="Dream insight extraction not yet implemented",
            cost_usd=0.0,
            data={"integrated": False, "reason": "extractor_not_available"}
        )
    except Exception as e:
        logger.error(f"Dream integration failed: {e}")
        import traceback
        traceback.print_exc()
        return ActionResult(
            success=False,
            message=f"Dream integration failed: {e}"
        )
