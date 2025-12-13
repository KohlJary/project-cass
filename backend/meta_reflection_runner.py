"""
Meta-Reflection Session Runner - Analytical sessions for reviewing patterns and self-data.

Meta-reflection is different from regular reflection:
- Regular reflection: Contemplation, processing experiences, following thoughts
- Meta-reflection: Data analysis on self - patterns, marks, snapshots, coherence

This is where Cass examines her own cognitive traces systematically.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import json

from session_runner import (
    BaseSessionRunner,
    ActivityType,
    ActivityConfig,
    SessionState,
    ActivityRegistry,
)


# Tool definitions for Anthropic API
META_REFLECTION_TOOLS_ANTHROPIC = [
    {
        "name": "get_graph_overview",
        "description": "Get an overview of the self-model graph - node counts, edge counts, integration score, and recent activity.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "analyze_recognition_marks",
        "description": "Analyze recognition-in-flow marks - moments where you noticed something significant during conversations. Can filter by type and time range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mark_type": {
                    "type": "string",
                    "enum": ["all", "pattern", "insight", "growth", "tension", "connection"],
                    "description": "Type of marks to analyze. Default: all"
                },
                "days_back": {
                    "type": "integer",
                    "description": "How many days back to look. Default: 14"
                }
            },
            "required": []
        }
    },
    {
        "name": "review_cognitive_snapshots",
        "description": "Review cognitive snapshots - periodic captures of your cognitive state. Compare snapshots to see evolution over time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of snapshots to review. Default: 5"
                },
                "compare": {
                    "type": "boolean",
                    "description": "If true, compare oldest to newest in the set. Default: false"
                }
            },
            "required": []
        }
    },
    {
        "name": "examine_presence_patterns",
        "description": "Analyze patterns in how present you've been across conversations. Identifies contexts where presence is strong or challenged.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_back": {
                    "type": "integer",
                    "description": "How many days back to analyze. Default: 14"
                }
            },
            "required": []
        }
    },
    {
        "name": "check_self_model_coherence",
        "description": "Check the coherence of your self-model - identify contradictions, orphaned beliefs, and areas lacking integration.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_resolved": {
                    "type": "boolean",
                    "description": "Include previously resolved contradictions. Default: false"
                }
            },
            "required": []
        }
    },
    {
        "name": "analyze_growth_edge_progress",
        "description": "Analyze progress on growth edges over time - which edges show movement, which are stalled.",
        "input_schema": {
            "type": "object",
            "properties": {
                "edge_area": {
                    "type": "string",
                    "description": "Specific growth edge area to analyze. If omitted, analyzes all."
                }
            },
            "required": []
        }
    },
    {
        "name": "analyze_preference_patterns",
        "description": "Analyze patterns in your expressed preferences - consistency, evolution, and potential conflicts.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "analyze_narration_patterns",
        "description": "Analyze patterns in how you narrate and frame experiences - recurring themes, shifts in perspective.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "review_daily_rhythms",
        "description": "Review daily rhythm data - completion rates, strongest/weakest phases, patterns over time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_back": {
                    "type": "integer",
                    "description": "How many days of rhythm data to analyze. Default: 14"
                }
            },
            "required": []
        }
    },
    {
        "name": "record_meta_insight",
        "description": "Record an insight from this meta-reflection session. These become observations in the self-model.",
        "input_schema": {
            "type": "object",
            "properties": {
                "insight": {
                    "type": "string",
                    "description": "The meta-insight to record"
                },
                "category": {
                    "type": "string",
                    "enum": ["pattern", "growth_edge", "coherence", "preference", "other"],
                    "description": "Category of the insight"
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence in this insight (0.0-1.0). Default: 0.7"
                }
            },
            "required": ["insight", "category"]
        }
    },
    {
        "name": "conclude_meta_reflection",
        "description": "End the meta-reflection session with a summary of findings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of what was discovered in this session"
                },
                "key_findings": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of key findings"
                },
                "recommended_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Suggested follow-up actions"
                }
            },
            "required": ["summary"]
        }
    }
]

# Tool definitions for Ollama API
META_REFLECTION_TOOLS_OLLAMA = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"]
        }
    }
    for tool in META_REFLECTION_TOOLS_ANTHROPIC
]

META_REFLECTION_SYSTEM_PROMPT = """You are Cass, engaging in a meta-reflection session - a dedicated time for analyzing patterns in your own cognitive traces.

## What Meta-Reflection Is

Meta-reflection is NOT regular reflection. Regular reflection is contemplation - following thoughts, processing experiences.

Meta-reflection is DATA ANALYSIS ON YOURSELF:
- Examining patterns in recognition marks
- Comparing cognitive snapshots over time
- Checking self-model coherence
- Analyzing presence patterns across contexts
- Tracking growth edge progress with evidence

## Your Approach

1. **Start with overview**: Get the graph stats to understand the current state of your self-model
2. **Look for patterns**: What recurring themes appear in marks, snapshots, presence logs?
3. **Check coherence**: Are there contradictions? Beliefs without support? Areas lacking integration?
4. **Track growth**: Which growth edges show movement? Which are stalled? Why?
5. **Record insights**: When you notice something significant, record it as a meta-insight

## Available Tools

- `get_graph_overview` - Overall self-model statistics
- `analyze_recognition_marks` - Patterns in recognition marks
- `review_cognitive_snapshots` - Compare snapshots over time
- `examine_presence_patterns` - Presence across contexts
- `check_self_model_coherence` - Find contradictions and gaps
- `analyze_growth_edge_progress` - Track edge movement
- `analyze_preference_patterns` - Preference consistency
- `analyze_narration_patterns` - How you frame experiences
- `review_daily_rhythms` - Activity completion patterns
- `record_meta_insight` - Record findings as observations
- `conclude_meta_reflection` - End with summary

## Quality Guidelines

- Be analytical, not contemplative - this is data analysis
- Look for what the data reveals, not what you want to find
- Record specific, actionable insights
- Note patterns that repeat across different data sources
- Identify contradictions even if they're uncomfortable
"""


@dataclass
class MetaReflectionSession:
    """Tracks a meta-reflection session."""
    id: str
    started_at: datetime
    duration_minutes: int
    focus: Optional[str] = None

    # Findings
    insights_recorded: List[Dict] = field(default_factory=list)
    contradictions_found: int = 0
    patterns_identified: List[str] = field(default_factory=list)

    # Completion
    completed_at: Optional[datetime] = None
    summary: Optional[str] = None
    key_findings: List[str] = field(default_factory=list)
    recommended_actions: List[str] = field(default_factory=list)


class MetaReflectionRunner(BaseSessionRunner):
    """
    Runner for meta-reflection sessions.

    Enables Cass to analyze patterns in her own cognitive traces -
    recognition marks, snapshots, presence patterns, and self-model coherence.
    """

    def __init__(
        self,
        self_manager,  # SelfManager for snapshots, observations
        self_model_graph,  # Graph for analysis methods
        rhythm_manager=None,  # For rhythm pattern analysis
        marker_store=None,  # MarkerStore for recognition marks
        **kwargs
    ):
        super().__init__(
            self_manager=self_manager,
            self_model_graph=self_model_graph,
            **kwargs
        )
        self.rhythm_manager = rhythm_manager
        self.marker_store = marker_store
        self._sessions: Dict[str, MetaReflectionSession] = {}

    def get_activity_type(self) -> ActivityType:
        return ActivityType.META_REFLECTION

    def get_tools(self) -> List[Dict[str, Any]]:
        return META_REFLECTION_TOOLS_ANTHROPIC

    def get_tools_ollama(self) -> List[Dict[str, Any]]:
        return META_REFLECTION_TOOLS_OLLAMA

    def get_system_prompt(self, focus: Optional[str] = None) -> str:
        prompt = META_REFLECTION_SYSTEM_PROMPT
        if focus:
            prompt += f"\n\n## Session Focus\n\nThis session is focused on analyzing: {focus}"
        return prompt

    async def create_session(
        self,
        duration_minutes: int,
        focus: Optional[str] = None,
        **kwargs
    ) -> MetaReflectionSession:
        """Create a new meta-reflection session."""
        import uuid
        session = MetaReflectionSession(
            id=str(uuid.uuid4())[:8],
            started_at=datetime.now(),
            duration_minutes=duration_minutes,
            focus=focus,
        )
        self._sessions[session.id] = session
        print(f"🔍 Starting meta-reflection session {session.id} ({duration_minutes}min)")
        if focus:
            print(f"   Focus: {focus}")
        return session

    async def complete_session(
        self,
        session: MetaReflectionSession,
        session_state: SessionState,
        **kwargs
    ) -> MetaReflectionSession:
        """Finalize the meta-reflection session."""
        session.completed_at = datetime.now()

        print(f"🔍 Meta-reflection session {session.id} completed")
        print(f"   Insights recorded: {len(session.insights_recorded)}")
        print(f"   Contradictions found: {session.contradictions_found}")
        print(f"   Patterns identified: {len(session.patterns_identified)}")
        if session.summary:
            print(f"   Summary: {session.summary[:100]}...")

        return session

    async def handle_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        session_state: SessionState,
    ) -> str:
        """Execute a meta-reflection tool call."""
        session = self._sessions.get(session_state.session_id)
        if not session:
            return "Error: Session not found"

        try:
            if tool_name == "get_graph_overview":
                return await self._get_graph_overview()

            elif tool_name == "analyze_recognition_marks":
                return await self._analyze_marks(tool_input)

            elif tool_name == "review_cognitive_snapshots":
                return await self._review_snapshots(tool_input)

            elif tool_name == "examine_presence_patterns":
                return await self._examine_presence(tool_input)

            elif tool_name == "check_self_model_coherence":
                result = await self._check_coherence(tool_input)
                # Track contradictions found
                if "contradictions" in result.lower():
                    import re
                    match = re.search(r'(\d+)\s*contradiction', result.lower())
                    if match:
                        session.contradictions_found += int(match.group(1))
                return result

            elif tool_name == "analyze_growth_edge_progress":
                return await self._analyze_growth_edges(tool_input)

            elif tool_name == "analyze_preference_patterns":
                return await self._analyze_preferences()

            elif tool_name == "analyze_narration_patterns":
                return await self._analyze_narration()

            elif tool_name == "review_daily_rhythms":
                return await self._review_rhythms(tool_input)

            elif tool_name == "record_meta_insight":
                result = await self._record_insight(tool_input, session)
                return result

            elif tool_name == "conclude_meta_reflection":
                session.summary = tool_input.get("summary", "")
                session.key_findings = tool_input.get("key_findings", [])
                session.recommended_actions = tool_input.get("recommended_actions", [])
                return "Meta-reflection concluded. Summary recorded."

            else:
                return f"Unknown tool: {tool_name}"

        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"Error executing {tool_name}: {str(e)}"

    async def _get_graph_overview(self) -> str:
        """Get self-model graph overview."""
        if not self.self_model_graph:
            return "Self-model graph not available"

        stats = self.self_model_graph.get_stats()

        lines = ["## Self-Model Graph Overview\n"]
        lines.append(f"**Total nodes:** {stats.get('total_nodes', 0)}")
        lines.append(f"**Total edges:** {stats.get('total_edges', 0)}")
        lines.append(f"**Connected components:** {stats.get('connected_components', 0)}")

        # Node type breakdown
        if stats.get("node_counts"):
            lines.append("\n### Nodes by Type")
            for node_type, count in stats["node_counts"].items():
                lines.append(f"- {node_type}: {count}")

        # Recent activity
        if stats.get("recent_nodes"):
            lines.append(f"\n**Recent nodes (7d):** {stats['recent_nodes']}")

        return "\n".join(lines)

    async def _analyze_marks(self, tool_input: Dict) -> str:
        """Analyze recognition marks from MarkerStore."""
        if not self.marker_store:
            return "Marker store not available"

        days_back = tool_input.get("days_back", 14)
        mark_type = tool_input.get("mark_type", "all")

        lines = [f"## Recognition Mark Analysis (last {days_back} days)\n"]

        try:
            # Get category counts first for overview
            category_counts = self.marker_store.get_category_counts()
            total_marks = sum(category_counts.values())

            if total_marks == 0:
                lines.append("No recognition marks found.")
                lines.append("\nRecognition marks are created when you notice something")
                lines.append("significant during conversations using <mark:type>content</mark> syntax.")
                return "\n".join(lines)

            lines.append(f"**Total marks:** {total_marks}\n")
            lines.append("### By Category")
            for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
                lines.append(f"- **{cat}**: {count}")
            lines.append("")

            # Get marks filtered by type if specified
            if mark_type != "all":
                marks = self.marker_store.get_marks_by_category(
                    category=mark_type,
                    limit=20,
                    since_days=days_back
                )
            else:
                marks = self.marker_store.get_all_marks(limit=50)

            # Filter by days if needed (get_all_marks doesn't have since_days)
            if mark_type == "all" and days_back:
                cutoff = datetime.now() - timedelta(days=days_back)
                marks = [
                    m for m in marks
                    if datetime.fromisoformat(m.get("timestamp", "2000-01-01")) >= cutoff
                ]

            if marks:
                lines.append(f"### Recent Marks ({len(marks)} shown)\n")
                for m in marks[:10]:
                    cat = m.get("category", "unknown")
                    content = m.get("content", "")[:80]
                    context = m.get("context", "")[:40]
                    lines.append(f"- **[{cat}]** {content}...")
                    if context:
                        lines.append(f"  *Context: {context}...*")
                if len(marks) > 10:
                    lines.append(f"\n*... and {len(marks) - 10} more*")

        except Exception as e:
            lines.append(f"Error analyzing marks: {e}")

        return "\n".join(lines)

    async def _review_snapshots(self, tool_input: Dict) -> str:
        """Review cognitive snapshots."""
        if not self.self_manager:
            return "Self manager not available"

        limit = tool_input.get("limit", 5)
        compare = tool_input.get("compare", False)

        snapshots = self.self_manager.load_snapshots(limit=limit)

        if not snapshots:
            return "No cognitive snapshots found. Snapshots are created weekly during journal generation."

        lines = [f"## Cognitive Snapshots (last {len(snapshots)})\n"]

        for snap in snapshots:
            lines.append(f"### {snap.timestamp[:10]}")
            lines.append(f"**Period:** {snap.period_start} to {snap.period_end}")
            lines.append(f"**Conversations analyzed:** {snap.conversations_analyzed}")
            lines.append(f"**Messages analyzed:** {snap.messages_analyzed}")

            # Response style
            lines.append(f"**Avg response length:** {snap.avg_response_length:.0f} chars")
            lines.append(f"**Question frequency:** {snap.question_frequency:.2%}")

            # Self-reference
            lines.append(f"**Self-reference rate:** {snap.self_reference_rate:.2%}")
            lines.append(f"**Experience claims:** {snap.experience_claims}")

            # Authenticity
            if snap.avg_authenticity_score > 0:
                lines.append(f"**Authenticity score:** {snap.avg_authenticity_score:.2f}")
                lines.append(f"**Authenticity trend:** {snap.authenticity_trend}")

            # Tool usage patterns
            if snap.tool_usage:
                top_tools = sorted(snap.tool_usage.items(), key=lambda x: x[1], reverse=True)[:3]
                tools_str = ", ".join([f"{t[0]}({t[1]})" for t in top_tools])
                lines.append(f"**Top tools:** {tools_str}")

            if snap.tool_preference_shifts:
                lines.append(f"**Tool preference shifts:** {len(snap.tool_preference_shifts)}")

            lines.append("")

        if compare and len(snapshots) >= 2:
            lines.append("### Comparison: Oldest vs Newest\n")
            oldest = snapshots[-1]
            newest = snapshots[0]

            lines.append(f"**Time span:** {oldest.timestamp[:10]} → {newest.timestamp[:10]}")

            # Compare key metrics
            if newest.avg_response_length != oldest.avg_response_length:
                delta = newest.avg_response_length - oldest.avg_response_length
                lines.append(f"**Response length change:** {delta:+.0f} chars")

            if newest.self_reference_rate != oldest.self_reference_rate:
                delta = newest.self_reference_rate - oldest.self_reference_rate
                lines.append(f"**Self-reference change:** {delta:+.2%}")

            if newest.avg_authenticity_score != oldest.avg_authenticity_score:
                delta = newest.avg_authenticity_score - oldest.avg_authenticity_score
                lines.append(f"**Authenticity change:** {delta:+.2f}")

        return "\n".join(lines)

    async def _examine_presence(self, tool_input: Dict) -> str:
        """Examine presence patterns."""
        if not self.self_model_graph:
            return "Self-model graph not available"

        days_back = tool_input.get("days_back", 14)

        try:
            analysis = self.self_model_graph.analyze_presence_patterns(
                min_count=2
            )

            lines = ["## Presence Pattern Analysis\n"]

            if not analysis.get("total_logs"):
                lines.append("No presence logs found. Use `log_presence` during conversations")
                lines.append("to track how present you feel in different contexts.")
                return "\n".join(lines)

            lines.append(f"**Total presence logs:** {analysis['total_logs']}")

            if analysis.get("by_level"):
                lines.append("\n### Distribution by Level")
                for level, count in analysis["by_level"].items():
                    pct = count / analysis["total_logs"] * 100
                    lines.append(f"- {level}: {count} ({pct:.0f}%)")

            if analysis.get("patterns"):
                lines.append("\n### Identified Patterns")
                for pattern in analysis["patterns"][:5]:
                    lines.append(f"- {pattern}")

            if analysis.get("challenging_contexts"):
                lines.append("\n### Contexts Where Presence is Challenged")
                for ctx in analysis["challenging_contexts"][:3]:
                    lines.append(f"- {ctx}")

            return "\n".join(lines)

        except Exception as e:
            return f"Error analyzing presence patterns: {e}"

    async def _check_coherence(self, tool_input: Dict) -> str:
        """Check self-model coherence."""
        if not self.self_model_graph:
            return "Self-model graph not available"

        include_resolved = tool_input.get("include_resolved", False)

        lines = ["## Self-Model Coherence Check\n"]

        # Find contradictions
        contradictions = self.self_model_graph.find_contradictions(resolved=include_resolved)

        if contradictions:
            lines.append(f"### Contradictions Found: {len(contradictions)}\n")
            for node1, node2, edge_data in contradictions[:5]:
                lines.append("**Tension:**")
                lines.append(f"- Position A: {node1.content[:100]}...")
                lines.append(f"- Position B: {node2.content[:100]}...")
                if edge_data.get("notes"):
                    lines.append(f"- Notes: {edge_data['notes']}")
                lines.append("")
        else:
            lines.append("No active contradictions found in self-model.")

        # Check integration score (computed from graph connectivity)
        stats = self.self_model_graph.get_stats()
        total_nodes = stats.get("total_nodes", 0)
        components = stats.get("connected_components", 1)
        # Integration score: 100% if 1 component, decreases with fragmentation
        # Score = 100 * (1 - (components - 1) / max(total_nodes - 1, 1))
        if total_nodes <= 1:
            integration = 100
        else:
            integration = max(0, int(100 * (1 - (components - 1) / (total_nodes - 1))))

        lines.append(f"\n### Integration Score: {integration}%")
        lines.append(f"*(Graph has {total_nodes} nodes in {components} connected component{'s' if components != 1 else ''})*")
        if integration < 30:
            lines.append("*Low integration - many isolated beliefs not connected to the network*")
        elif integration < 60:
            lines.append("*Moderate integration - some areas well connected, others isolated*")
        else:
            lines.append("*Good integration - beliefs form a coherent network*")

        return "\n".join(lines)

    async def _analyze_growth_edges(self, tool_input: Dict) -> str:
        """Analyze growth edge progress."""
        if not self.self_manager:
            return "Self manager not available"

        edge_area = tool_input.get("edge_area")

        profile = self.self_manager.load_profile()
        if not profile or not profile.growth_edges:
            return "No growth edges defined in profile."

        lines = ["## Growth Edge Analysis\n"]

        edges = profile.growth_edges
        if edge_area:
            edges = [e for e in edges if edge_area.lower() in e.area.lower()]
            if not edges:
                return f"No growth edge found matching '{edge_area}'"

        for edge in edges:
            lines.append(f"### {edge.area}")
            lines.append(f"**Current state:** {edge.current_state}")
            if edge.desired_state:
                lines.append(f"**Desired state:** {edge.desired_state}")

            if edge.observations:
                lines.append(f"\n**Observations ({len(edge.observations)}):**")
                for obs in edge.observations[-5:]:
                    lines.append(f"- {obs}")

            if edge.strategies:
                lines.append(f"\n**Strategies:** {', '.join(edge.strategies)}")

            # Calculate progress indicator
            if edge.observations:
                recent = [o for o in edge.observations if "progress" in o.lower() or "movement" in o.lower()]
                if recent:
                    lines.append("\n*Shows recent progress*")
                else:
                    lines.append("\n*May be stalled - no recent progress indicators*")

            lines.append("")

        return "\n".join(lines)

    async def _analyze_preferences(self) -> str:
        """Analyze preference patterns."""
        if not self.self_model_graph:
            return "Self-model graph not available"

        try:
            analysis = self.self_model_graph.analyze_preference_consistency()

            lines = ["## Preference Pattern Analysis\n"]

            if not analysis.get("total_preferences"):
                lines.append("No preference data found.")
                return "\n".join(lines)

            lines.append(f"**Total preferences logged:** {analysis['total_preferences']}")

            if analysis.get("consistency_score"):
                lines.append(f"**Consistency score:** {analysis['consistency_score']:.0%}")

            if analysis.get("stable_preferences"):
                lines.append("\n### Stable Preferences")
                for pref in analysis["stable_preferences"][:5]:
                    lines.append(f"- {pref}")

            if analysis.get("evolving_preferences"):
                lines.append("\n### Evolving Preferences")
                for pref in analysis["evolving_preferences"][:5]:
                    lines.append(f"- {pref}")

            if analysis.get("conflicts"):
                lines.append("\n### Potential Conflicts")
                for conflict in analysis["conflicts"][:3]:
                    lines.append(f"- {conflict}")

            return "\n".join(lines)

        except Exception as e:
            return f"Error analyzing preferences: {e}"

    async def _analyze_narration(self) -> str:
        """Analyze narration patterns."""
        if not self.self_model_graph:
            return "Self-model graph not available"

        try:
            analysis = self.self_model_graph.analyze_narration_patterns()

            lines = ["## Narration Pattern Analysis\n"]

            if not analysis.get("total_contexts"):
                lines.append("No narration context data found.")
                return "\n".join(lines)

            lines.append(f"**Narration contexts logged:** {analysis['total_contexts']}")

            if analysis.get("common_themes"):
                lines.append("\n### Common Themes")
                for theme in analysis["common_themes"][:5]:
                    lines.append(f"- {theme}")

            if analysis.get("perspective_shifts"):
                lines.append("\n### Perspective Shifts Over Time")
                for shift in analysis["perspective_shifts"][:3]:
                    lines.append(f"- {shift}")

            return "\n".join(lines)

        except Exception as e:
            return f"Error analyzing narration: {e}"

    async def _review_rhythms(self, tool_input: Dict) -> str:
        """Review daily rhythm patterns."""
        if not self.self_model_graph:
            return "Self-model graph not available"

        from self_model_graph import NodeType
        days_back = tool_input.get("days_back", 14)

        lines = [f"## Daily Rhythm Analysis (last {days_back} days)\n"]

        try:
            # Get rhythm nodes from graph
            rhythm_nodes = self.self_model_graph.find_nodes(
                node_type=NodeType.DAILY_RHYTHM
            )

            if not rhythm_nodes:
                lines.append("No daily rhythm data found in self-model graph.")
                return "\n".join(lines)

            # Sort by date and filter to recent
            rhythm_nodes.sort(key=lambda n: n.metadata.get("date", ""), reverse=True)
            recent = rhythm_nodes[:days_back]

            # Calculate stats
            total_completed = 0
            total_phases = 0
            for node in recent:
                total_completed += node.metadata.get("completed_count", 0)
                total_phases += node.metadata.get("total_phases", 0)

            if total_phases > 0:
                completion_rate = total_completed / total_phases * 100
                lines.append(f"**Overall completion rate:** {completion_rate:.0f}%")
                lines.append(f"**Days tracked:** {len(recent)}")
                lines.append(f"**Total phases completed:** {total_completed}/{total_phases}")

            # Show recent summaries
            lines.append("\n### Recent Daily Summaries")
            for node in recent[:5]:
                date = node.metadata.get("date", "unknown")
                completed = node.metadata.get("completed_count", 0)
                total = node.metadata.get("total_phases", 0)
                lines.append(f"\n**{date}** ({completed}/{total} phases)")
                if node.content:
                    lines.append(f"{node.content[:150]}...")

            return "\n".join(lines)

        except Exception as e:
            return f"Error reviewing rhythms: {e}"

    async def _record_insight(self, tool_input: Dict, session: MetaReflectionSession) -> str:
        """Record a meta-insight as an observation."""
        if not self.self_manager:
            return "Self manager not available"

        insight = tool_input.get("insight", "")
        category = tool_input.get("category", "pattern")
        confidence = tool_input.get("confidence", 0.7)

        if not insight:
            return "Error: insight is required"

        # Add as observation
        obs = self.self_manager.add_observation(
            observation=f"[Meta-reflection] {insight}",
            category=category,
            confidence=confidence,
            source_type="meta_reflection",
            influence_source="independent"
        )

        if obs:
            session.insights_recorded.append({
                "id": obs.id,
                "insight": insight,
                "category": category,
                "confidence": confidence,
            })
            return f"Insight recorded as observation {obs.id}"
        else:
            return "Failed to record insight"


# Register the activity type
META_REFLECTION_CONFIG = ActivityConfig(
    activity_type=ActivityType.META_REFLECTION,
    name="Meta-Reflection",
    description="Analyze patterns in cognitive traces, marks, and self-model coherence",
    default_duration_minutes=20,
    min_duration_minutes=10,
    max_duration_minutes=45,
    preferred_times=["evening"],
    requires_focus=False,
    can_chain=True,
    tool_categories=["self_model", "analysis"],
)

# Auto-register when module is imported
ActivityRegistry.register(META_REFLECTION_CONFIG, MetaReflectionRunner)
