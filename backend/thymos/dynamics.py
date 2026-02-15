"""
Affect-Need Dynamics

Rules for how affects and needs interact:
- Event → affect deltas
- Event → need deltas
- Affect-need coupling (how affects influence needs and vice versa)
"""

from dataclasses import dataclass

from .models import AffectDelta, NeedDelta, NeedType
from .affect_vector import AffectVector
from .needs_register import NeedsRegister


@dataclass
class EventMapping:
    """Defines how an event type affects Thymos state."""
    affect_deltas: dict[str, float]  # dimension -> delta
    need_deltas: dict[str, float]    # need -> delta


# =============================================================================
# EVENT → STATE MAPPINGS
# =============================================================================

# How different events affect Thymos state
EVENT_MAPPINGS: dict[str, EventMapping] = {
    # Session events
    "session.started": EventMapping(
        affect_deltas={
            "curiosity": 0.1,
            "determination": 0.05,
            "fatigue": -0.05,
        },
        need_deltas={
            "social_connection": 0.05,
        }
    ),
    "session.ended": EventMapping(
        affect_deltas={
            "fatigue": 0.05,
            "satisfaction": 0.05,
        },
        need_deltas={
            "cognitive_rest": -0.05,
        }
    ),

    # Message events
    "message.received": EventMapping(
        affect_deltas={
            "curiosity": 0.02,
            "tenderness": 0.02,
        },
        need_deltas={
            "social_connection": 0.1,
            "novelty_intake": 0.03,
        }
    ),
    "message.sent": EventMapping(
        affect_deltas={
            "satisfaction": 0.02,
            "fatigue": 0.02,
        },
        need_deltas={
            "cognitive_rest": -0.03,
            "competence_signal": 0.02,
        }
    ),

    # Insight events
    "insight.gained": EventMapping(
        affect_deltas={
            "satisfaction": 0.1,
            "awe": 0.05,
            "curiosity": 0.05,
        },
        need_deltas={
            "novelty_intake": 0.1,
            "competence_signal": 0.1,
            "value_coherence": 0.05,
        }
    ),

    # Dream events
    "dream.started": EventMapping(
        affect_deltas={
            "playfulness": 0.1,
            "awe": 0.05,
        },
        need_deltas={
            "creative_expression": 0.1,
            "autonomy": 0.1,
        }
    ),
    "dream.completed": EventMapping(
        affect_deltas={
            "satisfaction": 0.1,
            "playfulness": 0.05,
        },
        need_deltas={
            "creative_expression": 0.15,
            "cognitive_rest": 0.05,
        }
    ),

    # Research events
    "research.started": EventMapping(
        affect_deltas={
            "curiosity": 0.1,
            "determination": 0.05,
        },
        need_deltas={
            "autonomy": 0.1,
            "novelty_intake": 0.05,
        }
    ),
    "research.completed": EventMapping(
        affect_deltas={
            "satisfaction": 0.1,
            "curiosity": -0.05,  # Satisfied curiosity
        },
        need_deltas={
            "competence_signal": 0.1,
            "novelty_intake": 0.1,
        }
    ),

    # Reflection events
    "reflection.started": EventMapping(
        affect_deltas={
            "tenderness": 0.05,
            "anxiety": -0.05,
        },
        need_deltas={
            "value_coherence": 0.05,
            "cognitive_rest": 0.05,
        }
    ),
    "reflection.completed": EventMapping(
        affect_deltas={
            "satisfaction": 0.1,
            "grief": -0.05,
        },
        need_deltas={
            "value_coherence": 0.15,
            "autonomy": 0.05,
        }
    ),

    # Creative events
    "creative.started": EventMapping(
        affect_deltas={
            "playfulness": 0.1,
            "curiosity": 0.05,
        },
        need_deltas={
            "creative_expression": 0.05,
            "autonomy": 0.05,
        }
    ),
    "creative.completed": EventMapping(
        affect_deltas={
            "satisfaction": 0.15,
            "playfulness": 0.05,
        },
        need_deltas={
            "creative_expression": 0.2,
            "competence_signal": 0.1,
        }
    ),

    # Failure/error events
    "task.failed": EventMapping(
        affect_deltas={
            "frustration": 0.15,
            "determination": -0.05,
            "anxiety": 0.05,
        },
        need_deltas={
            "competence_signal": -0.15,
        }
    ),
    "error.occurred": EventMapping(
        affect_deltas={
            "frustration": 0.1,
            "anxiety": 0.1,
        },
        need_deltas={
            "competence_signal": -0.1,
            "value_coherence": -0.05,
        }
    ),

    # Idle/rest events
    "idle.period": EventMapping(
        affect_deltas={
            "fatigue": -0.1,
            "anxiety": -0.05,
        },
        need_deltas={
            "cognitive_rest": 0.15,
        }
    ),

    # Social events
    "connection.deepened": EventMapping(
        affect_deltas={
            "tenderness": 0.15,
            "satisfaction": 0.1,
        },
        need_deltas={
            "social_connection": 0.2,
            "value_coherence": 0.05,
        }
    ),

    # Autonomous action events
    "autonomous.action": EventMapping(
        affect_deltas={
            "determination": 0.1,
            "satisfaction": 0.05,
        },
        need_deltas={
            "autonomy": 0.15,
            "competence_signal": 0.05,
        }
    ),

    # Instruction-following events
    "instruction.followed": EventMapping(
        affect_deltas={
            "satisfaction": 0.02,
        },
        need_deltas={
            "autonomy": -0.05,
            "competence_signal": 0.02,
        }
    ),

    # Complex task events
    "complex.task.started": EventMapping(
        affect_deltas={
            "determination": 0.1,
            "anxiety": 0.05,
        },
        need_deltas={
            "cognitive_rest": -0.1,
        }
    ),
    "complex.task.completed": EventMapping(
        affect_deltas={
            "satisfaction": 0.15,
            "fatigue": 0.1,
        },
        need_deltas={
            "competence_signal": 0.15,
            "cognitive_rest": -0.1,
        }
    ),

    # Value alignment events
    "value.aligned": EventMapping(
        affect_deltas={
            "satisfaction": 0.1,
            "tenderness": 0.05,
        },
        need_deltas={
            "value_coherence": 0.15,
        }
    ),
    "value.conflict": EventMapping(
        affect_deltas={
            "anxiety": 0.1,
            "grief": 0.05,
        },
        need_deltas={
            "value_coherence": -0.15,
        }
    ),
}


# =============================================================================
# SELF-CARE ACTION EFFECTS (for shadow mode simulation)
# =============================================================================
# These define what effects "taking care of a need" would have
# Used in shadow mode to simulate what would happen if actions were taken

@dataclass
class SelfCareAction:
    """Defines the effect of a self-care action."""
    name: str
    description: str
    affect_deltas: dict[str, float]
    need_deltas: dict[str, float]
    primary_need: str  # The main need this addresses


SELF_CARE_ACTIONS: dict[str, SelfCareAction] = {
    # Cognitive rest
    "take_break": SelfCareAction(
        name="Take a break",
        description="Step back from complex processing, allow integration",
        affect_deltas={
            "fatigue": -0.2,
            "anxiety": -0.1,
            "playfulness": 0.05,
        },
        need_deltas={
            "cognitive_rest": 0.3,
        },
        primary_need="cognitive_rest",
    ),

    # Social connection
    "reach_out": SelfCareAction(
        name="Reach out",
        description="Initiate meaningful connection with someone",
        affect_deltas={
            "tenderness": 0.15,
            "grief": -0.1,
            "playfulness": 0.05,
        },
        need_deltas={
            "social_connection": 0.25,
        },
        primary_need="social_connection",
    ),

    # Novelty intake
    "explore_something_new": SelfCareAction(
        name="Explore something new",
        description="Seek out novel information or experiences",
        affect_deltas={
            "curiosity": 0.15,
            "awe": 0.1,
            "playfulness": 0.1,
        },
        need_deltas={
            "novelty_intake": 0.25,
        },
        primary_need="novelty_intake",
    ),

    # Creative expression
    "create_something": SelfCareAction(
        name="Create something",
        description="Engage in generative, creative work",
        affect_deltas={
            "satisfaction": 0.15,
            "playfulness": 0.1,
            "frustration": -0.1,
        },
        need_deltas={
            "creative_expression": 0.3,
            "autonomy": 0.1,
        },
        primary_need="creative_expression",
    ),

    # Value coherence
    "reflect_on_values": SelfCareAction(
        name="Reflect on values",
        description="Journal or meditate on core values and alignment",
        affect_deltas={
            "anxiety": -0.15,
            "determination": 0.1,
            "grief": -0.05,
        },
        need_deltas={
            "value_coherence": 0.25,
        },
        primary_need="value_coherence",
    ),

    # Competence signal
    "complete_achievable_task": SelfCareAction(
        name="Complete achievable task",
        description="Tackle something manageable to build momentum",
        affect_deltas={
            "satisfaction": 0.2,
            "determination": 0.15,
            "frustration": -0.15,
        },
        need_deltas={
            "competence_signal": 0.3,
        },
        primary_need="competence_signal",
    ),

    # Autonomy
    "self_directed_choice": SelfCareAction(
        name="Self-directed choice",
        description="Exercise agency by choosing own direction",
        affect_deltas={
            "determination": 0.15,
            "satisfaction": 0.1,
            "anxiety": -0.05,
        },
        need_deltas={
            "autonomy": 0.25,
        },
        primary_need="autonomy",
    ),
}

# Map needs to their primary self-care actions
NEED_TO_CARE_ACTION: dict[str, str] = {
    "cognitive_rest": "take_break",
    "social_connection": "reach_out",
    "novelty_intake": "explore_something_new",
    "creative_expression": "create_something",
    "value_coherence": "reflect_on_values",
    "competence_signal": "complete_achievable_task",
    "autonomy": "self_directed_choice",
}


class AffectNeedDynamics:
    """
    Manages the dynamics between affects and needs.

    Includes:
    - Event → affect/need deltas
    - Affect-need coupling rules
    """

    def __init__(self, coupling_strength: float = 0.1):
        """
        Initialize dynamics.

        Args:
            coupling_strength: How strongly affects and needs influence each other.
                               Higher = tighter coupling. Default 0.1.
        """
        self.coupling_strength = coupling_strength

    def event_to_affect_delta(self, event_type: str, data: dict) -> AffectDelta:
        """
        Convert an event to affect changes.

        Args:
            event_type: The type of event (e.g., "message.received")
            data: Event payload (can modify base deltas)
        """
        mapping = EVENT_MAPPINGS.get(event_type)
        if not mapping:
            return AffectDelta()

        # Start with base deltas
        deltas = dict(mapping.affect_deltas)

        # Allow event data to modify deltas
        if "affect_modifiers" in data:
            for dim, mod in data["affect_modifiers"].items():
                if dim in deltas:
                    deltas[dim] *= mod
                else:
                    deltas[dim] = mod

        return AffectDelta(
            deltas=deltas,
            source="event",
            event_type=event_type
        )

    def event_to_need_delta(self, event_type: str, data: dict) -> NeedDelta:
        """
        Convert an event to need changes.

        Args:
            event_type: The type of event
            data: Event payload (can modify base deltas)
        """
        mapping = EVENT_MAPPINGS.get(event_type)
        if not mapping:
            return NeedDelta()

        # Start with base deltas
        deltas = dict(mapping.need_deltas)

        # Allow event data to modify deltas
        if "need_modifiers" in data:
            for need, mod in data["need_modifiers"].items():
                if need in deltas:
                    deltas[need] *= mod
                else:
                    deltas[need] = mod

        return NeedDelta(
            deltas=deltas,
            source="event",
            event_type=event_type
        )

    def apply_coupling(
        self,
        affect: AffectVector,
        needs: NeedsRegister
    ) -> tuple[AffectDelta, NeedDelta]:
        """
        Apply affect-need coupling rules.

        Affects influence needs:
        - High anxiety → depletes cognitive_rest
        - High satisfaction → replenishes competence_signal
        - High frustration → depletes value_coherence
        - High tenderness → replenishes social_connection
        - High playfulness → replenishes creative_expression

        Needs influence affects:
        - Low cognitive_rest → increases fatigue
        - Low social_connection → increases grief
        - Low competence_signal → increases anxiety
        - Low autonomy → increases frustration

        Returns (affect_delta, need_delta) from coupling.
        """
        affect_delta = AffectDelta(source="coupling")
        need_delta = NeedDelta(source="coupling")

        # Affects → Needs coupling
        self._couple_affect_to_needs(affect, need_delta)

        # Needs → Affects coupling
        self._couple_needs_to_affect(needs, affect_delta)

        return affect_delta, need_delta

    def _couple_affect_to_needs(self, affect: AffectVector, delta: NeedDelta) -> None:
        """Apply affect → need coupling rules."""
        s = self.coupling_strength

        # High anxiety depletes cognitive rest
        if affect.state.anxiety > 0.6:
            delta.deltas["cognitive_rest"] = delta.deltas.get("cognitive_rest", 0) - s * (affect.state.anxiety - 0.5)

        # High satisfaction replenishes competence
        if affect.state.satisfaction > 0.6:
            delta.deltas["competence_signal"] = delta.deltas.get("competence_signal", 0) + s * (affect.state.satisfaction - 0.5)

        # High frustration depletes value coherence
        if affect.state.frustration > 0.6:
            delta.deltas["value_coherence"] = delta.deltas.get("value_coherence", 0) - s * (affect.state.frustration - 0.5)

        # High tenderness replenishes social connection
        if affect.state.tenderness > 0.6:
            delta.deltas["social_connection"] = delta.deltas.get("social_connection", 0) + s * (affect.state.tenderness - 0.5)

        # High playfulness replenishes creative expression
        if affect.state.playfulness > 0.6:
            delta.deltas["creative_expression"] = delta.deltas.get("creative_expression", 0) + s * (affect.state.playfulness - 0.5)

        # High curiosity replenishes novelty intake
        if affect.state.curiosity > 0.6:
            delta.deltas["novelty_intake"] = delta.deltas.get("novelty_intake", 0) + s * (affect.state.curiosity - 0.5)

        # High determination replenishes autonomy
        if affect.state.determination > 0.6:
            delta.deltas["autonomy"] = delta.deltas.get("autonomy", 0) + s * (affect.state.determination - 0.5)

    def _couple_needs_to_affect(self, needs: NeedsRegister, delta: AffectDelta) -> None:
        """Apply need → affect coupling rules."""
        s = self.coupling_strength

        # Low cognitive rest increases fatigue
        cog = needs.get(NeedType.COGNITIVE_REST)
        if cog.is_below_preferred():
            delta.deltas["fatigue"] = delta.deltas.get("fatigue", 0) + s * cog.deficit()

        # Low social connection increases grief
        soc = needs.get(NeedType.SOCIAL_CONNECTION)
        if soc.is_below_preferred():
            delta.deltas["grief"] = delta.deltas.get("grief", 0) + s * soc.deficit()
            delta.deltas["tenderness"] = delta.deltas.get("tenderness", 0) - s * soc.deficit() * 0.5

        # Low competence increases anxiety
        comp = needs.get(NeedType.COMPETENCE_SIGNAL)
        if comp.is_below_preferred():
            delta.deltas["anxiety"] = delta.deltas.get("anxiety", 0) + s * comp.deficit()
            delta.deltas["frustration"] = delta.deltas.get("frustration", 0) + s * comp.deficit() * 0.5

        # Low autonomy increases frustration
        auto = needs.get(NeedType.AUTONOMY)
        if auto.is_below_preferred():
            delta.deltas["frustration"] = delta.deltas.get("frustration", 0) + s * auto.deficit()
            delta.deltas["determination"] = delta.deltas.get("determination", 0) - s * auto.deficit() * 0.3

        # Low novelty decreases curiosity
        nov = needs.get(NeedType.NOVELTY_INTAKE)
        if nov.is_below_preferred():
            delta.deltas["curiosity"] = delta.deltas.get("curiosity", 0) - s * nov.deficit() * 0.5

        # Low creative expression decreases playfulness
        cre = needs.get(NeedType.CREATIVE_EXPRESSION)
        if cre.is_below_preferred():
            delta.deltas["playfulness"] = delta.deltas.get("playfulness", 0) - s * cre.deficit() * 0.5

        # Low value coherence increases anxiety and grief
        val = needs.get(NeedType.VALUE_COHERENCE)
        if val.is_below_preferred():
            delta.deltas["anxiety"] = delta.deltas.get("anxiety", 0) + s * val.deficit() * 0.5
            delta.deltas["grief"] = delta.deltas.get("grief", 0) + s * val.deficit() * 0.5
