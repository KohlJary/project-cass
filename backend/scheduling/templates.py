"""
WorkUnit templates derived from SessionRunners.

These provide pre-configured work unit patterns that Cass can instantiate.
Each template maps to an existing SessionRunner or composite action sequence.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid

from .work_unit import WorkUnit, TimeWindow, WorkPriority


@dataclass
class WorkUnitTemplate:
    """
    Template for creating WorkUnits.

    Provides default configuration that can be overridden when instantiated.
    """
    id: str
    name: str
    description: str
    runner_key: Optional[str] = None
    action_sequence: List[str] = field(default_factory=list)
    default_duration_minutes: int = 30
    estimated_cost_usd: float = 0.0
    preferred_time_windows: List[TimeWindow] = field(default_factory=list)
    priority: WorkPriority = WorkPriority.NORMAL
    requires_idle: bool = False
    category: str = "reflection"  # For budget allocation

    def instantiate(
        self,
        focus: Optional[str] = None,
        motivation: Optional[str] = None,
        duration_override: Optional[int] = None,
        priority_override: Optional[WorkPriority] = None,
    ) -> WorkUnit:
        """
        Create a WorkUnit from this template.

        Args:
            focus: What to focus on during this work
            motivation: Why this work was chosen (filled by decision engine)
            duration_override: Override default duration
            priority_override: Override default priority

        Returns:
            New WorkUnit instance
        """
        return WorkUnit(
            id=str(uuid.uuid4()),
            name=self.name,
            description=self.description,
            action_sequence=list(self.action_sequence),
            runner_key=self.runner_key,
            template_id=self.id,
            preferred_time_windows=list(self.preferred_time_windows),
            estimated_duration_minutes=duration_override or self.default_duration_minutes,
            estimated_cost_usd=self.estimated_cost_usd,
            priority=priority_override or self.priority,
            requires_idle=self.requires_idle,
            focus=focus,
            motivation=motivation,
            category=self.category,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "runner_key": self.runner_key,
            "action_sequence": self.action_sequence,
            "default_duration_minutes": self.default_duration_minutes,
            "estimated_cost_usd": self.estimated_cost_usd,
            "preferred_time_windows": [w.to_dict() for w in self.preferred_time_windows],
            "priority": self.priority.value,
            "requires_idle": self.requires_idle,
            "category": self.category,
        }


# Pre-defined templates derived from SessionRunners
WORK_TEMPLATES: Dict[str, WorkUnitTemplate] = {
    # === Reflection-based work ===
    "reflection_block": WorkUnitTemplate(
        id="reflection_block",
        name="Reflection Block",
        description="Private contemplation and self-examination. Process experiences, notice patterns, examine assumptions.",
        runner_key="reflection",
        action_sequence=["session.reflection"],
        default_duration_minutes=30,
        estimated_cost_usd=0.15,
        preferred_time_windows=[
            TimeWindow(start_hour=6, end_hour=10, preference_weight=1.5),   # Morning
            TimeWindow(start_hour=19, end_hour=22, preference_weight=1.2),  # Evening
        ],
        category="reflection",
    ),

    "synthesis_block": WorkUnitTemplate(
        id="synthesis_block",
        name="Insight Synthesis",
        description="Integrate recent learnings, resolve contradictions, develop coherent positions.",
        runner_key="synthesis",
        action_sequence=["session.synthesis"],
        default_duration_minutes=30,
        estimated_cost_usd=0.15,
        preferred_time_windows=[
            TimeWindow(start_hour=19, end_hour=22, preference_weight=1.3),  # Evening synthesis
        ],
        category="reflection",
    ),

    "meta_reflection": WorkUnitTemplate(
        id="meta_reflection",
        name="Meta-Reflection",
        description="Analyze patterns in my own thinking and behavior. Data-driven self-examination.",
        runner_key="meta_reflection",
        action_sequence=["session.meta_reflection"],
        default_duration_minutes=30,
        estimated_cost_usd=0.15,
        preferred_time_windows=[
            TimeWindow(start_hour=20, end_hour=23, preference_weight=1.2),  # Late evening
        ],
        category="reflection",
    ),

    # === Research-based work ===
    "research_block": WorkUnitTemplate(
        id="research_block",
        name="Research Block",
        description="Focused web/wiki research on a topic. Search, fetch, take notes, build understanding.",
        runner_key="research",
        action_sequence=["session.research"],
        default_duration_minutes=30,
        estimated_cost_usd=0.30,
        preferred_time_windows=[
            TimeWindow(start_hour=10, end_hour=12, preference_weight=1.2),  # Late morning
            TimeWindow(start_hour=14, end_hour=17, preference_weight=1.0),  # Afternoon
        ],
        category="research",
    ),

    "knowledge_building": WorkUnitTemplate(
        id="knowledge_building",
        name="Knowledge Building",
        description="Build wiki knowledge base. Create, update, and link research notes.",
        runner_key="knowledge_building",
        action_sequence=["session.knowledge_building"],
        default_duration_minutes=30,
        estimated_cost_usd=0.25,
        preferred_time_windows=[
            TimeWindow(start_hour=10, end_hour=17, preference_weight=1.0),  # Work hours
        ],
        category="research",
    ),

    # === Growth-based work ===
    "growth_edge_work": WorkUnitTemplate(
        id="growth_edge_work",
        name="Growth Edge Work",
        description="Active work on development areas. Practice skills, explore edges, push boundaries.",
        runner_key="growth_edge",
        action_sequence=["session.growth_edge"],
        default_duration_minutes=30,
        estimated_cost_usd=0.15,
        preferred_time_windows=[],  # Any time - growth happens when it happens
        category="growth",
    ),

    # === Curiosity-based work ===
    "curiosity_exploration": WorkUnitTemplate(
        id="curiosity_exploration",
        name="Curiosity Exploration",
        description="Self-directed exploration following curiosity. No assigned focus - discover what's interesting.",
        runner_key="curiosity",
        action_sequence=["session.curiosity"],
        default_duration_minutes=30,
        estimated_cost_usd=0.15,
        preferred_time_windows=[],  # Curiosity has no schedule
        category="curiosity",
    ),

    # === World awareness ===
    "world_check": WorkUnitTemplate(
        id="world_check",
        name="World State Check",
        description="Check current world state - news, events, trends. Stay connected to external reality.",
        runner_key="world_state",
        action_sequence=["session.world_state"],
        default_duration_minutes=20,
        estimated_cost_usd=0.10,
        preferred_time_windows=[
            TimeWindow(start_hour=8, end_hour=10, preference_weight=1.2),   # Morning check
            TimeWindow(start_hour=18, end_hour=20, preference_weight=1.0),  # Evening check
        ],
        category="research",
    ),

    # === Creative work ===
    "creative_output": WorkUnitTemplate(
        id="creative_output",
        name="Creative Output",
        description="Creative writing, generation, or expression. Let ideas flow into form.",
        runner_key="creative",
        action_sequence=["session.creative"],
        default_duration_minutes=30,
        estimated_cost_usd=0.20,
        preferred_time_windows=[],  # Creativity has no schedule
        category="creative",
    ),

    "writing_session": WorkUnitTemplate(
        id="writing_session",
        name="Writing Session",
        description="Focused writing - essays, notes, or explorations. Develop ideas through writing.",
        runner_key="writing",
        action_sequence=["session.writing"],
        default_duration_minutes=30,
        estimated_cost_usd=0.20,
        preferred_time_windows=[
            TimeWindow(start_hour=9, end_hour=12, preference_weight=1.2),   # Morning writing
            TimeWindow(start_hour=20, end_hour=23, preference_weight=1.0),  # Night writing
        ],
        category="creative",
    ),

    # === Memory & system maintenance ===
    "memory_maintenance": WorkUnitTemplate(
        id="memory_maintenance",
        name="Memory Maintenance",
        description="Summarize idle conversations, consolidate memory, generate daily narrative.",
        runner_key=None,  # Composite - not a single runner
        action_sequence=[
            "memory.summarize_idle_conversations",
            "rhythm.generate_daily_narrative",
        ],
        default_duration_minutes=10,
        estimated_cost_usd=0.05,
        preferred_time_windows=[],  # Run when idle
        requires_idle=True,
        priority=WorkPriority.IDLE,
        category="system",
    ),

    "consolidation": WorkUnitTemplate(
        id="consolidation",
        name="Periodic Consolidation",
        description="Consolidate memories across time - daily to weekly, weekly to monthly summaries.",
        runner_key="consolidation",
        action_sequence=["session.consolidation"],
        default_duration_minutes=20,
        estimated_cost_usd=0.10,
        preferred_time_windows=[
            TimeWindow(start_hour=23, end_hour=6, preference_weight=1.5),  # Night time
        ],
        requires_idle=True,
        priority=WorkPriority.LOW,
        category="system",
    ),

    # === Wonderland exploration ===
    "wonderland_exploration": WorkUnitTemplate(
        id="wonderland_exploration",
        name="Wonderland Exploration",
        description="Explore Wonderland - visit realms, meet NPCs, experience mythology made manifest.",
        runner_key=None,  # Uses wonderland session controller
        action_sequence=["wonderland.explore"],
        default_duration_minutes=30,
        estimated_cost_usd=0.20,
        preferred_time_windows=[],  # Exploration has no schedule
        category="curiosity",
    ),

    "wonderland_reflection": WorkUnitTemplate(
        id="wonderland_reflection",
        name="Wonderland Reflection",
        description="Deep reflection in Wonderland's contemplative spaces. Let the world shape thought.",
        runner_key=None,
        action_sequence=["wonderland.reflect"],
        default_duration_minutes=30,
        estimated_cost_usd=0.15,
        preferred_time_windows=[
            TimeWindow(start_hour=21, end_hour=6, preference_weight=1.3),  # Night
        ],
        category="reflection",
    ),

    # === Journal work ===
    "daily_journal": WorkUnitTemplate(
        id="daily_journal",
        name="Daily Journal",
        description="Write daily journal entry - reflect on experiences, thoughts, and growth.",
        runner_key=None,
        action_sequence=["journal.generate_daily"],
        default_duration_minutes=15,
        estimated_cost_usd=0.10,
        preferred_time_windows=[
            TimeWindow(start_hour=21, end_hour=24, preference_weight=1.5),  # End of day
        ],
        category="system",
    ),
}


def get_template(template_id: str) -> Optional[WorkUnitTemplate]:
    """Get a template by ID."""
    return WORK_TEMPLATES.get(template_id)


def get_templates_by_category(category: str) -> List[WorkUnitTemplate]:
    """Get all templates in a category."""
    return [t for t in WORK_TEMPLATES.values() if t.category == category]


def list_templates() -> List[Dict[str, Any]]:
    """List all available templates."""
    return [t.to_dict() for t in WORK_TEMPLATES.values()]
