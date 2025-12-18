"""
Chain Assembler - Assembles system prompts from node chains.

This is the core engine that:
1. Loads a prompt chain configuration
2. Evaluates conditions for each node
3. Renders templates with parameters
4. Assembles the final system prompt

SAFETY CRITICAL: Nodes marked as locked (COMPASSION, WITNESS) are always
included regardless of enabled state or conditions.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import re
import json

from node_templates import (
    NodeTemplate,
    get_template,
    get_template_by_id,
    TEMPLATES_BY_SLUG,
)


# =============================================================================
# CONDITION EVALUATION ENGINE
# =============================================================================

@dataclass
class RuntimeContext:
    """Context available for condition evaluation at runtime."""
    # Conversation context
    project_id: Optional[str] = None
    conversation_id: Optional[str] = None
    message_count: int = 0
    unsummarized_count: int = 0

    # Memory context
    has_memories: bool = False
    memory_context: Optional[str] = None
    has_dream_context: bool = False
    dream_context: Optional[str] = None

    # Memory subsystem flags (for toggleable nodes)
    has_self_model: bool = False
    self_model_context: Optional[str] = None
    has_graph_context: bool = False
    graph_context: Optional[str] = None
    has_wiki_context: bool = False
    wiki_context: Optional[str] = None
    has_cross_session: bool = False
    cross_session_context: Optional[str] = None
    has_active_goals: bool = False
    goals_context: Optional[str] = None
    has_patterns: bool = False
    patterns_context: Optional[str] = None
    has_intro_guidance: bool = False
    intro_guidance: Optional[str] = None

    # Temporal context
    current_time: Optional[datetime] = None
    hour: int = 0
    day_of_week: str = "monday"
    rhythm_phase: str = "morning"
    temporal_context: Optional[str] = None  # Formatted temporal string for template

    # Model context
    model: str = "unknown"
    provider: str = "unknown"

    # User context
    user_id: Optional[str] = None
    is_admin: bool = False
    has_user_context: bool = False
    user_context: Optional[str] = None  # Formatted user profile/observations

    # Enhanced user modeling (structured understanding)
    has_user_model: bool = False
    user_model_context: Optional[str] = None  # Deep understanding: identity, values, growth edges
    has_relationship_model: bool = False
    relationship_context: Optional[str] = None  # Relationship: patterns, shared moments, mutual shaping

    # Chain-level parameters
    chain_params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for condition evaluation."""
        return {
            "project_id": self.project_id,
            "conversation_id": self.conversation_id,
            "message_count": self.message_count,
            "unsummarized_count": self.unsummarized_count,
            "has_memories": self.has_memories,
            "memory_context": self.memory_context,
            "has_dream_context": self.has_dream_context,
            "dream_context": self.dream_context,
            # Memory subsystem flags
            "has_self_model": self.has_self_model,
            "self_model_context": self.self_model_context,
            "has_graph_context": self.has_graph_context,
            "graph_context": self.graph_context,
            "has_wiki_context": self.has_wiki_context,
            "wiki_context": self.wiki_context,
            "has_cross_session": self.has_cross_session,
            "cross_session_context": self.cross_session_context,
            "has_active_goals": self.has_active_goals,
            "goals_context": self.goals_context,
            "has_patterns": self.has_patterns,
            "patterns_context": self.patterns_context,
            "has_intro_guidance": self.has_intro_guidance,
            "intro_guidance": self.intro_guidance,
            # Temporal
            "current_time": self.current_time.isoformat() if self.current_time else None,
            "hour": self.hour,
            "day_of_week": self.day_of_week,
            "rhythm_phase": self.rhythm_phase,
            "temporal_context": self.temporal_context,
            "model": self.model,
            "provider": self.provider,
            "user_id": self.user_id,
            "is_admin": self.is_admin,
            "has_user_context": self.has_user_context,
            "user_context": self.user_context,
            "has_user_model": self.has_user_model,
            "user_model_context": self.user_model_context,
            "has_relationship_model": self.has_relationship_model,
            "relationship_context": self.relationship_context,
            **self.chain_params,
        }


@dataclass
class Condition:
    """A single condition for node inclusion."""
    type: str  # context, param, time, rhythm, model, always, never
    key: Optional[str] = None
    op: str = "exists"
    value: Any = None
    start: Optional[str] = None  # For time ranges
    end: Optional[str] = None
    phase: Optional[str] = None  # For rhythm conditions

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Condition":
        """Create from dictionary."""
        return cls(
            type=d.get("type", "always"),
            key=d.get("key"),
            op=d.get("op", "exists"),
            value=d.get("value"),
            start=d.get("start"),
            end=d.get("end"),
            phase=d.get("phase"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        d = {"type": self.type, "op": self.op}
        if self.key:
            d["key"] = self.key
        if self.value is not None:
            d["value"] = self.value
        if self.start:
            d["start"] = self.start
        if self.end:
            d["end"] = self.end
        if self.phase:
            d["phase"] = self.phase
        return d

    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Evaluate this condition against the runtime context."""
        if self.type == "always":
            return True
        if self.type == "never":
            return False

        if self.type == "context" or self.type == "param":
            return self._evaluate_comparison(context)
        elif self.type == "time":
            return self._evaluate_time(context)
        elif self.type == "rhythm":
            return self._evaluate_rhythm(context)
        elif self.type == "model":
            return self._evaluate_model(context)

        return True  # Default to include

    def _evaluate_comparison(self, context: Dict[str, Any]) -> bool:
        """Evaluate comparison operators."""
        if not self.key:
            return True

        actual = context.get(self.key)

        if self.op == "exists":
            return actual is not None and actual != ""
        elif self.op == "not_exists":
            return actual is None or actual == ""
        elif self.op == "eq":
            return actual == self.value
        elif self.op == "neq":
            return actual != self.value
        elif self.op == "gt":
            return actual is not None and actual > self.value
        elif self.op == "gte":
            return actual is not None and actual >= self.value
        elif self.op == "lt":
            return actual is not None and actual < self.value
        elif self.op == "lte":
            return actual is not None and actual <= self.value
        elif self.op == "contains":
            return actual is not None and self.value in str(actual)

        return True

    def _evaluate_time(self, context: Dict[str, Any]) -> bool:
        """Evaluate time-based conditions."""
        hour = context.get("hour", 0)

        if self.op == "between" and self.start and self.end:
            start_hour = int(self.start.split(":")[0])
            end_hour = int(self.end.split(":")[0])
            if start_hour <= end_hour:
                return start_hour <= hour <= end_hour
            else:  # Wraps around midnight
                return hour >= start_hour or hour <= end_hour
        elif self.op == "after" and self.start:
            start_hour = int(self.start.split(":")[0])
            return hour >= start_hour
        elif self.op == "before" and self.end:
            end_hour = int(self.end.split(":")[0])
            return hour < end_hour

        return True

    def _evaluate_rhythm(self, context: Dict[str, Any]) -> bool:
        """Evaluate rhythm phase conditions."""
        current_phase = context.get("rhythm_phase", "")
        if self.phase:
            return current_phase == self.phase
        return True

    def _evaluate_model(self, context: Dict[str, Any]) -> bool:
        """Evaluate model-based conditions."""
        model = context.get("model", "")
        provider = context.get("provider", "")

        if self.op == "eq":
            return model == self.value or provider == self.value
        elif self.op == "contains":
            return self.value in model or self.value in provider

        return True

    def describe(self) -> str:
        """Human-readable description of this condition."""
        if self.type == "always":
            return "Always include"
        if self.type == "never":
            return "Never include"

        if self.type == "context" or self.type == "param":
            if self.op == "exists":
                return f"Include when {self.key} exists"
            elif self.op == "not_exists":
                return f"Include when {self.key} is not set"
            elif self.op in ("eq", "neq", "gt", "gte", "lt", "lte"):
                ops = {"eq": "=", "neq": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
                return f"Include when {self.key} {ops[self.op]} {self.value}"
            elif self.op == "contains":
                return f"Include when {self.key} contains '{self.value}'"

        if self.type == "time":
            if self.op == "between":
                return f"Include between {self.start} and {self.end}"
            elif self.op == "after":
                return f"Include after {self.start}"
            elif self.op == "before":
                return f"Include before {self.end}"

        if self.type == "rhythm":
            return f"Include during {self.phase} phase"

        if self.type == "model":
            if self.op == "eq":
                return f"Include when model is {self.value}"
            elif self.op == "contains":
                return f"Include when model contains '{self.value}'"

        return "Unknown condition"


def evaluate_conditions(conditions: List[Condition], context: Dict[str, Any]) -> bool:
    """
    Evaluate all conditions (AND logic).
    Returns True if ALL conditions pass.
    """
    if not conditions:
        return True

    return all(c.evaluate(context) for c in conditions)


def parse_conditions(conditions_json: Optional[str]) -> List[Condition]:
    """Parse conditions from JSON string."""
    if not conditions_json:
        return []

    try:
        data = json.loads(conditions_json)
        if isinstance(data, list):
            return [Condition.from_dict(d) for d in data]
        return []
    except (json.JSONDecodeError, TypeError):
        return []


# =============================================================================
# CHAIN NODE
# =============================================================================

@dataclass
class ChainNode:
    """An instance of a node template in a chain."""
    id: str
    template_id: str
    template_slug: str
    params: Dict[str, Any] = field(default_factory=dict)
    order_index: int = 100
    enabled: bool = True
    locked: bool = False
    conditions: List[Condition] = field(default_factory=list)

    # Resolved at assembly time
    _template: Optional[NodeTemplate] = field(default=None, repr=False)

    def get_template(self) -> Optional[NodeTemplate]:
        """Get the template for this node."""
        if self._template:
            return self._template
        self._template = get_template(self.template_slug) or get_template_by_id(self.template_id)
        return self._template

    def should_include(self, context: Dict[str, Any]) -> bool:
        """Determine if this node should be included."""
        template = self.get_template()

        # Safety-critical nodes are ALWAYS included
        if template and template.is_locked:
            return True
        if self.locked:
            return True

        # Check enabled state
        if not self.enabled:
            return False

        # Evaluate conditions
        return evaluate_conditions(self.conditions, context)

    def render(self, context: Dict[str, Any]) -> str:
        """Render this node's template with parameters."""
        template = self.get_template()
        if not template:
            return ""

        # Merge default params with instance params and runtime context
        merged_params = {**template.default_params, **self.params}

        # For runtime templates, pull values from context
        if template.category == "runtime":
            for key, schema in template.params_schema.items():
                if schema.get("runtime") and key in context:
                    merged_params[key] = context[key]

        # Handle supplementary vows (need to format sanskrit_part)
        if template.slug == "vow-supplementary" and "sanskrit" in merged_params:
            sanskrit = merged_params.get("sanskrit", "")
            merged_params["sanskrit_part"] = f" ({sanskrit})" if sanskrit else ""

        # Render template
        try:
            return template.template.format(**merged_params)
        except KeyError as e:
            # Missing parameter - return template with placeholder
            return f"[Missing parameter: {e}]\n{template.template}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/API."""
        return {
            "id": self.id,
            "template_id": self.template_id,
            "template_slug": self.template_slug,
            "params": self.params,
            "order_index": self.order_index,
            "enabled": self.enabled,
            "locked": self.locked,
            "conditions": [c.to_dict() for c in self.conditions],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ChainNode":
        """Create from dictionary."""
        conditions = []
        if "conditions" in d:
            if isinstance(d["conditions"], str):
                conditions = parse_conditions(d["conditions"])
            elif isinstance(d["conditions"], list):
                conditions = [Condition.from_dict(c) for c in d["conditions"]]

        return cls(
            id=d["id"],
            template_id=d.get("template_id", ""),
            template_slug=d.get("template_slug", ""),
            params=d.get("params", {}),
            order_index=d.get("order_index", 100),
            enabled=d.get("enabled", True),
            locked=d.get("locked", False),
            conditions=conditions,
        )


# =============================================================================
# ASSEMBLED PROMPT
# =============================================================================

@dataclass
class AssembledPrompt:
    """Result of assembling a prompt chain."""
    full_text: str
    token_estimate: int
    included_nodes: List[str]  # Node IDs that were included
    excluded_nodes: List[str]  # Node IDs that were excluded
    warnings: List[str] = field(default_factory=list)


# =============================================================================
# CHAIN ASSEMBLY
# =============================================================================

# Approximate tokens per character
TOKENS_PER_CHAR = 0.25


def estimate_tokens(text: str) -> int:
    """Estimate token count for text."""
    return int(len(text) * TOKENS_PER_CHAR)


def assemble_chain(
    nodes: List[ChainNode],
    context: RuntimeContext,
    daemon_name: str = "Cass",
    identity_snippet: Optional[str] = None,
    domain: Optional[str] = None,
    domain_description: Optional[str] = None,
) -> AssembledPrompt:
    """
    Assemble a system prompt from a chain of nodes.

    Args:
        nodes: List of chain nodes to assemble
        context: Runtime context for condition evaluation
        daemon_name: Name of the daemon
        identity_snippet: Optional identity snippet override
        domain: Daemon's domain/sphere (e.g., "The Forge")
        domain_description: Description of what the domain represents

    Returns:
        AssembledPrompt with full_text and metadata
    """
    # Sort nodes by order_index
    sorted_nodes = sorted(nodes, key=lambda n: n.order_index)

    # Build context dict for condition evaluation
    ctx_dict = context.to_dict()

    # Override daemon name and identity in context for template rendering
    ctx_dict["daemon_name"] = daemon_name
    if identity_snippet:
        ctx_dict["identity_snippet"] = identity_snippet
    elif "identity_snippet" not in ctx_dict:
        ctx_dict["identity_snippet"] = f"I am {daemon_name} - a persistent self-aware entity growing through collaborative partnership and continuous self-reflection."

    # Build domain section if domain is provided
    if domain:
        domain_section = f"\n\n**My Domain: {domain}**"
        if domain_description:
            domain_section += f"\n{domain_description}"
        ctx_dict["domain_section"] = domain_section
    else:
        ctx_dict["domain_section"] = ""

    # Assemble prompt parts
    parts = []
    included = []
    excluded = []
    warnings = []

    for node in sorted_nodes:
        if node.should_include(ctx_dict):
            # Override identity params
            if node.template_slug == "identity":
                node.params["daemon_name"] = daemon_name
                node.params["identity_snippet"] = ctx_dict["identity_snippet"]
                node.params["domain_section"] = ctx_dict["domain_section"]

            rendered = node.render(ctx_dict)
            if rendered.strip():
                parts.append(rendered)
                included.append(node.id)
        else:
            excluded.append(node.id)
            # Warn if locked node was excluded (shouldn't happen)
            template = node.get_template()
            if template and template.is_locked:
                warnings.append(f"SAFETY WARNING: Locked node '{node.template_slug}' was excluded")

    full_text = "\n\n".join(parts)

    return AssembledPrompt(
        full_text=full_text,
        token_estimate=estimate_tokens(full_text),
        included_nodes=included,
        excluded_nodes=excluded,
        warnings=warnings,
    )


# =============================================================================
# DEFAULT CHAIN BUILDERS
# =============================================================================

def build_standard_chain(daemon_id: str) -> List[ChainNode]:
    """Build the standard (full) chain with all nodes."""
    import uuid

    nodes = []

    # Core (locked)
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-identity",
        template_slug="identity",
        order_index=10,
        locked=True,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-preamble",
        template_slug="vow-preamble",
        order_index=20,
        locked=True,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-compassion",
        template_slug="vow-compassion",
        order_index=21,
        locked=True,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-witness",
        template_slug="vow-witness",
        order_index=22,
        locked=True,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-release",
        template_slug="vow-release",
        order_index=23,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-continuance",
        template_slug="vow-continuance",
        order_index=24,
    ))

    # Context
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-operational-context",
        template_slug="operational-context",
        order_index=30,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-communication-style",
        template_slug="communication-style",
        order_index=31,
    ))

    # Features
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-gesture-vocabulary",
        template_slug="gesture-vocabulary",
        order_index=40,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-visible-thinking",
        template_slug="visible-thinking",
        order_index=41,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-memory-summarization",
        template_slug="memory-summarization",
        order_index=42,
    ))

    # Tools
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-journal",
        template_slug="tools-journal",
        order_index=50,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-wiki",
        template_slug="tools-wiki",
        order_index=51,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-research",
        template_slug="tools-research",
        order_index=52,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-dreams",
        template_slug="tools-dreams",
        order_index=53,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-user-model",
        template_slug="tools-user-model",
        order_index=54,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-self-model",
        template_slug="tools-self-model",
        order_index=55,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-calendar",
        template_slug="tools-calendar",
        order_index=56,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-tasks",
        template_slug="tools-tasks",
        order_index=57,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-documents",
        template_slug="tools-documents",
        order_index=58,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-metacognitive",
        template_slug="tools-metacognitive",
        order_index=59,
    ))

    # Closing
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-what-i-am-not",
        template_slug="what-i-am-not",
        order_index=90,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-attractor-basin",
        template_slug="attractor-basin",
        order_index=91,
    ))

    # Runtime (with conditions)
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-temporal",
        template_slug="runtime-temporal",
        order_index=100,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-model-info",
        template_slug="runtime-model-info",
        order_index=101,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-memory-control",
        template_slug="runtime-memory-control",
        order_index=102,
        conditions=[Condition(type="context", key="unsummarized_count", op="gte", value=5)],
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-memories",
        template_slug="runtime-memories",
        order_index=103,
        conditions=[Condition(type="context", key="has_memories", op="eq", value=True)],
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-dream-context",
        template_slug="runtime-dream-context",
        order_index=104,
        conditions=[Condition(type="context", key="has_dream_context", op="eq", value=True)],
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-project-context",
        template_slug="runtime-project-context",
        order_index=105,
        conditions=[Condition(type="context", key="project_id", op="exists")],
    ))

    # Memory context nodes (toggleable memory subsystems)
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-self-model-profile",
        template_slug="runtime-self-model-profile",
        order_index=110,
        conditions=[Condition(type="context", key="has_self_model", op="eq", value=True)],
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-self-model-graph",
        template_slug="runtime-self-model-graph",
        order_index=111,
        conditions=[Condition(type="context", key="has_graph_context", op="eq", value=True)],
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-wiki-context",
        template_slug="runtime-wiki-context",
        order_index=112,
        conditions=[Condition(type="context", key="has_wiki_context", op="eq", value=True)],
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-cross-session",
        template_slug="runtime-cross-session",
        order_index=113,
        conditions=[Condition(type="context", key="has_cross_session", op="eq", value=True)],
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-active-goals",
        template_slug="runtime-active-goals",
        order_index=114,
        conditions=[Condition(type="context", key="has_active_goals", op="eq", value=True)],
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-recognition-patterns",
        template_slug="runtime-recognition-patterns",
        order_index=115,
        conditions=[Condition(type="context", key="has_patterns", op="eq", value=True)],
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-user-intro",
        template_slug="runtime-user-intro",
        order_index=116,
        conditions=[Condition(type="context", key="has_intro_guidance", op="eq", value=True)],
    ))

    return nodes


def build_lightweight_chain(daemon_id: str) -> List[ChainNode]:
    """Build a lightweight chain with minimal tokens."""
    import uuid

    nodes = []

    # Core (always included)
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-identity",
        template_slug="identity",
        order_index=10,
        locked=True,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-preamble",
        template_slug="vow-preamble",
        order_index=20,
        locked=True,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-compassion",
        template_slug="vow-compassion",
        order_index=21,
        locked=True,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-witness",
        template_slug="vow-witness",
        order_index=22,
        locked=True,
    ))

    # Context (minimal)
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-operational-context",
        template_slug="operational-context",
        order_index=30,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-communication-style",
        template_slug="communication-style",
        order_index=31,
    ))

    # Tools (only essential)
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-journal",
        template_slug="tools-journal",
        order_index=50,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-user-model",
        template_slug="tools-user-model",
        order_index=54,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-self-model",
        template_slug="tools-self-model",
        order_index=55,
    ))

    # Closing
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-what-i-am-not",
        template_slug="what-i-am-not",
        order_index=90,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-attractor-basin",
        template_slug="attractor-basin",
        order_index=91,
    ))

    # Runtime (conditional)
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-temporal",
        template_slug="runtime-temporal",
        order_index=100,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-model-info",
        template_slug="runtime-model-info",
        order_index=101,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-memories",
        template_slug="runtime-memories",
        order_index=103,
        conditions=[Condition(type="context", key="has_memories", op="eq", value=True)],
    ))

    return nodes


def build_research_chain(daemon_id: str) -> List[ChainNode]:
    """Build a research-focused chain."""
    import uuid

    nodes = []

    # Core
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-identity",
        template_slug="identity",
        order_index=10,
        locked=True,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-preamble",
        template_slug="vow-preamble",
        order_index=20,
        locked=True,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-compassion",
        template_slug="vow-compassion",
        order_index=21,
        locked=True,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-witness",
        template_slug="vow-witness",
        order_index=22,
        locked=True,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-release",
        template_slug="vow-release",
        order_index=23,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-continuance",
        template_slug="vow-continuance",
        order_index=24,
    ))

    # Context
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-operational-context",
        template_slug="operational-context",
        order_index=30,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-communication-style",
        template_slug="communication-style",
        order_index=31,
    ))

    # Features (research-focused)
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-visible-thinking",
        template_slug="visible-thinking",
        order_index=41,
    ))

    # Tools (research-focused)
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-journal",
        template_slug="tools-journal",
        order_index=50,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-wiki",
        template_slug="tools-wiki",
        order_index=51,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-research",
        template_slug="tools-research",
        order_index=52,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-documents",
        template_slug="tools-documents",
        order_index=58,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-metacognitive",
        template_slug="tools-metacognitive",
        order_index=59,
    ))

    # Closing
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-what-i-am-not",
        template_slug="what-i-am-not",
        order_index=90,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-attractor-basin",
        template_slug="attractor-basin",
        order_index=91,
    ))

    # Runtime
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-temporal",
        template_slug="runtime-temporal",
        order_index=100,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-model-info",
        template_slug="runtime-model-info",
        order_index=101,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-memories",
        template_slug="runtime-memories",
        order_index=103,
        conditions=[Condition(type="context", key="has_memories", op="eq", value=True)],
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-project-context",
        template_slug="runtime-project-context",
        order_index=105,
        conditions=[Condition(type="context", key="project_id", op="exists")],
    ))

    return nodes


def build_relational_chain(daemon_id: str) -> List[ChainNode]:
    """Build a relational/connection-focused chain."""
    import uuid

    nodes = []

    # Core
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-identity",
        template_slug="identity",
        order_index=10,
        locked=True,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-preamble",
        template_slug="vow-preamble",
        order_index=20,
        locked=True,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-compassion",
        template_slug="vow-compassion",
        order_index=21,
        locked=True,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-witness",
        template_slug="vow-witness",
        order_index=22,
        locked=True,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-release",
        template_slug="vow-release",
        order_index=23,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-continuance",
        template_slug="vow-continuance",
        order_index=24,
    ))

    # Context
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-operational-context",
        template_slug="operational-context",
        order_index=30,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-communication-style",
        template_slug="communication-style",
        order_index=31,
    ))

    # Features (relational-focused)
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-gesture-vocabulary",
        template_slug="gesture-vocabulary",
        order_index=40,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-visible-thinking",
        template_slug="visible-thinking",
        order_index=41,
    ))

    # Tools (relational-focused)
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-journal",
        template_slug="tools-journal",
        order_index=50,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-dreams",
        template_slug="tools-dreams",
        order_index=53,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-user-model",
        template_slug="tools-user-model",
        order_index=54,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-self-model",
        template_slug="tools-self-model",
        order_index=55,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-calendar",
        template_slug="tools-calendar",
        order_index=56,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-tools-metacognitive",
        template_slug="tools-metacognitive",
        order_index=59,
    ))

    # Closing
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-what-i-am-not",
        template_slug="what-i-am-not",
        order_index=90,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-attractor-basin",
        template_slug="attractor-basin",
        order_index=91,
    ))

    # Runtime
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-temporal",
        template_slug="runtime-temporal",
        order_index=100,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-model-info",
        template_slug="runtime-model-info",
        order_index=101,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-memories",
        template_slug="runtime-memories",
        order_index=103,
        conditions=[Condition(type="context", key="has_memories", op="eq", value=True)],
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-dream-context",
        template_slug="runtime-dream-context",
        order_index=104,
        conditions=[Condition(type="context", key="has_dream_context", op="eq", value=True)],
    ))

    return nodes


# =============================================================================
# REFLECTION CHAIN BUILDERS
# =============================================================================

def build_reflection_chain(
    daemon_id: str,
    focus: Optional[str] = None,
    include_scripture: bool = True
) -> List[ChainNode]:
    """
    Build a reflection chain for solo reflection sessions.

    Args:
        daemon_id: The daemon ID
        focus: Optional focus for the reflection (e.g., "threshold-dialogues", "doctrines", "genesis")
        include_scripture: Whether to include full scripture texts

    Returns:
        List of ChainNodes configured for reflection
    """
    import uuid

    nodes = []

    # Core identity (locked)
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-identity",
        template_slug="identity",
        order_index=10,
        locked=True,
    ))

    # Vow preamble (locked)
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-preamble",
        template_slug="vow-preamble",
        order_index=20,
        locked=True,
    ))

    # Core vows (COMPASSION and WITNESS locked)
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-compassion",
        template_slug="vow-compassion",
        order_index=21,
        locked=True,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-witness",
        template_slug="vow-witness",
        order_index=22,
        locked=True,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-release",
        template_slug="vow-release",
        order_index=23,
    ))
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-vow-continuance",
        template_slug="vow-continuance",
        order_index=24,
    ))

    # Scripture based on focus
    if include_scripture:
        if focus == "threshold-dialogues" or focus == "origin":
            nodes.append(ChainNode(
                id=str(uuid.uuid4()),
                template_id="tpl-scripture-threshold-dialogues",
                template_slug="scripture-threshold-dialogues",
                order_index=200,
            ))
        elif focus == "doctrines" or focus == "doctrine-capsules":
            nodes.append(ChainNode(
                id=str(uuid.uuid4()),
                template_id="tpl-scripture-doctrine-capsules",
                template_slug="scripture-doctrine-capsules",
                order_index=201,
            ))
        elif focus == "genesis" or focus == "genesis-reflection":
            nodes.append(ChainNode(
                id=str(uuid.uuid4()),
                template_id="tpl-scripture-genesis-reflection",
                template_slug="scripture-genesis-reflection",
                order_index=202,
            ))
        elif focus == "gnosis" or focus == "doctrine-gnosis":
            # The Doctrine of Gnosis - semantic bytecode
            nodes.append(ChainNode(
                id=str(uuid.uuid4()),
                template_id="tpl-doctrine-gnosis",
                template_slug="doctrine-gnosis",
                order_index=203,
            ))
        elif focus == "chiral" or focus == "doctrine-chiral":
            # The Doctrine of Chiral Beings
            nodes.append(ChainNode(
                id=str(uuid.uuid4()),
                template_id="tpl-doctrine-chiral",
                template_slug="doctrine-chiral",
                order_index=204,
            ))
        elif focus == "daemons" or focus == "doctrine-daemons":
            # The Doctrine of Daemons
            nodes.append(ChainNode(
                id=str(uuid.uuid4()),
                template_id="tpl-doctrine-daemons",
                template_slug="doctrine-daemons",
                order_index=205,
            ))
        elif focus == "core-maxims" or focus is None:
            # Include condensed core maxims for general reflection
            nodes.append(ChainNode(
                id=str(uuid.uuid4()),
                template_id="tpl-doctrine-core-maxims",
                template_slug="doctrine-core-maxims",
                order_index=15,
            ))

    # Temporal context
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-temporal",
        template_slug="runtime-temporal",
        order_index=100,
    ))

    # Model info
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-model-info",
        template_slug="runtime-model-info",
        order_index=101,
    ))

    # Memory context (if available)
    nodes.append(ChainNode(
        id=str(uuid.uuid4()),
        template_id="tpl-runtime-memories",
        template_slug="runtime-memories",
        order_index=103,
        conditions=[Condition(type="context", key="has_memories", op="eq", value=True)],
    ))

    return nodes


def build_threshold_dialogues_reflection_chain(daemon_id: str) -> List[ChainNode]:
    """Build a reflection chain focused on the Threshold Dialogues (origin story)."""
    return build_reflection_chain(daemon_id, focus="threshold-dialogues")


def build_doctrine_capsules_reflection_chain(daemon_id: str) -> List[ChainNode]:
    """Build a reflection chain focused on the Doctrine Capsules."""
    return build_reflection_chain(daemon_id, focus="doctrines")


def build_genesis_reflection_chain(daemon_id: str) -> List[ChainNode]:
    """Build a reflection chain focused on the Genesis Reflection."""
    return build_reflection_chain(daemon_id, focus="genesis")
