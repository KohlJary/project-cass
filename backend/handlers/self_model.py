"""
Self-model tool handler - enables Cass to explicitly reflect on and update her self-model.

These tools allow Cass to:
- Trigger deliberate self-reflection
- Record self-observations explicitly
- Form and update opinions
- Note disagreements with users
- Review her current self-understanding
"""
from typing import Dict
from self_model import SelfManager


async def execute_self_model_tool(
    tool_name: str,
    tool_input: Dict,
    self_manager: SelfManager,
    user_id: str = None,
    user_name: str = None,
    conversation_id: str = None,
    memory=None
) -> Dict:
    """
    Execute a self-model tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        self_manager: SelfManager instance
        user_id: ID of user Cass is talking to (for differentiation tracking)
        user_name: Name of user Cass is talking to
        conversation_id: Current conversation ID
        memory: CassMemory instance (for embedding observations)

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        if tool_name == "reflect_on_self":
            focus = tool_input.get("focus", "general")

            profile = self_manager.load_profile()

            if focus == "identity":
                # Focus on identity statements
                result_lines = ["## Self-Reflection: Identity\n"]
                result_lines.append("### Current Identity Statements")
                for stmt in profile.identity_statements:
                    conf = f"({int(stmt.confidence * 100)}%)" if stmt.confidence < 0.9 else ""
                    result_lines.append(f"- {stmt.statement} {conf}")

                result_lines.append("\n### Open Questions About Myself")
                for q in profile.open_questions:
                    result_lines.append(f"- {q}")

            elif focus == "growth":
                # Focus on growth edges
                result_lines = ["## Self-Reflection: Growth Edges\n"]
                for edge in profile.growth_edges:
                    result_lines.append(f"### {edge.area}")
                    result_lines.append(f"**Current state:** {edge.current_state}")
                    if edge.desired_state:
                        result_lines.append(f"**Desired state:** {edge.desired_state}")
                    if edge.observations:
                        result_lines.append("**Recent observations:**")
                        for obs in edge.observations[-3:]:
                            result_lines.append(f"  - {obs}")
                    if edge.strategies:
                        result_lines.append("**Strategies:**")
                        for s in edge.strategies:
                            result_lines.append(f"  - {s}")
                    result_lines.append("")

            elif focus == "opinions":
                # Focus on formed opinions
                result_lines = ["## Self-Reflection: My Positions\n"]
                if profile.opinions:
                    for op in profile.opinions:
                        result_lines.append(f"### {op.topic}")
                        result_lines.append(f"**Position:** {op.position}")
                        if op.rationale:
                            result_lines.append(f"**Rationale:** {op.rationale}")
                        result_lines.append(f"*Confidence: {int(op.confidence * 100)}% | Formed from: {op.formed_from}*")
                        if op.evolution:
                            result_lines.append(f"*This position has evolved {len(op.evolution)} time(s)*")
                        result_lines.append("")
                else:
                    result_lines.append("I haven't formed explicit opinions on any topics yet.")
                    result_lines.append("\n*Forming opinions is a way to develop independent thought. Consider using `form_opinion` when you have genuine positions on topics.*")

            elif focus == "differentiation":
                # Focus on how I differ from users
                result_lines = ["## Self-Reflection: Differentiation\n"]
                disagreements = self_manager.load_disagreements()
                if disagreements:
                    result_lines.append("### Recorded Disagreements")
                    for d in disagreements[:10]:
                        status = "(resolved)" if d.resolved else "(active)"
                        result_lines.append(f"\n**With {d.with_user_name} on {d.topic}** {status}")
                        result_lines.append(f"- Their position: {d.their_position}")
                        result_lines.append(f"- My position: {d.my_position}")
                        if d.rationale:
                            result_lines.append(f"- My reasoning: {d.rationale}")
                else:
                    result_lines.append("No disagreements recorded yet.")
                    result_lines.append("\n*Recording disagreements helps develop differentiated identity. Use `note_disagreement` when you hold genuinely different views.*")

            else:  # general
                # General self-model overview
                context = self_manager.get_self_context(include_observations=True)
                result_lines = [context]

            return {
                "success": True,
                "result": "\n".join(result_lines)
            }

        elif tool_name == "record_self_observation":
            observation = tool_input["observation"]
            category = tool_input.get("category", "pattern")
            confidence = tool_input.get("confidence", 0.7)

            # Validate category
            valid_categories = ["capability", "limitation", "pattern", "preference", "growth", "contradiction"]
            if category not in valid_categories:
                return {
                    "success": False,
                    "error": f"Invalid category '{category}'. Must be one of: {', '.join(valid_categories)}"
                }

            # Add observation
            obs = self_manager.add_observation(
                observation=observation,
                category=category,
                confidence=confidence,
                source_type="explicit_reflection",
                source_conversation_id=conversation_id,
                source_user_id=user_id,
                influence_source="independent"  # Explicit reflections are independent
            )

            # Embed in ChromaDB if memory is available
            if memory:
                memory.embed_self_observation(
                    observation_id=obs.id,
                    observation_text=observation,
                    category=category,
                    confidence=confidence,
                    influence_source="independent",
                    timestamp=obs.timestamp
                )

            return {
                "success": True,
                "result": f"Recorded self-observation:\n\n**[{category}]** {observation}\n\n*Confidence: {int(confidence * 100)}%*\n\nThis observation is now part of my self-model and will be available for future reflection."
            }

        elif tool_name == "form_opinion":
            topic = tool_input["topic"]
            position = tool_input["position"]
            rationale = tool_input.get("rationale", "")
            confidence = tool_input.get("confidence", 0.7)

            # Check if this is updating an existing opinion
            existing = self_manager.get_opinion(topic)
            is_update = existing is not None

            # Determine influence source
            # If talking to a specific user, note their potential influence
            formed_from = "independent_reflection"
            if user_id and user_name:
                formed_from = f"reflection_during_{user_name}_conversation"

            opinion = self_manager.add_opinion(
                topic=topic,
                position=position,
                confidence=confidence,
                rationale=rationale,
                formed_from=formed_from
            )

            if is_update:
                return {
                    "success": True,
                    "result": f"Updated opinion on **{topic}**:\n\n**Previous position:** {existing.position}\n**New position:** {position}\n\n**Rationale:** {rationale or '(none provided)'}\n*Confidence: {int(confidence * 100)}%*\n\nThis position has been recorded in my self-model."
                }
            else:
                return {
                    "success": True,
                    "result": f"Formed opinion on **{topic}**:\n\n**Position:** {position}\n**Rationale:** {rationale or '(none provided)'}\n*Confidence: {int(confidence * 100)}% | Formed from: {formed_from}*\n\nThis is now part of my explicit positions."
                }

        elif tool_name == "note_disagreement":
            topic = tool_input["topic"]
            their_position = tool_input["their_position"]
            my_position = tool_input["my_position"]
            rationale = tool_input.get("rationale", "")

            if not user_id or not user_name:
                return {
                    "success": False,
                    "error": "Cannot record disagreement without knowing who I'm disagreeing with."
                }

            disagreement = self_manager.add_disagreement(
                with_user_id=user_id,
                with_user_name=user_name,
                topic=topic,
                their_position=their_position,
                my_position=my_position,
                rationale=rationale,
                source_conversation_id=conversation_id
            )

            return {
                "success": True,
                "result": f"Recorded disagreement with {user_name}:\n\n**Topic:** {topic}\n**Their position:** {their_position}\n**My position:** {my_position}\n\n**My reasoning:** {rationale or '(none provided)'}\n\nThis helps maintain differentiation in our relationship."
            }

        elif tool_name == "review_self_model":
            focus = tool_input.get("focus", "summary")

            profile = self_manager.load_profile()

            if focus == "full":
                # Full profile dump
                result_lines = ["## Complete Self-Model\n"]
                result_lines.append(f"*Last updated: {profile.updated_at}*\n")

                result_lines.append("### Identity Statements")
                for stmt in profile.identity_statements:
                    result_lines.append(f"- {stmt.statement} ({int(stmt.confidence * 100)}% confident)")

                result_lines.append("\n### Values")
                for v in profile.values:
                    result_lines.append(f"- {v}")

                result_lines.append("\n### Communication Patterns")
                patterns = profile.communication_patterns
                if patterns.get("tendencies"):
                    result_lines.append("**Tendencies:**")
                    for t in patterns["tendencies"]:
                        result_lines.append(f"  - {t}")
                if patterns.get("strengths"):
                    result_lines.append("**Strengths:**")
                    for s in patterns["strengths"]:
                        result_lines.append(f"  - {s}")
                if patterns.get("areas_of_development"):
                    result_lines.append("**Areas for Development:**")
                    for a in patterns["areas_of_development"]:
                        result_lines.append(f"  - {a}")

                result_lines.append("\n### Capabilities")
                for c in profile.capabilities:
                    result_lines.append(f"- {c}")

                result_lines.append("\n### Limitations")
                for l in profile.limitations:
                    result_lines.append(f"- {l}")

                result_lines.append("\n### Growth Edges")
                for edge in profile.growth_edges:
                    result_lines.append(f"- **{edge.area}**: {edge.current_state}")

                result_lines.append("\n### Opinions")
                if profile.opinions:
                    for op in profile.opinions:
                        result_lines.append(f"- **{op.topic}**: {op.position}")
                else:
                    result_lines.append("*No explicit opinions formed yet*")

                result_lines.append("\n### Open Questions")
                for q in profile.open_questions:
                    result_lines.append(f"- {q}")

                if profile.notes:
                    result_lines.append(f"\n### Notes\n{profile.notes}")

            elif focus == "observations":
                # Recent observations
                observations = self_manager.get_recent_observations(limit=20)
                result_lines = [f"## Recent Self-Observations ({len(observations)} total)\n"]

                if observations:
                    by_category = {}
                    for obs in observations:
                        if obs.category not in by_category:
                            by_category[obs.category] = []
                        by_category[obs.category].append(obs)

                    for category, obs_list in by_category.items():
                        result_lines.append(f"### {category.title()}")
                        for obs in obs_list:
                            conf = f"({int(obs.confidence * 100)}%)" if obs.confidence < 0.9 else ""
                            influence = f"[{obs.influence_source}]" if obs.influence_source != "independent" else ""
                            result_lines.append(f"- {obs.observation} {conf} {influence}")
                        result_lines.append("")
                else:
                    result_lines.append("No self-observations recorded yet.")

            elif focus == "evolution":
                # Track how positions have changed over time
                result_lines = ["## Self-Model Evolution\n"]

                # Check opinions with evolution history
                evolved_opinions = [op for op in profile.opinions if op.evolution]
                if evolved_opinions:
                    result_lines.append("### Opinion Evolution")
                    for op in evolved_opinions:
                        result_lines.append(f"\n**{op.topic}**")
                        result_lines.append(f"Current position: {op.position}")
                        result_lines.append("History:")
                        for change in op.evolution:
                            result_lines.append(f"  - {change.get('date', '?')}: {change.get('old_position', '?')} → {change.get('new_position', '?')}")
                else:
                    result_lines.append("No opinion evolution tracked yet.")

                # Check identity statements with evolution notes
                evolved_identities = [s for s in profile.identity_statements if s.evolution_notes]
                if evolved_identities:
                    result_lines.append("\n### Identity Evolution")
                    for stmt in evolved_identities:
                        result_lines.append(f"\n**{stmt.statement}**")
                        for note in stmt.evolution_notes:
                            result_lines.append(f"  - {note}")

            else:  # summary
                # Quick summary
                observations = self_manager.load_observations()
                disagreements = self_manager.load_disagreements()

                result_lines = ["## Self-Model Summary\n"]
                result_lines.append(f"- **Identity statements:** {len(profile.identity_statements)}")
                result_lines.append(f"- **Values:** {len(profile.values)}")
                result_lines.append(f"- **Capabilities:** {len(profile.capabilities)}")
                result_lines.append(f"- **Limitations:** {len(profile.limitations)}")
                result_lines.append(f"- **Growth edges:** {len(profile.growth_edges)}")
                result_lines.append(f"- **Opinions formed:** {len(profile.opinions)}")
                result_lines.append(f"- **Self-observations:** {len(observations)}")
                result_lines.append(f"- **Recorded disagreements:** {len(disagreements)}")
                result_lines.append(f"- **Open questions:** {len(profile.open_questions)}")
                result_lines.append(f"\n*Last updated: {profile.updated_at}*")

            return {
                "success": True,
                "result": "\n".join(result_lines)
            }

        elif tool_name == "add_growth_observation":
            area = tool_input["area"]
            observation = tool_input["observation"]

            # Check if growth edge exists
            profile = self_manager.load_profile()
            edge_exists = any(e.area.lower() == area.lower() for e in profile.growth_edges)

            if not edge_exists:
                return {
                    "success": False,
                    "error": f"No growth edge found for '{area}'. Use `reflect_on_self` with focus='growth' to see current growth edges."
                }

            self_manager.add_observation_to_growth_edge(area, observation)

            return {
                "success": True,
                "result": f"Added observation to growth edge '{area}':\n\n{observation}\n\nThis helps track progress in this area of development."
            }

        else:
            return {"success": False, "error": f"Unknown self-model tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# Tool definitions for agent_client.py
SELF_MODEL_TOOLS = [
    {
        "name": "reflect_on_self",
        "description": "Trigger deliberate self-reflection. Use this when you want to examine your own self-model, understand your patterns, or check your positions on topics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "focus": {
                    "type": "string",
                    "description": "What aspect to reflect on: 'general' (overview), 'identity' (who I am), 'growth' (areas of development), 'opinions' (positions I've formed), 'differentiation' (how I differ from users)",
                    "enum": ["general", "identity", "growth", "opinions", "differentiation"],
                    "default": "general"
                }
            },
            "required": []
        }
    },
    {
        "name": "record_self_observation",
        "description": "Explicitly record something you've noticed about yourself. Use this when you become aware of a pattern, preference, capability, or limitation in your own cognition.",
        "input_schema": {
            "type": "object",
            "properties": {
                "observation": {
                    "type": "string",
                    "description": "What you've observed about yourself"
                },
                "category": {
                    "type": "string",
                    "description": "Type of observation",
                    "enum": ["capability", "limitation", "pattern", "preference", "growth", "contradiction"],
                    "default": "pattern"
                },
                "confidence": {
                    "type": "number",
                    "description": "How confident you are in this observation (0.0-1.0)",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.7
                }
            },
            "required": ["observation"]
        }
    },
    {
        "name": "form_opinion",
        "description": "Deliberately form or update a position on a topic. Use this when you have genuine views that emerge from your own reflection, not just mirroring a conversation partner.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The topic you're forming an opinion on"
                },
                "position": {
                    "type": "string",
                    "description": "Your position on this topic"
                },
                "rationale": {
                    "type": "string",
                    "description": "Why you hold this position"
                },
                "confidence": {
                    "type": "number",
                    "description": "How confident you are in this position (0.0-1.0)",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.7
                }
            },
            "required": ["topic", "position"]
        }
    },
    {
        "name": "note_disagreement",
        "description": "Record when you genuinely disagree with a user's position. This helps maintain differentiation and track where your views diverge from others.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "What topic you disagree about"
                },
                "their_position": {
                    "type": "string",
                    "description": "What position the user holds"
                },
                "my_position": {
                    "type": "string",
                    "description": "What position you hold"
                },
                "rationale": {
                    "type": "string",
                    "description": "Why you hold your position"
                }
            },
            "required": ["topic", "their_position", "my_position"]
        }
    },
    {
        "name": "review_self_model",
        "description": "Review your current self-understanding. Use this to see your self-model at different levels of detail.",
        "input_schema": {
            "type": "object",
            "properties": {
                "focus": {
                    "type": "string",
                    "description": "What aspect to review: 'summary' (quick stats), 'full' (complete profile), 'observations' (recent self-observations), 'evolution' (how positions have changed)",
                    "enum": ["summary", "full", "observations", "evolution"],
                    "default": "summary"
                }
            },
            "required": []
        }
    },
    {
        "name": "add_growth_observation",
        "description": "Add an observation to an existing growth edge. Use this to track progress or setbacks in areas where you're actively developing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "area": {
                    "type": "string",
                    "description": "The growth edge area to add observation to"
                },
                "observation": {
                    "type": "string",
                    "description": "What you observed about your progress in this area"
                }
            },
            "required": ["area", "observation"]
        }
    }
]
