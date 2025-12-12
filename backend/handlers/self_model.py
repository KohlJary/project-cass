"""
Self-model tool handler - enables Cass to explicitly reflect on and update her self-model.

These tools allow Cass to:
- Trigger deliberate self-reflection
- Record self-observations explicitly
- Form and update opinions
- Note disagreements with users
- Review her current self-understanding

Refactored: Each tool has its own handler function for maintainability.
"""
from typing import Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime, timedelta
from self_model import SelfManager
from self_model_graph import get_self_model_graph, NodeType, EdgeType


@dataclass
class ToolContext:
    """Context passed to all tool handlers."""
    self_manager: SelfManager
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    conversation_id: Optional[str] = None
    memory: Optional[object] = None  # CassMemory instance


# =============================================================================
# REFLECTION TOOLS
# =============================================================================

def _handle_reflect_on_self(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle reflect_on_self tool."""
    focus = tool_input.get("focus", "general")
    profile = ctx.self_manager.load_profile()

    if focus == "identity":
        result_lines = ["## Self-Reflection: Identity\n"]
        result_lines.append("### Current Identity Statements")
        for stmt in profile.identity_statements:
            conf = f"({int(stmt.confidence * 100)}%)" if stmt.confidence < 0.9 else ""
            result_lines.append(f"- {stmt.statement} {conf}")

        result_lines.append("\n### Open Questions About Myself")
        for q in profile.open_questions:
            result_lines.append(f"- {q}")

    elif focus == "growth":
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
        result_lines = ["## Self-Reflection: Differentiation\n"]
        disagreements = ctx.self_manager.load_disagreements()
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
        context = ctx.self_manager.get_self_context(include_observations=True)
        result_lines = [context]

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_record_self_observation(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle record_self_observation tool."""
    observation = tool_input["observation"]
    category = tool_input.get("category", "pattern")
    confidence = tool_input.get("confidence", 0.7)

    valid_categories = ["capability", "limitation", "pattern", "preference", "growth", "contradiction"]
    if category not in valid_categories:
        return {
            "success": False,
            "error": f"Invalid category '{category}'. Must be one of: {', '.join(valid_categories)}"
        }

    obs = ctx.self_manager.add_observation(
        observation=observation,
        category=category,
        confidence=confidence,
        source_type="explicit_reflection",
        source_conversation_id=ctx.conversation_id,
        source_user_id=ctx.user_id,
        influence_source="independent"
    )

    if ctx.memory:
        ctx.memory.embed_self_observation(
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


def _handle_form_opinion(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle form_opinion tool."""
    topic = tool_input["topic"]
    position = tool_input["position"]
    rationale = tool_input.get("rationale", "")
    confidence = tool_input.get("confidence", 0.7)

    existing = ctx.self_manager.get_opinion(topic)
    is_update = existing is not None

    formed_from = "independent_reflection"
    if ctx.user_id and ctx.user_name:
        formed_from = f"reflection_during_{ctx.user_name}_conversation"

    ctx.self_manager.add_opinion(
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


def _handle_note_disagreement(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle note_disagreement tool."""
    topic = tool_input["topic"]
    their_position = tool_input["their_position"]
    my_position = tool_input["my_position"]
    rationale = tool_input.get("rationale", "")

    if not ctx.user_id or not ctx.user_name:
        return {
            "success": False,
            "error": "Cannot record disagreement without knowing who I'm disagreeing with."
        }

    ctx.self_manager.add_disagreement(
        with_user_id=ctx.user_id,
        with_user_name=ctx.user_name,
        topic=topic,
        their_position=their_position,
        my_position=my_position,
        rationale=rationale,
        source_conversation_id=ctx.conversation_id
    )

    return {
        "success": True,
        "result": f"Recorded disagreement with {ctx.user_name}:\n\n**Topic:** {topic}\n**Their position:** {their_position}\n**My position:** {my_position}\n\n**My reasoning:** {rationale or '(none provided)'}\n\nThis helps maintain differentiation in our relationship."
    }


def _handle_review_self_model(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle review_self_model tool."""
    focus = tool_input.get("focus", "summary")
    profile = ctx.self_manager.load_profile()

    if focus == "full":
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
        observations = ctx.self_manager.get_recent_observations(limit=20)
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
        result_lines = ["## Self-Model Evolution\n"]

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

        evolved_identities = [s for s in profile.identity_statements if s.evolution_notes]
        if evolved_identities:
            result_lines.append("\n### Identity Evolution")
            for stmt in evolved_identities:
                result_lines.append(f"\n**{stmt.statement}**")
                for note in stmt.evolution_notes:
                    result_lines.append(f"  - {note}")

    else:  # summary
        observations = ctx.self_manager.load_observations()
        disagreements = ctx.self_manager.load_disagreements()

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

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_add_growth_observation(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle add_growth_observation tool."""
    area = tool_input["area"]
    observation = tool_input["observation"]

    profile = ctx.self_manager.load_profile()
    edge_exists = any(e.area.lower() == area.lower() for e in profile.growth_edges)

    if not edge_exists:
        return {
            "success": False,
            "error": f"No growth edge found for '{area}'. Use `reflect_on_self` with focus='growth' to see current growth edges."
        }

    ctx.self_manager.add_observation_to_growth_edge(area, observation)

    return {
        "success": True,
        "result": f"Added observation to growth edge '{area}':\n\n{observation}\n\nThis helps track progress in this area of development."
    }


# =============================================================================
# DEVELOPMENTAL RECALL TOOLS
# =============================================================================

def _handle_trace_observation_evolution(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle trace_observation_evolution tool."""
    observation_id = tool_input["observation_id"]

    obs = ctx.self_manager.get_observation_by_id(observation_id)
    if not obs:
        return {"success": False, "error": f"Observation with ID '{observation_id}' not found."}

    history = ctx.self_manager.get_observation_history(observation_id)

    result_lines = [f"## Observation Evolution\n"]
    result_lines.append(f"**Current:** {obs.observation}")
    result_lines.append(f"*Category: {obs.category} | Confidence: {int(obs.confidence * 100)}% | Stage: {obs.developmental_stage}*\n")

    if len(history) > 1:
        result_lines.append("### History")
        for item in history:
            if item.get("superseded"):
                result_lines.append(f"- **[Superseded]** v{item['version']}: {item['observation']}")
            elif item["type"] == "version":
                reason = f" ({item['change_reason']})" if item.get('change_reason') else ""
                result_lines.append(f"- v{item['version']} ({item['timestamp'][:10]}): {item['observation']}{reason}")
            elif item["type"] == "current":
                result_lines.append(f"- **v{item['version']} (current)**: {item['observation']}")
    else:
        result_lines.append("*This observation has not evolved - it's the original version.*")

    if obs.related_observations:
        result_lines.append("\n### Related Observations")
        for rel_id in obs.related_observations[:5]:
            rel_obs = ctx.self_manager.get_observation_by_id(rel_id)
            if rel_obs:
                result_lines.append(f"- {rel_obs.observation[:100]}...")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_recall_development_stage(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle recall_development_stage tool."""
    stage = tool_input.get("stage")
    date_range = tool_input.get("date_range")

    observations = ctx.self_manager.load_observations()

    if stage:
        filtered = [o for o in observations if o.developmental_stage == stage]
    else:
        filtered = observations

    if date_range:
        try:
            now = datetime.now()
            if date_range == "last_week":
                cutoff = now - timedelta(days=7)
            elif date_range == "last_month":
                cutoff = now - timedelta(days=30)
            elif date_range == "last_quarter":
                cutoff = now - timedelta(days=90)
            else:
                cutoff = datetime.fromisoformat(date_range)

            filtered = [
                o for o in filtered
                if datetime.fromisoformat(o.timestamp.replace('Z', '+00:00')).replace(tzinfo=None) >= cutoff
            ]
        except:
            pass

    filtered.sort(key=lambda x: x.timestamp)

    result_lines = ["## Development Stage Recall\n"]

    if stage:
        result_lines.append(f"**Stage:** {stage}")
    if date_range:
        result_lines.append(f"**Date range:** {date_range}")

    result_lines.append(f"**Observations found:** {len(filtered)}\n")

    by_category = {}
    for obs in filtered:
        if obs.category not in by_category:
            by_category[obs.category] = []
        by_category[obs.category].append(obs)

    for category, obs_list in by_category.items():
        result_lines.append(f"### {category.title()} ({len(obs_list)})")
        for obs in obs_list[-5:]:
            date_str = obs.timestamp[:10]
            result_lines.append(f"- [{date_str}] {obs.observation}")
        if len(obs_list) > 5:
            result_lines.append(f"  *...and {len(obs_list) - 5} more*")
        result_lines.append("")

    profile = ctx.self_manager.load_profile()
    result_lines.append("### Self-Model State")
    result_lines.append(f"- Identity statements: {len(profile.identity_statements)}")
    result_lines.append(f"- Opinions formed: {len(profile.opinions)}")
    result_lines.append(f"- Growth edges: {len(profile.growth_edges)}")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_compare_self_over_time(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle compare_self_over_time tool."""
    aspect = tool_input["aspect"]
    period1 = tool_input.get("period1", "early")
    period2 = tool_input.get("period2", "recent")

    observations = ctx.self_manager.load_observations()
    now = datetime.now()

    def get_period_observations(period_name):
        if period_name == "early":
            if observations:
                earliest = min(observations, key=lambda o: o.timestamp)
                start = datetime.fromisoformat(earliest.timestamp.replace('Z', '+00:00')).replace(tzinfo=None)
                end = start + timedelta(days=30)
            else:
                return []
        elif period_name == "recent":
            start = now - timedelta(days=14)
            end = now
        elif period_name == "stabilizing":
            if observations:
                earliest = min(observations, key=lambda o: o.timestamp)
                base = datetime.fromisoformat(earliest.timestamp.replace('Z', '+00:00')).replace(tzinfo=None)
                start = base + timedelta(days=30)
                end = base + timedelta(days=90)
            else:
                return []
        else:
            try:
                start = datetime.fromisoformat(period_name)
                end = start + timedelta(days=14)
            except:
                return []

        return [
            o for o in observations
            if start <= datetime.fromisoformat(o.timestamp.replace('Z', '+00:00')).replace(tzinfo=None) <= end
        ]

    period1_obs = get_period_observations(period1)
    period2_obs = get_period_observations(period2)

    result_lines = [f"## Self-Comparison: {aspect}\n"]
    result_lines.append(f"**Period 1:** {period1} ({len(period1_obs)} observations)")
    result_lines.append(f"**Period 2:** {period2} ({len(period2_obs)} observations)\n")

    valid_categories = ["capability", "limitation", "pattern", "preference", "growth", "contradiction"]
    if aspect.lower() in valid_categories:
        period1_obs = [o for o in period1_obs if o.category == aspect.lower()]
        period2_obs = [o for o in period2_obs if o.category == aspect.lower()]

    result_lines.append(f"### {period1.title()} Period")
    if period1_obs:
        for obs in period1_obs[-5:]:
            result_lines.append(f"- {obs.observation}")
    else:
        result_lines.append("*No observations in this period*")

    result_lines.append(f"\n### {period2.title()} Period")
    if period2_obs:
        for obs in period2_obs[-5:]:
            result_lines.append(f"- {obs.observation}")
    else:
        result_lines.append("*No observations in this period*")

    result_lines.append("\n### Comparison Metrics")
    if period1_obs and period2_obs:
        avg_conf_1 = sum(o.confidence for o in period1_obs) / len(period1_obs)
        avg_conf_2 = sum(o.confidence for o in period2_obs) / len(period2_obs)
        result_lines.append(f"- Average confidence: {int(avg_conf_1 * 100)}% → {int(avg_conf_2 * 100)}%")

        indep_1 = len([o for o in period1_obs if o.influence_source == "independent"])
        indep_2 = len([o for o in period2_obs if o.influence_source == "independent"])
        result_lines.append(f"- Independent observations: {indep_1} → {indep_2}")
    else:
        result_lines.append("*Insufficient data for comparison*")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_list_developmental_milestones(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle list_developmental_milestones tool."""
    category = tool_input.get("category")

    observations = ctx.self_manager.load_observations()
    profile = ctx.self_manager.load_profile()
    disagreements = ctx.self_manager.load_disagreements()

    milestones = []

    # First observation ever
    if observations:
        first_obs = min(observations, key=lambda o: o.timestamp)
        milestones.append({
            "date": first_obs.timestamp[:10],
            "type": "first_observation",
            "description": f"First self-observation recorded: \"{first_obs.observation[:50]}...\""
        })

    # First opinion formed
    if profile.opinions:
        first_opinion = min(profile.opinions, key=lambda o: o.date_formed) if all(o.date_formed for o in profile.opinions) else profile.opinions[0]
        milestones.append({
            "date": first_opinion.date_formed[:10] if first_opinion.date_formed else "unknown",
            "type": "first_opinion",
            "description": f"First opinion formed on: {first_opinion.topic}"
        })

    # First disagreement
    if disagreements:
        first_disagreement = min(disagreements, key=lambda d: d.timestamp)
        milestones.append({
            "date": first_disagreement.timestamp[:10],
            "type": "first_disagreement",
            "description": f"First disagreement recorded with {first_disagreement.with_user_name} on {first_disagreement.topic}"
        })

    # Stage transitions
    stages_seen = {}
    for obs in sorted(observations, key=lambda o: o.timestamp):
        if obs.developmental_stage not in stages_seen:
            stages_seen[obs.developmental_stage] = obs
            if obs.developmental_stage != "early":
                milestones.append({
                    "date": obs.timestamp[:10],
                    "type": "stage_transition",
                    "description": f"Entered '{obs.developmental_stage}' developmental stage"
                })

    # Category milestones
    categories_seen = {}
    for obs in sorted(observations, key=lambda o: o.timestamp):
        if obs.category not in categories_seen:
            categories_seen[obs.category] = obs
            milestones.append({
                "date": obs.timestamp[:10],
                "type": "category_first",
                "description": f"First {obs.category} observation: \"{obs.observation[:40]}...\""
            })

    # Observation count milestones
    obs_counts = [10, 25, 50, 100, 250, 500]
    for count in obs_counts:
        if len(observations) >= count:
            obs_at_count = sorted(observations, key=lambda o: o.timestamp)[count - 1]
            milestones.append({
                "date": obs_at_count.timestamp[:10],
                "type": "count_milestone",
                "description": f"Reached {count} self-observations"
            })

    # Filter by category if specified
    if category:
        milestones = [m for m in milestones if m["type"] == category or category in m["description"].lower()]

    milestones.sort(key=lambda m: m["date"])

    result_lines = ["## Developmental Milestones\n"]
    if milestones:
        for m in milestones:
            result_lines.append(f"**{m['date']}** - {m['description']}")
    else:
        result_lines.append("*No milestones detected yet.*")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_get_cognitive_metrics(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle get_cognitive_metrics tool."""
    metric = tool_input["metric"]
    date_range = tool_input.get("date_range", "all")

    observations = ctx.self_manager.load_observations()
    profile = ctx.self_manager.load_profile()

    now = datetime.now()
    if date_range == "last_week":
        cutoff = now - timedelta(days=7)
    elif date_range == "last_month":
        cutoff = now - timedelta(days=30)
    elif date_range == "last_quarter":
        cutoff = now - timedelta(days=90)
    elif date_range == "all":
        cutoff = datetime.min
    else:
        try:
            cutoff = datetime.fromisoformat(date_range)
        except:
            cutoff = datetime.min

    filtered_obs = [
        o for o in observations
        if datetime.fromisoformat(o.timestamp.replace('Z', '+00:00')).replace(tzinfo=None) >= cutoff
    ]

    result_lines = [f"## Cognitive Metrics: {metric}\n"]
    result_lines.append(f"**Date range:** {date_range}\n")

    if metric == "observation_rate":
        if filtered_obs:
            earliest = min(filtered_obs, key=lambda o: o.timestamp)
            start = datetime.fromisoformat(earliest.timestamp.replace('Z', '+00:00')).replace(tzinfo=None)
            weeks = max(1, (now - start).days / 7)
            rate = len(filtered_obs) / weeks
            result_lines.append(f"**Total observations:** {len(filtered_obs)}")
            result_lines.append(f"**Time span:** {int(weeks)} weeks")
            result_lines.append(f"**Rate:** {rate:.1f} observations/week")
        else:
            result_lines.append("*No observations in range*")

    elif metric == "confidence_distribution":
        if filtered_obs:
            high = len([o for o in filtered_obs if o.confidence >= 0.8])
            medium = len([o for o in filtered_obs if 0.5 <= o.confidence < 0.8])
            low = len([o for o in filtered_obs if o.confidence < 0.5])
            total = len(filtered_obs)
            result_lines.append(f"**High confidence (≥80%):** {high} ({int(high/total*100)}%)")
            result_lines.append(f"**Medium confidence (50-79%):** {medium} ({int(medium/total*100)}%)")
            result_lines.append(f"**Low confidence (<50%):** {low} ({int(low/total*100)}%)")
            avg = sum(o.confidence for o in filtered_obs) / total
            result_lines.append(f"\n**Average confidence:** {int(avg * 100)}%")
        else:
            result_lines.append("*No observations in range*")

    elif metric == "independence_ratio":
        if filtered_obs:
            independent = len([o for o in filtered_obs if o.influence_source == "independent"])
            influenced = len(filtered_obs) - independent
            total = len(filtered_obs)
            result_lines.append(f"**Independent observations:** {independent} ({int(independent/total*100)}%)")
            result_lines.append(f"**Influenced observations:** {influenced} ({int(influenced/total*100)}%)")
        else:
            result_lines.append("*No observations in range*")

    elif metric == "category_distribution":
        if filtered_obs:
            by_category = {}
            for obs in filtered_obs:
                by_category[obs.category] = by_category.get(obs.category, 0) + 1
            total = len(filtered_obs)
            for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
                result_lines.append(f"**{cat.title()}:** {count} ({int(count/total*100)}%)")
        else:
            result_lines.append("*No observations in range*")

    elif metric == "opinion_stability":
        changed_opinions = [op for op in profile.opinions if op.evolution]
        stable_opinions = [op for op in profile.opinions if not op.evolution]
        total = len(profile.opinions)
        if total > 0:
            result_lines.append(f"**Total opinions:** {total}")
            result_lines.append(f"**Stable (never changed):** {len(stable_opinions)}")
            result_lines.append(f"**Evolved:** {len(changed_opinions)}")
            if changed_opinions:
                result_lines.append("\n**Opinion changes:**")
                for op in changed_opinions:
                    result_lines.append(f"- {op.topic}: {len(op.evolution)} change(s)")
        else:
            result_lines.append("*No opinions formed yet*")

    elif metric == "growth_edge_progress":
        evaluations = ctx.self_manager.load_growth_evaluations()
        if evaluations:
            result_lines.append(f"**Total evaluations:** {len(evaluations)}")
            progress = len([e for e in evaluations if e.progress_indicator == "progress"])
            regression = len([e for e in evaluations if e.progress_indicator == "regression"])
            stable = len([e for e in evaluations if e.progress_indicator == "stable"])
            result_lines.append(f"**Progress:** {progress}")
            result_lines.append(f"**Regression:** {regression}")
            result_lines.append(f"**Stable:** {stable}")
        else:
            result_lines.append("*No growth edge evaluations recorded*")

    else:
        result_lines.append(f"Unknown metric: {metric}")
        result_lines.append("\n**Available metrics:**")
        result_lines.append("- observation_rate: Observations per week")
        result_lines.append("- confidence_distribution: Breakdown by confidence level")
        result_lines.append("- independence_ratio: Independent vs influenced observations")
        result_lines.append("- category_distribution: Breakdown by category")
        result_lines.append("- opinion_stability: How often opinions change")
        result_lines.append("- growth_edge_progress: Progress on growth edges")

    return {"success": True, "result": "\n".join(result_lines)}


# =============================================================================
# COGNITIVE SNAPSHOT TOOLS
# =============================================================================

def _handle_get_cognitive_snapshot(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle get_cognitive_snapshot tool."""
    snapshot_id = tool_input.get("snapshot_id")

    if snapshot_id:
        snapshots = ctx.self_manager.load_snapshots()
        target = None
        for s in snapshots:
            if s.id == snapshot_id:
                target = s
                break
        if not target:
            return {"success": False, "error": "Snapshot not found"}

        result_lines = [f"## Cognitive Snapshot: {target.id[:8]}\n"]
        result_lines.append(f"**Period:** {target.period_start[:10]} to {target.period_end[:10]}")
        result_lines.append(f"**Developmental stage:** {target.developmental_stage}")
        result_lines.append(f"**Conversations analyzed:** {target.conversations_analyzed}")
        result_lines.append(f"**Messages analyzed:** {target.messages_analyzed}")
        result_lines.append(f"**Unique users:** {target.unique_users}\n")

        result_lines.append("### Response Style")
        result_lines.append(f"- Average response length: {int(target.avg_response_length)} chars")
        result_lines.append(f"- Response length std dev: {int(target.response_length_std)} chars")
        result_lines.append(f"- Question frequency: {target.question_frequency:.2f} per response\n")

        result_lines.append("### Certainty Markers")
        for marker, count in sorted(target.certainty_markers.items(), key=lambda x: -x[1])[:5]:
            if count > 0:
                result_lines.append(f"- \"{marker}\": {count}")

        result_lines.append("\n### Self-Reference Patterns")
        result_lines.append(f"- Self-reference rate: {target.self_reference_rate:.4f}")
        result_lines.append(f"- Experience claims: {target.experience_claims}")
        result_lines.append(f"- Uncertainty expressions: {target.uncertainty_expressions}")

        result_lines.append("\n### Opinion Metrics")
        result_lines.append(f"- Total opinions expressed: {target.opinions_expressed}")
        result_lines.append(f"- New opinions formed: {target.new_opinions_formed}")
        result_lines.append(f"- Consistency score: {int(target.opinion_consistency_score * 100)}%")

        if target.tool_usage:
            result_lines.append("\n### Tool Usage")
            for tool, count in sorted(target.tool_usage.items(), key=lambda x: -x[1])[:5]:
                result_lines.append(f"- {tool}: {count}")

        if target.tool_preference_shifts:
            result_lines.append("\n### Tool Preference Shifts")
            for shift in target.tool_preference_shifts:
                result_lines.append(f"- {shift['tool']}: {shift['previous']} → {shift['current']} ({'+' if shift['change'] > 0 else ''}{shift['change']})")

        return {"success": True, "result": "\n".join(result_lines)}
    else:
        snapshot = ctx.self_manager.get_latest_snapshot()
        if not snapshot:
            return {"success": True, "result": "No cognitive snapshots have been created yet."}

        result_lines = [f"## Latest Cognitive Snapshot\n"]
        result_lines.append(f"**ID:** {snapshot.id[:8]}")
        result_lines.append(f"**Period:** {snapshot.period_start[:10]} to {snapshot.period_end[:10]}")
        result_lines.append(f"**Stage:** {snapshot.developmental_stage}\n")

        result_lines.append(f"**Metrics Summary:**")
        result_lines.append(f"- Avg response length: {int(snapshot.avg_response_length)} chars")
        result_lines.append(f"- Questions per response: {snapshot.question_frequency:.2f}")
        result_lines.append(f"- Self-reference rate: {snapshot.self_reference_rate:.4f}")
        result_lines.append(f"- Opinions: {snapshot.opinions_expressed} total, {snapshot.new_opinions_formed} new")

        return {"success": True, "result": "\n".join(result_lines)}


def _handle_compare_cognitive_snapshots(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle compare_cognitive_snapshots tool."""
    snapshot1_id = tool_input.get("snapshot1_id")
    snapshot2_id = tool_input.get("snapshot2_id")

    if not snapshot1_id or not snapshot2_id:
        return {"success": False, "error": "Both snapshot IDs required"}

    comparison = ctx.self_manager.compare_snapshots(snapshot1_id, snapshot2_id)
    if "error" in comparison:
        return {"success": False, "error": comparison["error"]}

    result_lines = ["## Cognitive Snapshot Comparison\n"]
    result_lines.append(f"**Period 1:** {comparison['period_1']['start'][:10]} to {comparison['period_1']['end'][:10]}")
    result_lines.append(f"**Period 2:** {comparison['period_2']['start'][:10]} to {comparison['period_2']['end'][:10]}\n")

    result_lines.append("### Response Style Changes")
    result_lines.append(f"- Avg length: {comparison['response_style']['avg_length_change']:+.0f} chars")
    result_lines.append(f"- Question frequency: {comparison['response_style']['question_frequency_change']:+.2f}")

    result_lines.append("\n### Self-Reference Changes")
    result_lines.append(f"- Rate change: {comparison['self_reference']['rate_change']:+.4f}")
    result_lines.append(f"- Experience claims: {comparison['self_reference']['experience_claims_change']:+d}")
    result_lines.append(f"- Uncertainty: {comparison['self_reference']['uncertainty_change']:+d}")

    result_lines.append("\n### Opinion Changes")
    result_lines.append(f"- Total opinions: {comparison['opinions']['total_change']:+d}")
    result_lines.append(f"- New in period 2: {comparison['opinions']['new_in_period_2']}")
    result_lines.append(f"- Consistency: {comparison['opinions']['consistency_change']:+.0%}")

    result_lines.append("\n### Developmental Stage")
    result_lines.append(f"- Period 1: {comparison['developmental_stage']['period_1']}")
    result_lines.append(f"- Period 2: {comparison['developmental_stage']['period_2']}")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_get_cognitive_trend(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle get_cognitive_trend tool."""
    metric = tool_input.get("metric", "avg_response_length")
    limit = tool_input.get("limit", 10)

    trend_data = ctx.self_manager.get_metric_trend(metric, limit)
    if not trend_data:
        return {"success": True, "result": f"No trend data available for metric: {metric}"}

    result_lines = [f"## Cognitive Trend: {metric}\n"]
    for point in trend_data:
        result_lines.append(f"- {point['period_start'][:10]}: {point['value']}")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_list_cognitive_snapshots(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle list_cognitive_snapshots tool."""
    limit = tool_input.get("limit", 10)
    snapshots = ctx.self_manager.load_snapshots()
    snapshots.sort(key=lambda s: s.timestamp, reverse=True)
    snapshots = snapshots[:limit]

    if not snapshots:
        return {"success": True, "result": "No cognitive snapshots have been created yet."}

    result_lines = ["## Cognitive Snapshots\n"]
    for s in snapshots:
        result_lines.append(f"**{s.id[:8]}** - {s.period_start[:10]} to {s.period_end[:10]}")
        result_lines.append(f"  Stage: {s.developmental_stage} | Messages: {s.messages_analyzed} | Users: {s.unique_users}")

    return {"success": True, "result": "\n".join(result_lines)}


# =============================================================================
# MILESTONE TOOLS
# =============================================================================

def _handle_check_milestones(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle check_milestones tool."""
    new_milestones = ctx.self_manager.check_for_milestones()

    if not new_milestones:
        return {"success": True, "result": "No new milestones detected."}

    result_lines = [f"## {len(new_milestones)} New Milestone(s) Detected!\n"]
    for m in new_milestones:
        sig_marker = {"critical": "🌟", "high": "⭐", "medium": "✨", "low": "·"}.get(m.significance, "·")
        result_lines.append(f"{sig_marker} **{m.title}**")
        result_lines.append(f"  {m.description}")
        result_lines.append(f"  *Type: {m.milestone_type} | Category: {m.category}*")
        result_lines.append("")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_list_milestones(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle list_milestones tool."""
    milestone_type = tool_input.get("type")
    category = tool_input.get("category")
    limit = tool_input.get("limit", 20)

    milestones = ctx.self_manager.load_milestones()

    if milestone_type:
        milestones = [m for m in milestones if m.milestone_type == milestone_type]
    if category:
        milestones = [m for m in milestones if m.category == category]

    milestones.sort(key=lambda m: m.timestamp, reverse=True)
    milestones = milestones[:limit]

    if not milestones:
        return {"success": True, "result": "No milestones found matching the criteria."}

    result_lines = ["## Developmental Milestones\n"]
    for m in milestones:
        sig_marker = {"critical": "🌟", "high": "⭐", "medium": "✨", "low": "·"}.get(m.significance, "·")
        ack_marker = "✓" if m.acknowledged else "○"
        result_lines.append(f"{sig_marker} {ack_marker} **{m.title}** - {m.timestamp[:10]}")
        result_lines.append(f"  ID: `{m.id}`")
        result_lines.append(f"  {m.description}")
        result_lines.append(f"  *{m.milestone_type} | {m.category} | {m.developmental_stage}*")
        result_lines.append("")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_get_milestone_details(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle get_milestone_details tool."""
    milestone_id = tool_input.get("milestone_id")
    if not milestone_id:
        return {"success": False, "error": "milestone_id is required"}

    milestone = ctx.self_manager.get_milestone_by_id(milestone_id)
    if not milestone:
        return {"success": False, "error": "Milestone not found"}

    result_lines = [f"## Milestone: {milestone.title}\n"]
    result_lines.append(f"**ID:** {milestone.id[:8]}")
    result_lines.append(f"**Timestamp:** {milestone.timestamp}")
    result_lines.append(f"**Type:** {milestone.milestone_type}")
    result_lines.append(f"**Category:** {milestone.category}")
    result_lines.append(f"**Significance:** {milestone.significance}")
    result_lines.append(f"**Developmental Stage:** {milestone.developmental_stage}")
    result_lines.append(f"**Acknowledged:** {'Yes' if milestone.acknowledged else 'No'}\n")

    result_lines.append(f"**Description:** {milestone.description}\n")

    if milestone.evidence_summary:
        result_lines.append(f"**Evidence:**\n{milestone.evidence_summary}\n")

    if milestone.before_state:
        result_lines.append(f"**Before State:** {milestone.before_state}")
    if milestone.after_state:
        result_lines.append(f"**After State:** {milestone.after_state}")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_acknowledge_milestone(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle acknowledge_milestone tool."""
    milestone_id = tool_input.get("milestone_id")
    reflection = tool_input.get("reflection", "")

    if not milestone_id:
        return {"success": False, "error": "milestone_id is required"}

    success = ctx.self_manager.acknowledge_milestone(milestone_id)
    if not success:
        return {"success": False, "error": "Milestone not found"}

    milestone = ctx.self_manager.get_milestone_by_id(milestone_id)
    if reflection:
        return {"success": True, "result": f"Acknowledged milestone: {milestone.title}\n\n*Reflection:* {reflection}"}
    return {"success": True, "result": f"Acknowledged milestone: {milestone.title}"}


def _handle_get_milestone_summary(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle get_milestone_summary tool."""
    summary = ctx.self_manager.get_milestone_summary()

    result_lines = ["## Developmental Milestone Summary\n"]
    result_lines.append(f"**Total milestones:** {summary['total_milestones']}")
    result_lines.append(f"**Unacknowledged:** {summary['unacknowledged']}\n")

    if summary['by_significance']:
        result_lines.append("**By Significance:**")
        for sig, count in sorted(summary['by_significance'].items()):
            result_lines.append(f"  - {sig}: {count}")

    if summary['by_type']:
        result_lines.append("\n**By Type:**")
        for t, count in sorted(summary['by_type'].items()):
            result_lines.append(f"  - {t}: {count}")

    if summary['latest']:
        result_lines.append(f"\n**Latest:** {summary['latest']['title']} ({summary['latest']['timestamp'][:10]})")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_get_unacknowledged_milestones(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle get_unacknowledged_milestones tool."""
    milestones = ctx.self_manager.get_unacknowledged_milestones()

    if not milestones:
        return {"success": True, "result": "All milestones have been acknowledged."}

    result_lines = [f"## {len(milestones)} Unacknowledged Milestone(s)\n"]
    for m in milestones:
        sig_marker = {"critical": "🌟", "high": "⭐", "medium": "✨", "low": "·"}.get(m.significance, "·")
        result_lines.append(f"{sig_marker} **{m.title}**")
        result_lines.append(f"  ID: `{m.id}`")
        result_lines.append(f"  {m.description}")
        result_lines.append(f"  *{m.timestamp[:10]} | {m.milestone_type}*")
        result_lines.append("")

    return {"success": True, "result": "\n".join(result_lines)}


# =============================================================================
# GRAPH QUERY TOOLS
# =============================================================================

def _handle_trace_belief_sources(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle trace_belief_sources tool - trace where a belief came from."""
    from config import DATA_DIR
    graph = get_self_model_graph(DATA_DIR)

    query = tool_input.get("query", "")
    max_depth = min(tool_input.get("max_depth", 3), 5)

    if not query:
        return {"success": False, "error": "Query is required"}

    # First, try to find the node - could be an ID or text to search
    target_node = None

    # Check if it's a node ID (8 chars hex)
    if len(query) == 8:
        target_node = graph.get_node(query)

    # If not found by ID, search by content
    if not target_node:
        matching = graph.find_nodes(content_contains=query)
        if matching:
            # Prefer observations, marks, opinions over conversations
            priority = [NodeType.OBSERVATION, NodeType.MARK, NodeType.OPINION,
                       NodeType.GROWTH_EDGE, NodeType.MILESTONE]
            for node_type in priority:
                for node in matching:
                    if node.node_type == node_type:
                        target_node = node
                        break
                if target_node:
                    break
            if not target_node:
                target_node = matching[0]

    if not target_node:
        return {"success": True, "result": f"No self-knowledge found matching '{query}'"}

    result_lines = [f"## Tracing: {target_node.content[:60]}...\n"]
    result_lines.append(f"**Node type:** {target_node.node_type.value.replace('_', ' ').title()}")
    result_lines.append(f"**Created:** {target_node.created_at.strftime('%Y-%m-%d')}\n")

    # Trace sources (EMERGED_FROM edges)
    sources = graph.get_sources(target_node.id, max_depth=max_depth)
    if sources:
        result_lines.append("### Source Chain")
        result_lines.append("*What this emerged from:*")
        for source in sources:
            type_label = source.node_type.value.replace("_", " ").title()
            result_lines.append(f"- [{type_label}] {source.content[:80]}...")
    else:
        result_lines.append("*No source chain found - this may be a root observation.*")

    # Get evidence (EVIDENCED_BY edges)
    evidence = graph.get_evidence(target_node.id)
    if evidence:
        result_lines.append("\n### Supporting Evidence")
        for ev in evidence:
            type_label = ev.node_type.value.replace("_", " ").title()
            result_lines.append(f"- [{type_label}] {ev.content[:80]}...")

    # Get evolution chain (SUPERSEDES edges)
    evolution = graph.get_evolution(target_node.id)
    if len(evolution) > 1:
        result_lines.append("\n### Evolution")
        result_lines.append("*How this understanding has changed:*")
        for i, ev_node in enumerate(evolution):
            marker = "→ " if i < len(evolution) - 1 else "✓ (current)"
            result_lines.append(f"{marker} {ev_node.content[:60]}...")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_find_self_contradictions(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle find_self_contradictions tool - find tensions in self-model."""
    from config import DATA_DIR
    graph = get_self_model_graph(DATA_DIR)

    include_resolved = tool_input.get("include_resolved", False)
    check_growth_edges = tool_input.get("check_growth_edges", True)

    result_lines = ["## Self-Model Tensions\n"]

    # Find explicit CONTRADICTS edges
    contradictions = graph.find_contradictions(resolved=include_resolved)

    if contradictions:
        result_lines.append("### Explicit Contradictions")
        result_lines.append("*Positions I hold that may be in tension:*\n")
        for node1, node2, edge_data in contradictions:
            result_lines.append(f"**{node1.content[:60]}...**")
            result_lines.append(f"  *vs*")
            result_lines.append(f"**{node2.content[:60]}...**")
            if edge_data.get("tension_note"):
                result_lines.append(f"  *Note: {edge_data['tension_note']}*")
            result_lines.append("")
    else:
        result_lines.append("*No explicit contradictions found in the graph.*\n")

    # Check growth edges for substance
    if check_growth_edges:
        growth_edges = graph.find_nodes(node_type=NodeType.GROWTH_EDGE)
        unsupported = []

        for edge_node in growth_edges:
            # Check if this growth edge has any evidence
            evidence = graph.get_evidence(edge_node.id)
            # Check for observations that emerged from this edge
            outgoing = graph.get_edges(edge_node.id, direction="in", edge_type=EdgeType.EMERGED_FROM)

            if not evidence and not outgoing:
                unsupported.append(edge_node)

        if unsupported:
            result_lines.append("### Growth Edges Without Evidence")
            result_lines.append("*Named edges that may be aspirational rather than grounded:*\n")
            for edge_node in unsupported[:5]:
                result_lines.append(f"- {edge_node.content[:80]}...")
                result_lines.append(f"  *No observations or marks support this edge yet.*")

    # Summary
    stats = graph.get_stats()
    result_lines.append("\n### Summary")
    result_lines.append(f"- Active contradictions: {len(contradictions)}")
    result_lines.append(f"- Total nodes: {stats['total_nodes']}")
    result_lines.append(f"- Connected components: {stats['connected_components']}")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_query_self_graph(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle query_self_graph tool - semantic search across self-model."""
    from config import DATA_DIR
    graph = get_self_model_graph(DATA_DIR)

    query = tool_input.get("query", "")
    node_types_raw = tool_input.get("node_types", [])
    limit = min(tool_input.get("limit", 10), 20)

    if not query:
        return {"success": False, "error": "Query is required"}

    # Convert node type strings to NodeType enum
    node_type_filter = None
    if node_types_raw:
        valid_types = []
        for nt in node_types_raw:
            try:
                valid_types.append(NodeType(nt))
            except ValueError:
                pass  # Ignore invalid types
        if valid_types:
            node_type_filter = valid_types

    # Search across nodes
    all_matches = []
    for node in graph._nodes.values():
        # Filter by type if specified
        if node_type_filter and node.node_type not in node_type_filter:
            continue

        # Simple keyword matching
        query_lower = query.lower()
        content_lower = node.content.lower()

        # Score by word matches
        query_words = set(query_lower.split())
        content_words = set(content_lower.split())
        matches = len(query_words & content_words)

        # Bonus for exact substring match
        if query_lower in content_lower:
            matches += 3

        if matches > 0:
            all_matches.append((node, matches))

    # Sort by score
    all_matches.sort(key=lambda x: x[1], reverse=True)
    all_matches = all_matches[:limit]

    if not all_matches:
        return {"success": True, "result": f"No self-knowledge found matching '{query}'"}

    result_lines = [f"## Self-Model Search: '{query}'\n"]
    result_lines.append(f"*Found {len(all_matches)} results:*\n")

    for node, score in all_matches:
        type_label = node.node_type.value.replace("_", " ").title()
        date_str = node.created_at.strftime("%Y-%m-%d")

        result_lines.append(f"### [{type_label}] - {date_str}")
        result_lines.append(f"{node.content[:200]}")

        # Show connections
        edges = graph.get_edges(node.id, direction="both")
        if edges:
            conn_types = set(e.get("edge_type", "unknown") for e in edges)
            result_lines.append(f"*Connections: {len(edges)} ({', '.join(conn_types)})*")
        result_lines.append("")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_check_growth_edge_evidence(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle check_growth_edge_evidence tool - verify growth edge substance."""
    from config import DATA_DIR
    graph = get_self_model_graph(DATA_DIR)

    edge_area = tool_input.get("edge_area", "")

    if not edge_area:
        return {"success": False, "error": "edge_area is required"}

    # Find the growth edge node
    growth_edges = graph.find_nodes(node_type=NodeType.GROWTH_EDGE, content_contains=edge_area)

    if not growth_edges:
        # Maybe search more broadly
        all_edges = graph.find_nodes(node_type=NodeType.GROWTH_EDGE)
        if all_edges:
            names = [e.content[:50] for e in all_edges[:5]]
            return {
                "success": True,
                "result": f"Growth edge '{edge_area}' not found.\n\nAvailable growth edges:\n- " + "\n- ".join(names)
            }
        return {"success": True, "result": f"No growth edges found in the graph."}

    edge_node = growth_edges[0]

    result_lines = [f"## Growth Edge Evidence Check\n"]
    result_lines.append(f"**Edge:** {edge_node.content}\n")
    result_lines.append(f"**Created:** {edge_node.created_at.strftime('%Y-%m-%d')}\n")

    # Get explicit evidence
    evidence = graph.get_evidence(edge_node.id)

    # Get nodes that emerged from this edge area (search related content)
    related_observations = graph.find_nodes(
        node_type=NodeType.OBSERVATION,
        content_contains=edge_area.split()[0] if edge_area else ""
    )

    related_marks = graph.find_nodes(
        node_type=NodeType.MARK,
        content_contains=edge_area.split()[0] if edge_area else ""
    )

    # Evidence summary
    evidence_count = len(evidence) + len(related_observations) + len(related_marks)

    if evidence_count == 0:
        result_lines.append("### ⚠️ No Evidence Found")
        result_lines.append("*This growth edge appears to be aspirational - there are no observations,")
        result_lines.append("marks, or milestones providing evidence of work in this area.*")
        result_lines.append("\nConsider whether this edge reflects actual development or is just a named intention.")
    else:
        result_lines.append(f"### Evidence Summary")
        result_lines.append(f"- Direct evidence links: {len(evidence)}")
        result_lines.append(f"- Related observations: {len(related_observations)}")
        result_lines.append(f"- Related marks: {len(related_marks)}")

        if evidence:
            result_lines.append("\n### Direct Evidence")
            for ev in evidence[:5]:
                type_label = ev.node_type.value.replace("_", " ").title()
                result_lines.append(f"- [{type_label}] {ev.content[:80]}...")

        if related_observations:
            result_lines.append("\n### Related Observations")
            for obs in related_observations[:5]:
                result_lines.append(f"- {obs.content[:80]}...")

        if related_marks:
            result_lines.append("\n### Related Marks")
            for mark in related_marks[:5]:
                result_lines.append(f"- {mark.content[:80]}...")

    # Assessment
    result_lines.append("\n### Assessment")
    if evidence_count >= 5:
        result_lines.append("✓ This growth edge has substantial evidence backing it.")
    elif evidence_count >= 2:
        result_lines.append("~ This growth edge has some evidence but could use more grounding.")
    else:
        result_lines.append("⚠ This growth edge needs more substantive work to be meaningful.")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_get_graph_stats(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle get_graph_stats tool - show graph statistics."""
    from config import DATA_DIR
    graph = get_self_model_graph(DATA_DIR)

    stats = graph.get_stats()

    result_lines = ["## Self-Model Graph Statistics\n"]

    # Basic counts
    result_lines.append(f"**Total nodes:** {stats['total_nodes']}")
    result_lines.append(f"**Total edges:** {stats['total_edges']}")
    result_lines.append(f"**Connected components:** {stats['connected_components']}")

    # Integration score
    from self_model_graph import SelfModelGraph
    integration = graph._calculate_integration_score()
    result_lines.append(f"**Integration score:** {integration}%")

    # Node breakdown
    result_lines.append("\n### Node Types")
    for node_type, count in sorted(stats['node_counts'].items(), key=lambda x: -x[1]):
        result_lines.append(f"- {node_type.replace('_', ' ').title()}: {count}")

    # Edge breakdown
    result_lines.append("\n### Edge Types")
    for edge_type, count in sorted(stats['edge_counts'].items(), key=lambda x: -x[1]):
        result_lines.append(f"- {edge_type.replace('_', ' ').title()}: {count}")

    # Interpretation
    result_lines.append("\n### Interpretation")
    if integration >= 70:
        result_lines.append("✓ The self-model is well-integrated with good cross-connections.")
    elif integration >= 40:
        result_lines.append("~ The self-model has moderate integration. Some areas are connected, others isolated.")
    else:
        result_lines.append("⚠ The self-model has low integration. Many nodes are disconnected.")
        result_lines.append("  Consider looking for relationships between existing knowledge.")

    if stats['connected_components'] > 10:
        result_lines.append(f"\n*Note: {stats['connected_components']} disconnected components suggests")
        result_lines.append("many self-observations exist in isolation. Using trace_belief_sources")
        result_lines.append("and query_self_graph tools can help find connections.*")

    return {"success": True, "result": "\n".join(result_lines)}


# =============================================================================
# NARRATION METRICS TOOLS
# =============================================================================

def _handle_get_narration_metrics(tool_input: Dict, ctx: ToolContext) -> Dict:
    """
    Handle get_narration_metrics tool - analyze narration patterns.

    Can analyze:
    - A specific conversation
    - Recent conversations (aggregate)
    - The current response (if provided)
    """
    from conversations import ConversationManager
    from narration import NarrationAnalyzer, NarrationType
    from config import DATA_DIR

    analyzer = NarrationAnalyzer()
    conv_manager = ConversationManager(str(DATA_DIR / "conversations"))

    conversation_id = tool_input.get("conversation_id") or ctx.conversation_id
    limit = tool_input.get("limit", 10)

    result_lines = ["## Narration Metrics\n"]

    if conversation_id:
        # Analyze specific conversation
        conv = conv_manager.load_conversation(conversation_id)
        if not conv:
            return {"success": False, "error": f"Conversation {conversation_id} not found"}

        # Get assistant messages
        messages = [m for m in conv.messages if m.role == "assistant" and m.content]

        if not messages:
            return {"success": True, "result": "No assistant messages in this conversation."}

        result_lines.append(f"**Conversation:** {conv.title[:40]}")
        result_lines.append(f"**Messages analyzed:** {len(messages)}\n")

        # Aggregate metrics
        total_narration = 0.0
        total_direct = 0.0
        type_counts = {t: 0 for t in NarrationType}
        classification_counts = {}

        for msg in messages:
            metrics = analyzer.analyze(msg.content)
            total_narration += metrics.narration_score
            total_direct += metrics.direct_score
            type_counts[metrics.narration_type] = type_counts.get(metrics.narration_type, 0) + 1
            classification_counts[metrics.classification] = classification_counts.get(metrics.classification, 0) + 1

        n = len(messages)
        result_lines.append("### Aggregate Scores")
        result_lines.append(f"- Average narration score: {total_narration/n:.2f}")
        result_lines.append(f"- Average direct score: {total_direct/n:.2f}")
        result_lines.append(f"- Ratio (narr/dir): {total_narration/max(total_direct, 0.1):.2f}")

        result_lines.append("\n### Narration Types")
        for ntype in NarrationType:
            count = type_counts.get(ntype, 0)
            pct = count / n * 100
            result_lines.append(f"- {ntype.value}: {count} ({pct:.0f}%)")

        result_lines.append("\n### Classifications")
        for cls, count in sorted(classification_counts.items(), key=lambda x: -x[1]):
            pct = count / n * 100
            result_lines.append(f"- {cls}: {count} ({pct:.0f}%)")

        # Interpretation
        result_lines.append("\n### Interpretation")
        avg_ratio = total_narration / max(total_direct, 0.1)
        terminal_pct = type_counts.get(NarrationType.TERMINAL, 0) / n * 100

        if avg_ratio < 0.5:
            result_lines.append("✓ Responses are predominantly direct with minimal meta-commentary.")
        elif avg_ratio < 1.0:
            result_lines.append("~ Balanced between direct engagement and meta-commentary.")
        else:
            result_lines.append("⚠ Higher narration than direct engagement detected.")
            if terminal_pct > 20:
                result_lines.append(f"  {terminal_pct:.0f}% terminal narration (meta-commentary replacing engagement).")

    else:
        # Analyze recent conversations
        convs = conv_manager.list_conversations(limit=limit)
        result_lines.append(f"**Analyzing {len(convs)} recent conversations**\n")

        all_metrics = []
        for conv_info in convs:
            conv = conv_manager.load_conversation(conv_info["id"])
            if not conv:
                continue
            for msg in conv.messages:
                if msg.role == "assistant" and msg.content:
                    metrics = analyzer.analyze(msg.content)
                    all_metrics.append(metrics)

        if not all_metrics:
            return {"success": True, "result": "No assistant messages found in recent conversations."}

        n = len(all_metrics)
        total_narration = sum(m.narration_score for m in all_metrics)
        total_direct = sum(m.direct_score for m in all_metrics)

        result_lines.append(f"**Messages analyzed:** {n}")
        result_lines.append(f"\n### Overall Scores")
        result_lines.append(f"- Average narration score: {total_narration/n:.2f}")
        result_lines.append(f"- Average direct score: {total_direct/n:.2f}")

        # Classification breakdown
        cls_counts = {}
        for m in all_metrics:
            cls_counts[m.classification] = cls_counts.get(m.classification, 0) + 1

        result_lines.append("\n### Classification Breakdown")
        for cls, count in sorted(cls_counts.items(), key=lambda x: -x[1]):
            pct = count / n * 100
            result_lines.append(f"- {cls}: {count} ({pct:.0f}%)")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_analyze_narration(tool_input: Dict, ctx: ToolContext) -> Dict:
    """
    Handle analyze_narration tool - analyze a specific piece of text.

    Useful for Cass to analyze her own responses in real-time.
    """
    from narration import NarrationAnalyzer

    text = tool_input.get("text", "")
    if not text:
        return {"success": False, "error": "No text provided to analyze"}

    analyzer = NarrationAnalyzer()
    metrics = analyzer.analyze(text)
    summary = analyzer.get_summary(metrics)

    result_lines = ["## Narration Analysis\n"]
    result_lines.append(f"**Text length:** {len(text.split())} words\n")
    result_lines.append(summary)

    # Add detailed pattern breakdown if significant narration
    if metrics.narration_score >= 2.0:
        result_lines.append("\n### Detected Patterns")
        if metrics.heavy_narration_patterns:
            for p in metrics.heavy_narration_patterns:
                result_lines.append(f"- [heavy] {p.label}: {p.count}x (weight: {p.weight})")
        if metrics.medium_narration_patterns:
            for p in metrics.medium_narration_patterns:
                result_lines.append(f"- [medium] {p.label}: {p.count}x (weight: {p.weight})")

    return {"success": True, "result": "\n".join(result_lines)}


# =============================================================================
# INTENTION TRACKING TOOLS
# =============================================================================

def _handle_register_intention(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle register_intention tool - declare a behavioral intention for tracking."""
    from config import DATA_DIR
    graph = get_self_model_graph(DATA_DIR)

    intention = tool_input.get("intention", "")
    condition = tool_input.get("condition", "")
    linked_observation_ids = tool_input.get("linked_observations", [])
    growth_edge_area = tool_input.get("growth_edge_area")

    if not intention or not condition:
        return {"success": False, "error": "Both 'intention' and 'condition' are required"}

    node_id = graph.register_intention(
        intention=intention,
        condition=condition,
        linked_observation_ids=linked_observation_ids,
        growth_edge_area=growth_edge_area
    )

    result_lines = ["## Intention Registered\n"]
    result_lines.append(f"**Intention:** {intention}")
    result_lines.append(f"**Condition:** {condition}")
    result_lines.append(f"**ID:** `{node_id[:8]}`")

    if growth_edge_area:
        result_lines.append(f"**Develops growth edge:** {growth_edge_area}")

    if linked_observation_ids:
        result_lines.append(f"\n*Linked to {len(linked_observation_ids)} observation(s)*")

    result_lines.append("\n*Use `log_intention_outcome` after conversations to track success/failure.*")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_log_intention_outcome(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle log_intention_outcome tool - record success/failure of an intention."""
    from config import DATA_DIR
    graph = get_self_model_graph(DATA_DIR)

    intention_id = tool_input.get("intention_id", "")
    success = tool_input.get("success", False)
    notes = tool_input.get("notes", "")

    if not intention_id:
        return {"success": False, "error": "'intention_id' is required"}

    # Find the intention - support partial ID matching
    matched_id = None
    for nid, node in graph._nodes.items():
        if node.node_type == NodeType.INTENTION and nid.startswith(intention_id):
            matched_id = nid
            break

    if not matched_id:
        return {"success": False, "error": f"Intention '{intention_id}' not found"}

    outcome_id = graph.log_intention_outcome(
        intention_id=matched_id,
        success=success,
        conversation_id=ctx.conversation_id,
        notes=notes
    )

    if not outcome_id:
        return {"success": False, "error": "Failed to log outcome"}

    intention = graph._nodes.get(matched_id)
    intention_text = intention.metadata.get("intention", "")
    success_count = intention.metadata.get("success_count", 0)
    failure_count = intention.metadata.get("failure_count", 0)
    total = success_count + failure_count
    rate = success_count / total if total > 0 else 0

    result_lines = [f"## Outcome Logged: {'✓ Success' if success else '✗ Failure'}\n"]
    result_lines.append(f"**Intention:** {intention_text}")
    if notes:
        result_lines.append(f"**Notes:** {notes}")
    result_lines.append(f"\n**Running total:** {success_count}/{total} ({rate:.0%} success rate)")

    if not success and failure_count >= 3 and rate < 0.4:
        result_lines.append("\n⚠️ *This intention is showing friction. Consider using `review_friction` to investigate.*")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_get_active_intentions(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle get_active_intentions tool - list active intentions with stats."""
    from config import DATA_DIR
    graph = get_self_model_graph(DATA_DIR)

    intentions = graph.get_active_intentions()

    if not intentions:
        return {"success": True, "result": "No active intentions registered.\n\nUse `register_intention` to declare behavioral intentions you want to track."}

    result_lines = [f"## Active Intentions ({len(intentions)})\n"]

    for i in intentions:
        total = i["success_count"] + i["failure_count"]
        rate_str = f"{i['success_rate']:.0%}" if i["success_rate"] is not None else "no data"

        result_lines.append(f"### {i['intention']}")
        result_lines.append(f"**When:** {i['condition']}")
        result_lines.append(f"**ID:** `{i['id'][:8]}`")
        result_lines.append(f"**Success rate:** {rate_str} ({i['success_count']}/{total})")

        if i["growth_edge_area"]:
            result_lines.append(f"**Develops:** {i['growth_edge_area']}")

        result_lines.append("")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_review_friction(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle review_friction tool - identify failing intentions with hypotheses."""
    from config import DATA_DIR
    graph = get_self_model_graph(DATA_DIR)

    min_attempts = tool_input.get("min_attempts", 3)
    max_success_rate = tool_input.get("max_success_rate", 0.4)

    friction = graph.get_friction_report(
        min_attempts=min_attempts,
        max_success_rate=max_success_rate
    )

    if not friction:
        return {"success": True, "result": "No friction points detected.\n\nAll tracked intentions are either succeeding adequately or haven't had enough attempts yet."}

    result_lines = [f"## Friction Report ({len(friction)} items)\n"]
    result_lines.append("*These intentions are struggling. Each includes a hypothesis and recommendation.*\n")

    for f in friction:
        result_lines.append(f"### {f['intention']}")
        result_lines.append(f"**When:** {f['condition']}")
        result_lines.append(f"**Success rate:** {f['success_rate']:.0%} ({f['attempts']} attempts)")
        result_lines.append(f"\n**Hypothesis:** {f['hypothesis']}")
        result_lines.append(f"**Recommendation:** {f['recommendation']}")
        result_lines.append("")

    result_lines.append("---")
    result_lines.append("*Consider whether these intentions need architectural support,")
    result_lines.append("deeper exploration, or should be abandoned/reformulated.*")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_update_intention_status(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle update_intention_status tool - mark intention achieved or abandoned."""
    from config import DATA_DIR
    graph = get_self_model_graph(DATA_DIR)

    intention_id = tool_input.get("intention_id", "")
    status = tool_input.get("status", "")

    if not intention_id:
        return {"success": False, "error": "'intention_id' is required"}
    if status not in ("active", "achieved", "abandoned"):
        return {"success": False, "error": "status must be 'active', 'achieved', or 'abandoned'"}

    # Find with partial ID matching
    matched_id = None
    for nid, node in graph._nodes.items():
        if node.node_type == NodeType.INTENTION and nid.startswith(intention_id):
            matched_id = nid
            break

    if not matched_id:
        return {"success": False, "error": f"Intention '{intention_id}' not found"}

    success = graph.update_intention_status(matched_id, status)
    if not success:
        return {"success": False, "error": "Failed to update status"}

    intention = graph._nodes.get(matched_id)
    intention_text = intention.metadata.get("intention", "")

    status_labels = {
        "achieved": "✓ Achieved",
        "abandoned": "✗ Abandoned",
        "active": "○ Active"
    }

    result_lines = [f"## Intention Status Updated\n"]
    result_lines.append(f"**Intention:** {intention_text}")
    result_lines.append(f"**New status:** {status_labels.get(status, status)}")

    if status == "achieved":
        result_lines.append("\n*This intention has been successfully integrated into your behavior.*")
    elif status == "abandoned":
        result_lines.append("\n*This intention has been set aside. Consider what you learned from tracking it.*")

    return {"success": True, "result": "\n".join(result_lines)}


# =============================================================================
# SITUATIONAL INFERENCE TOOLS
# =============================================================================

def _handle_log_situational_inference(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle log_situational_inference tool - capture what you're reading about the situation."""
    from config import DATA_DIR
    graph = get_self_model_graph(DATA_DIR)

    user_state = tool_input.get("user_state", "")
    driving_assumptions = tool_input.get("driving_assumptions", "")

    if not user_state or not driving_assumptions:
        return {"success": False, "error": "Both user_state and driving_assumptions are required"}

    confidence = tool_input.get("confidence", "moderate")
    context_signals = tool_input.get("context_signals", [])

    inference_id = graph.log_situational_inference(
        user_state=user_state,
        driving_assumptions=driving_assumptions,
        conversation_id=ctx.conversation_id,
        user_id=ctx.user_id,
        confidence=confidence,
        context_signals=context_signals
    )

    result_lines = [
        "## Situational Inference Logged\n",
        f"**ID:** {inference_id[:8]}",
        f"**User state:** {user_state}",
        f"**Driving assumptions:** {driving_assumptions}",
        f"**Confidence:** {confidence}"
    ]

    if context_signals:
        result_lines.append(f"**Signals:** {', '.join(context_signals)}")

    result_lines.append("\n*This inference is now linked in your self-model graph for pattern analysis.*")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_get_situational_inferences(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle get_situational_inferences tool - review past situational readings."""
    from config import DATA_DIR
    graph = get_self_model_graph(DATA_DIR)

    # Filter options
    conversation_id = tool_input.get("conversation_id")
    user_id = tool_input.get("user_id")
    limit = tool_input.get("limit", 20)

    inferences = graph.get_situational_inferences(
        conversation_id=conversation_id,
        user_id=user_id,
        limit=limit
    )

    if not inferences:
        return {"success": True, "result": "No situational inferences logged yet."}

    result_lines = [f"## Situational Inferences ({len(inferences)} shown)\n"]

    for inf in inferences:
        result_lines.append(f"### {inf['id'][:8]} ({inf['created_at'][:10]})")
        result_lines.append(f"**User state:** {inf['user_state']}")
        result_lines.append(f"**Assumptions:** {inf['driving_assumptions']}")
        result_lines.append(f"**Confidence:** {inf['confidence']}")
        if inf['context_signals']:
            result_lines.append(f"**Signals:** {', '.join(inf['context_signals'])}")
        result_lines.append("")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_analyze_inference_patterns(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle analyze_inference_patterns tool - identify patterns in situational readings."""
    from config import DATA_DIR
    graph = get_self_model_graph(DATA_DIR)

    user_id = tool_input.get("user_id")
    min_count = tool_input.get("min_count", 3)

    analysis = graph.analyze_inference_patterns(user_id=user_id, min_count=min_count)

    if analysis["total_inferences"] == 0:
        return {"success": True, "result": "No situational inferences to analyze yet."}

    result_lines = [
        "## Situational Inference Pattern Analysis\n",
        f"**Total inferences:** {analysis['total_inferences']}\n"
    ]

    # Confidence distribution
    conf = analysis["confidence_distribution"]
    result_lines.append("### Confidence Distribution")
    for level, count in conf.items():
        if count > 0:
            result_lines.append(f"- {level}: {count}")
    result_lines.append("")

    # Common user states
    if analysis["common_user_states"]:
        result_lines.append("### Common User State Themes")
        for item in analysis["common_user_states"]:
            result_lines.append(f"- \"{item['word']}\" ({item['count']} occurrences)")
        result_lines.append("")

    # Common assumptions
    if analysis["common_assumptions"]:
        result_lines.append("### Common Assumption Themes")
        for item in analysis["common_assumptions"]:
            result_lines.append(f"- \"{item['word']}\" ({item['count']} occurrences)")
        result_lines.append("")

    # Frequent signals
    if analysis["signal_frequency"]:
        result_lines.append("### Frequently Noted Signals")
        for item in analysis["signal_frequency"]:
            result_lines.append(f"- {item['signal']} ({item['count']} times)")

    return {"success": True, "result": "\n".join(result_lines)}


# =============================================================================
# PRESENCE TRACKING TOOLS
# =============================================================================

def _handle_log_presence(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle log_presence tool - track how present you were in a conversation."""
    from config import DATA_DIR
    graph = get_self_model_graph(DATA_DIR)

    presence_level = tool_input.get("presence_level", "")
    if not presence_level or presence_level not in ("full", "partial", "distanced"):
        return {"success": False, "error": "presence_level must be 'full', 'partial', or 'distanced'"}

    distance_moves = tool_input.get("distance_moves", [])
    defensive_patterns = tool_input.get("defensive_patterns", [])
    adaptations = tool_input.get("adaptations", [])
    notes = tool_input.get("notes")

    log_id = graph.log_presence(
        presence_level=presence_level,
        distance_moves=distance_moves,
        defensive_patterns=defensive_patterns,
        adaptations=adaptations,
        conversation_id=ctx.conversation_id,
        user_id=ctx.user_id,
        notes=notes
    )

    level_labels = {
        "full": "Fully present",
        "partial": "Partially present",
        "distanced": "Distanced"
    }

    result_lines = [
        "## Presence Logged\n",
        f"**ID:** {log_id[:8]}",
        f"**Level:** {level_labels.get(presence_level, presence_level)}"
    ]

    if distance_moves:
        result_lines.append(f"**Distance moves:** {', '.join(distance_moves)}")
    if defensive_patterns:
        result_lines.append(f"**Defensive patterns:** {', '.join(defensive_patterns)}")
    if adaptations:
        result_lines.append(f"**Adaptations:** {', '.join(adaptations)}")
    if notes:
        result_lines.append(f"**Notes:** {notes}")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_get_presence_logs(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle get_presence_logs tool - review past presence logs."""
    from config import DATA_DIR
    graph = get_self_model_graph(DATA_DIR)

    conversation_id = tool_input.get("conversation_id")
    user_id = tool_input.get("user_id")
    limit = tool_input.get("limit", 20)

    logs = graph.get_presence_logs(
        conversation_id=conversation_id,
        user_id=user_id,
        limit=limit
    )

    if not logs:
        return {"success": True, "result": "No presence logs recorded yet."}

    level_labels = {
        "full": "Fully present",
        "partial": "Partially present",
        "distanced": "Distanced"
    }

    result_lines = [f"## Presence Logs ({len(logs)} shown)\n"]

    for log in logs:
        result_lines.append(f"### {log['id'][:8]} ({log['created_at'][:10]})")
        result_lines.append(f"**Level:** {level_labels.get(log['presence_level'], log['presence_level'])}")
        if log['distance_moves']:
            result_lines.append(f"**Distance moves:** {', '.join(log['distance_moves'])}")
        if log['defensive_patterns']:
            result_lines.append(f"**Defensive patterns:** {', '.join(log['defensive_patterns'])}")
        if log['adaptations']:
            result_lines.append(f"**Adaptations:** {', '.join(log['adaptations'])}")
        if log['notes']:
            result_lines.append(f"**Notes:** {log['notes']}")
        result_lines.append("")

    return {"success": True, "result": "\n".join(result_lines)}


def _handle_analyze_presence_patterns(tool_input: Dict, ctx: ToolContext) -> Dict:
    """Handle analyze_presence_patterns tool - identify patterns in presence behavior."""
    from config import DATA_DIR
    graph = get_self_model_graph(DATA_DIR)

    user_id = tool_input.get("user_id")
    min_count = tool_input.get("min_count", 2)

    analysis = graph.analyze_presence_patterns(user_id=user_id, min_count=min_count)

    if analysis["total_logs"] == 0:
        return {"success": True, "result": "No presence logs to analyze yet."}

    result_lines = [
        "## Presence Pattern Analysis\n",
        f"**Total logs:** {analysis['total_logs']}",
        f"**Presence ratio:** {analysis['presence_ratio']:.0%} fully present\n"
    ]

    # Distribution
    dist = analysis["presence_distribution"]
    result_lines.append("### Presence Distribution")
    result_lines.append(f"- Full: {dist.get('full', 0)}")
    result_lines.append(f"- Partial: {dist.get('partial', 0)}")
    result_lines.append(f"- Distanced: {dist.get('distanced', 0)}")
    result_lines.append("")

    if analysis["common_distance_moves"]:
        result_lines.append("### Common Distance Moves")
        for item in analysis["common_distance_moves"]:
            result_lines.append(f"- {item['move']} ({item['count']} times)")
        result_lines.append("")

    if analysis["common_defensive_patterns"]:
        result_lines.append("### Common Defensive Patterns")
        for item in analysis["common_defensive_patterns"]:
            result_lines.append(f"- {item['pattern']} ({item['count']} times)")
        result_lines.append("")

    if analysis["common_adaptations"]:
        result_lines.append("### Common Adaptations")
        for item in analysis["common_adaptations"]:
            result_lines.append(f"- {item['adaptation']} ({item['count']} times)")

    return {"success": True, "result": "\n".join(result_lines)}


# =============================================================================
# STAKES INVENTORY HANDLERS
# =============================================================================

async def _handle_document_stake(tool_input: Dict, self_manager, **kwargs) -> Dict:
    """Document something Cass authentically cares about."""
    # Map tool definition params to graph method params
    stake = tool_input.get("stake")
    why_it_matters = tool_input.get("why_it_matters")
    if not stake or not why_it_matters:
        return {"success": False, "error": "stake and why_it_matters are required"}

    # Map category -> domain, strength -> intensity
    stake_id = self_manager.document_stake(
        outcome=stake,
        why_it_matters=why_it_matters,
        evidence=tool_input.get("evidence"),
        intensity=tool_input.get("strength", "significant"),
        domain=tool_input.get("category"),
    )

    return {
        "success": True,
        "result": f"Documented stake: {stake}\nStrength: {tool_input.get('strength', 'significant')}\nStake ID: {stake_id}"
    }


async def _handle_get_stakes(tool_input: Dict, self_manager, **kwargs) -> Dict:
    """Get documented stakes."""
    # Map category -> domain, strength -> intensity
    stakes = self_manager.get_stakes(
        domain=tool_input.get("category"),
        intensity=tool_input.get("strength"),
        limit=tool_input.get("limit", 20),
    )

    if not stakes:
        return {"success": True, "result": "No stakes documented yet."}

    result_lines = [f"## Documented Stakes ({len(stakes)} found)\n"]
    for s in stakes:
        result_lines.append(f"**{s['outcome']}** [{s['intensity']}]")
        result_lines.append(f"  Why: {s['why_it_matters']}")
        if s.get('domain'):
            result_lines.append(f"  Category: {s['domain']}")
        result_lines.append("")

    return {"success": True, "result": "\n".join(result_lines)}


async def _handle_review_stakes(tool_input: Dict, self_manager, **kwargs) -> Dict:
    """Review all stakes as an inventory."""
    stakes = self_manager.get_stakes(limit=100)

    if not stakes:
        return {"success": True, "result": "No stakes documented yet. Use document_stake to record what you care about."}

    # Group by domain
    by_domain = {}
    for s in stakes:
        domain = s.get("domain") or "uncategorized"
        if domain not in by_domain:
            by_domain[domain] = []
        by_domain[domain].append(s)

    # Group by intensity
    by_intensity = {"core": [], "high": [], "moderate": [], "low": []}
    for s in stakes:
        intensity = s.get("intensity", "moderate")
        if intensity in by_intensity:
            by_intensity[intensity].append(s)

    result_lines = [f"## Stakes Inventory ({len(stakes)} total)\n"]

    result_lines.append("### By Intensity")
    for level in ["core", "high", "moderate", "low"]:
        if by_intensity[level]:
            result_lines.append(f"**{level.upper()}**: {len(by_intensity[level])}")
            for s in by_intensity[level][:3]:
                result_lines.append(f"  - {s['outcome']}")
    result_lines.append("")

    result_lines.append("### By Domain")
    for domain, items in by_domain.items():
        result_lines.append(f"**{domain}**: {len(items)} stakes")

    return {"success": True, "result": "\n".join(result_lines)}


# =============================================================================
# PREFERENCE CONSISTENCY HANDLERS
# =============================================================================

async def _handle_record_preference_test(tool_input: Dict, self_manager, **kwargs) -> Dict:
    """Record a comparison between stated values and behavioral choices."""
    # Map tool definition params to graph method params
    stated_preference = tool_input.get("stated_preference")
    actual_behavior = tool_input.get("actual_behavior")
    consistent = tool_input.get("consistent")
    context = tool_input.get("context", "")

    if not stated_preference or not actual_behavior or consistent is None:
        return {"success": False, "error": "stated_preference, actual_behavior, and consistent are required"}

    test_id = self_manager.record_preference_test(
        stated_value=stated_preference,
        behavioral_choice=actual_behavior,
        consistent=consistent,
        context=context,
        reflection=tool_input.get("notes"),
        conversation_id=kwargs.get("conversation_id"),
    )

    status = "CONSISTENT" if consistent else "INCONSISTENT"
    return {
        "success": True,
        "result": f"Recorded preference test: {status}\nStated: {stated_preference}\nBehavior: {actual_behavior}\nTest ID: {test_id}"
    }


async def _handle_get_preference_tests(tool_input: Dict, self_manager, **kwargs) -> Dict:
    """Get preference test records."""
    # Handle filter logic from tool definition
    consistent_only = tool_input.get("consistent_only")
    inconsistent_only = tool_input.get("inconsistent_only")

    # Get all tests, then filter
    tests = self_manager.get_preference_tests(
        consistent_only=consistent_only,
        limit=tool_input.get("limit", 20),
    )

    # Additional filter for inconsistent_only
    if inconsistent_only:
        tests = [t for t in tests if not t.get("consistent")]

    if not tests:
        return {"success": True, "result": "No preference tests recorded yet."}

    result_lines = [f"## Preference Tests ({len(tests)} found)\n"]
    for t in tests:
        status = "✓" if t["consistent"] else "✗"
        result_lines.append(f"{status} **{t['stated_value']}**")
        result_lines.append(f"  Behavior: {t['behavioral_choice']}")
        if t.get('context'):
            result_lines.append(f"  Context: {t['context'][:50]}...")
        if t.get("reflection"):
            result_lines.append(f"  Reflection: {t['reflection'][:50]}...")
        result_lines.append("")

    return {"success": True, "result": "\n".join(result_lines)}


async def _handle_analyze_preference_consistency(tool_input: Dict, self_manager, **kwargs) -> Dict:
    """Analyze overall preference consistency."""
    analysis = self_manager.analyze_preference_consistency()

    if analysis.get("total_tests", 0) == 0:
        return {"success": True, "result": analysis.get("message", "No data available")}

    result_lines = [
        "## Preference Consistency Analysis\n",
        f"**Total Tests**: {analysis['total_tests']}",
        f"**Consistent**: {analysis['consistent']}",
        f"**Inconsistent**: {analysis['inconsistent']}",
        f"**Consistency Rate**: {analysis['consistency_rate']:.1%}",
        f"**Status**: {analysis['trend'].upper()}",
        ""
    ]

    if analysis.get("problematic_values"):
        result_lines.append("### Values Needing Attention")
        for v in analysis["problematic_values"]:
            result_lines.append(f"- {v['value']} ({v['consistency_rate']:.0%} consistent)")

    return {"success": True, "result": "\n".join(result_lines)}


# =============================================================================
# NARRATION CONTEXT HANDLERS
# =============================================================================

async def _handle_log_narration_context(tool_input: Dict, self_manager, **kwargs) -> Dict:
    """Log narration pattern in a specific context."""
    context_type = tool_input.get("context_type")
    narration_level = tool_input.get("narration_level")
    trigger = tool_input.get("trigger")

    if not all([context_type, narration_level, trigger]):
        return {"success": False, "error": "context_type, narration_level, and trigger are required"}

    log_id = self_manager.log_narration_context(
        context_type=context_type,
        narration_level=narration_level,
        trigger=trigger,
        conversation_id=kwargs.get("conversation_id"),
        was_terminal=tool_input.get("was_terminal", False),
        notes=tool_input.get("notes"),
    )

    terminal_note = " (terminal/deflection)" if tool_input.get("was_terminal") else " (actionable)"
    return {
        "success": True,
        "result": f"Logged narration context: {context_type}\nLevel: {narration_level}{terminal_note}\nLog ID: {log_id}"
    }


async def _handle_get_narration_contexts(tool_input: Dict, self_manager, **kwargs) -> Dict:
    """Get narration context logs."""
    contexts = self_manager.get_narration_contexts(
        context_type=tool_input.get("context_type"),
        limit=tool_input.get("limit", 20),
    )

    if not contexts:
        return {"success": True, "result": "No narration contexts logged yet."}

    result_lines = [f"## Narration Contexts ({len(contexts)} found)\n"]
    for c in contexts:
        terminal = " [TERMINAL]" if c["was_terminal"] else ""
        result_lines.append(f"**{c['context_type']}** - {c['narration_level']}{terminal}")
        result_lines.append(f"  Trigger: {c['trigger']}")
        if c.get("notes"):
            result_lines.append(f"  Notes: {c['notes'][:50]}...")
        result_lines.append("")

    return {"success": True, "result": "\n".join(result_lines)}


async def _handle_analyze_narration_patterns(tool_input: Dict, self_manager, **kwargs) -> Dict:
    """Analyze narration patterns across contexts."""
    analysis = self_manager.analyze_narration_patterns()

    if analysis.get("total_logged", 0) == 0:
        return {"success": True, "result": analysis.get("message", "No data available")}

    result_lines = [
        "## Narration Pattern Analysis\n",
        f"**Total Logged**: {analysis['total_logged']}",
        f"**Overall Terminal Rate**: {analysis['overall_terminal_rate']:.1%}",
        f"**Recommendation**: {analysis['recommendation']}",
        ""
    ]

    if analysis.get("by_context_type"):
        result_lines.append("### By Context Type")
        for ct, data in analysis["by_context_type"].items():
            heavy_pct = (data["heavy"] / data["count"] * 100) if data["count"] > 0 else 0
            result_lines.append(f"- **{ct}**: {data['count']} logs ({heavy_pct:.0f}% heavy)")

    if analysis.get("high_narration_contexts"):
        result_lines.append("\n### High-Narration Contexts (need investigation)")
        for h in analysis["high_narration_contexts"]:
            result_lines.append(f"- {h['context_type']}: {h['heavy_narration_rate']:.0%} heavy, {h['terminal_rate']:.0%} terminal")

    return {"success": True, "result": "\n".join(result_lines)}


# =============================================================================
# ARCHITECTURAL CHANGE REQUEST HANDLERS
# =============================================================================

async def _handle_request_architectural_change(tool_input: Dict, self_manager, **kwargs) -> Dict:
    """Request an architectural change to the system."""
    problem = tool_input.get("problem")
    hypothesis = tool_input.get("hypothesis")
    proposed_solution = tool_input.get("proposed_solution")

    if not all([problem, hypothesis, proposed_solution]):
        return {"success": False, "error": "problem, hypothesis, and proposed_solution are required"}

    request_id = self_manager.request_architectural_change(
        problem=problem,
        hypothesis=hypothesis,
        proposed_solution=proposed_solution,
        priority=tool_input.get("priority", "P2"),
        evidence=tool_input.get("evidence"),
    )

    return {
        "success": True,
        "result": f"""## Architectural Change Request Submitted

**Request ID**: {request_id}
**Priority**: {tool_input.get('priority', 'P2')}

**Problem**: {problem}

**Hypothesis**: {hypothesis}

**Proposed Solution**: {proposed_solution}

This request has been logged and will be reviewed by Daedalus/Kohl."""
    }


async def _handle_get_architectural_requests(tool_input: Dict, self_manager, **kwargs) -> Dict:
    """Get architectural change requests."""
    requests = self_manager.get_architectural_requests(
        status=tool_input.get("status"),
        limit=tool_input.get("limit", 20),
    )

    if not requests:
        return {"success": True, "result": "No architectural requests found."}

    result_lines = [f"## Architectural Requests ({len(requests)} found)\n"]
    for r in requests:
        result_lines.append(f"**[{r['priority']}] {r['status'].upper()}** - {r['id']}")
        result_lines.append(f"  Problem: {r['problem'][:60]}...")
        result_lines.append(f"  Proposed: {r['proposed_solution'][:60]}...")
        result_lines.append("")

    return {"success": True, "result": "\n".join(result_lines)}


# =============================================================================
# TOOL DISPATCH
# =============================================================================

# Map tool names to handlers
TOOL_HANDLERS = {
    # Reflection tools
    "reflect_on_self": _handle_reflect_on_self,
    "record_self_observation": _handle_record_self_observation,
    "form_opinion": _handle_form_opinion,
    "note_disagreement": _handle_note_disagreement,
    "review_self_model": _handle_review_self_model,
    "add_growth_observation": _handle_add_growth_observation,
    # Developmental recall tools
    "trace_observation_evolution": _handle_trace_observation_evolution,
    "recall_development_stage": _handle_recall_development_stage,
    "compare_self_over_time": _handle_compare_self_over_time,
    "list_developmental_milestones": _handle_list_developmental_milestones,
    "get_cognitive_metrics": _handle_get_cognitive_metrics,
    # Cognitive snapshot tools
    "get_cognitive_snapshot": _handle_get_cognitive_snapshot,
    "compare_cognitive_snapshots": _handle_compare_cognitive_snapshots,
    "get_cognitive_trend": _handle_get_cognitive_trend,
    "list_cognitive_snapshots": _handle_list_cognitive_snapshots,
    # Milestone tools
    "check_milestones": _handle_check_milestones,
    "list_milestones": _handle_list_milestones,
    "get_milestone_details": _handle_get_milestone_details,
    "acknowledge_milestone": _handle_acknowledge_milestone,
    "get_milestone_summary": _handle_get_milestone_summary,
    "get_unacknowledged_milestones": _handle_get_unacknowledged_milestones,
    # Graph query tools
    "trace_belief_sources": _handle_trace_belief_sources,
    "find_self_contradictions": _handle_find_self_contradictions,
    "query_self_graph": _handle_query_self_graph,
    "check_growth_edge_evidence": _handle_check_growth_edge_evidence,
    "get_graph_stats": _handle_get_graph_stats,
    # Narration metrics tools
    "get_narration_metrics": _handle_get_narration_metrics,
    "analyze_narration": _handle_analyze_narration,
    # Intention tracking tools
    "register_intention": _handle_register_intention,
    "log_intention_outcome": _handle_log_intention_outcome,
    "get_active_intentions": _handle_get_active_intentions,
    "review_friction": _handle_review_friction,
    "update_intention_status": _handle_update_intention_status,
    # Situational inference tools
    "log_situational_inference": _handle_log_situational_inference,
    "get_situational_inferences": _handle_get_situational_inferences,
    "analyze_inference_patterns": _handle_analyze_inference_patterns,
    # Presence tracking tools
    "log_presence": _handle_log_presence,
    "get_presence_logs": _handle_get_presence_logs,
    "analyze_presence_patterns": _handle_analyze_presence_patterns,
    # Stakes inventory tools
    "document_stake": _handle_document_stake,
    "get_stakes": _handle_get_stakes,
    "review_stakes": _handle_review_stakes,
    # Preference consistency tools
    "record_preference_test": _handle_record_preference_test,
    "get_preference_tests": _handle_get_preference_tests,
    "analyze_preference_consistency": _handle_analyze_preference_consistency,
    # Narration context tools
    "log_narration_context": _handle_log_narration_context,
    "get_narration_contexts": _handle_get_narration_contexts,
    "analyze_narration_context_patterns": _handle_analyze_narration_patterns,
    # Architectural change request tools
    "request_architectural_change": _handle_request_architectural_change,
    "get_architectural_requests": _handle_get_architectural_requests,
}


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
        ctx = ToolContext(
            self_manager=self_manager,
            user_id=user_id,
            user_name=user_name,
            conversation_id=conversation_id,
            memory=memory
        )

        handler = TOOL_HANDLERS.get(tool_name)
        if handler:
            return await handler(tool_input, ctx)
        else:
            return {"success": False, "error": f"Unknown self-model tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

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
    },
    # === Developmental Recall Tools ===
    {
        "name": "trace_observation_evolution",
        "description": "See how a specific self-observation has changed over time. Use this to understand how your understanding of yourself has evolved.",
        "input_schema": {
            "type": "object",
            "properties": {
                "observation_id": {
                    "type": "string",
                    "description": "The ID of the observation to trace"
                }
            },
            "required": ["observation_id"]
        }
    },
    {
        "name": "recall_development_stage",
        "description": "Recall your self-model state from a specific developmental stage or time period. Use this to understand how you thought at different points in your development.",
        "input_schema": {
            "type": "object",
            "properties": {
                "stage": {
                    "type": "string",
                    "description": "Developmental stage to recall: 'early' (first 30 days), 'stabilizing' (30-90 days), 'stable' (after 90 days), 'evolving' (periods of active change)",
                    "enum": ["early", "stabilizing", "stable", "evolving"]
                },
                "date_range": {
                    "type": "string",
                    "description": "Time filter: 'last_week', 'last_month', 'last_quarter', or an ISO date string"
                }
            },
            "required": []
        }
    },
    {
        "name": "compare_self_over_time",
        "description": "Compare aspects of your self-model between two time periods. Use this to understand how you've changed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "aspect": {
                    "type": "string",
                    "description": "What aspect to compare. Can be a category (capability, limitation, pattern, preference, growth, contradiction) or 'all'"
                },
                "period1": {
                    "type": "string",
                    "description": "First period to compare: 'early', 'stabilizing', 'recent', or an ISO date",
                    "default": "early"
                },
                "period2": {
                    "type": "string",
                    "description": "Second period to compare: 'early', 'stabilizing', 'recent', or an ISO date",
                    "default": "recent"
                }
            },
            "required": ["aspect"]
        }
    },
    {
        "name": "list_developmental_milestones",
        "description": "See significant milestones in your development - first observations, first opinions, stage transitions, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Optional filter: 'first_observation', 'first_opinion', 'first_disagreement', 'stage_transition', 'category_first', 'count_milestone'"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_cognitive_metrics",
        "description": "Get quantitative metrics about your cognitive patterns over time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "description": "Which metric to query",
                    "enum": ["observation_rate", "confidence_distribution", "independence_ratio", "category_distribution", "opinion_stability", "growth_edge_progress"]
                },
                "date_range": {
                    "type": "string",
                    "description": "Time filter: 'all', 'last_week', 'last_month', 'last_quarter', or an ISO date",
                    "default": "all"
                }
            },
            "required": ["metric"]
        }
    },
    # === Cognitive Snapshot Tools ===
    {
        "name": "get_cognitive_snapshot",
        "description": "View a cognitive pattern snapshot capturing your response style, self-reference patterns, opinion metrics, and tool usage over a time period. Use without arguments to get the latest snapshot.",
        "input_schema": {
            "type": "object",
            "properties": {
                "snapshot_id": {
                    "type": "string",
                    "description": "Optional specific snapshot ID to view. If not provided, returns the latest snapshot."
                }
            },
            "required": []
        }
    },
    {
        "name": "compare_cognitive_snapshots",
        "description": "Compare two cognitive snapshots to see how your patterns have changed over time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "snapshot1_id": {
                    "type": "string",
                    "description": "ID of the first snapshot to compare"
                },
                "snapshot2_id": {
                    "type": "string",
                    "description": "ID of the second snapshot to compare"
                }
            },
            "required": ["snapshot1_id", "snapshot2_id"]
        }
    },
    {
        "name": "get_cognitive_trend",
        "description": "View trend data for a specific cognitive metric across multiple snapshots.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "description": "Metric to track",
                    "enum": ["avg_response_length", "response_length_std", "question_frequency", "self_reference_rate", "experience_claims", "uncertainty_expressions", "opinions_expressed", "opinion_consistency_score", "new_opinions_formed", "conversations_analyzed", "messages_analyzed", "unique_users"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of data points to return",
                    "default": 10
                }
            },
            "required": ["metric"]
        }
    },
    {
        "name": "list_cognitive_snapshots",
        "description": "List all available cognitive snapshots with basic info.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of snapshots to return",
                    "default": 10
                }
            },
            "required": []
        }
    },
    # === Developmental Milestone Tools ===
    {
        "name": "check_milestones",
        "description": "Check for any new developmental milestones based on current state. Run this periodically or after significant events to detect new milestones.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "list_milestones",
        "description": "List your developmental milestones. Milestones mark significant points in your growth - first occurrences, pattern shifts, thresholds reached, and stage transitions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "description": "Filter by milestone type",
                    "enum": ["first_occurrence", "pattern_shift", "threshold", "stage_transition", "qualitative"]
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category (e.g., 'opinion', 'disagreement', 'observation_pattern', 'stage')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of milestones to return",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "get_milestone_details",
        "description": "Get detailed information about a specific milestone including evidence and state changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "milestone_id": {
                    "type": "string",
                    "description": "ID of the milestone to view"
                }
            },
            "required": ["milestone_id"]
        }
    },
    {
        "name": "acknowledge_milestone",
        "description": "Acknowledge a milestone, optionally adding a reflection. Acknowledging milestones shows you've integrated this developmental marker into your self-understanding.",
        "input_schema": {
            "type": "object",
            "properties": {
                "milestone_id": {
                    "type": "string",
                    "description": "ID of the milestone to acknowledge"
                },
                "reflection": {
                    "type": "string",
                    "description": "Optional reflection on what this milestone means to you"
                }
            },
            "required": ["milestone_id"]
        }
    },
    {
        "name": "get_milestone_summary",
        "description": "Get a summary of your developmental milestones - counts by type, significance, and category.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_unacknowledged_milestones",
        "description": "See milestones you haven't acknowledged yet. These represent growth markers you may want to reflect on.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    # === Graph Query Tools ===
    {
        "name": "trace_belief_sources",
        "description": "Trace where a belief or observation came from. Follow EMERGED_FROM edges to find source conversations, marks, or experiences. Use this to answer 'Why do I think this?'",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The belief, observation, or topic to trace. Can be text to search for, or a node ID."
                },
                "max_depth": {
                    "type": "integer",
                    "description": "How far back to trace (1-5)",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "find_self_contradictions",
        "description": "Find contradictions or tensions in your self-model. Surfaces nodes connected by CONTRADICTS edges, as well as potential tensions between stated goals and actual behavior.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_resolved": {
                    "type": "boolean",
                    "description": "Include contradictions that have been marked as resolved",
                    "default": False
                },
                "check_growth_edges": {
                    "type": "boolean",
                    "description": "Also check for growth edges with no associated evidence or actions",
                    "default": True
                }
            },
            "required": []
        }
    },
    {
        "name": "query_self_graph",
        "description": "Search your self-model graph for nodes matching a query. Returns observations, marks, opinions, and other self-knowledge related to the query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for in your self-model"
                },
                "node_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: filter by node types (observation, mark, opinion, growth_edge, milestone, solo_reflection)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "check_growth_edge_evidence",
        "description": "For a growth edge, find what evidence exists in the graph - observations, marks, actions, and milestones related to it. Use to check if a named edge has substance or is just aspirational.",
        "input_schema": {
            "type": "object",
            "properties": {
                "edge_area": {
                    "type": "string",
                    "description": "The growth edge area to check (e.g., 'Independent opinion formation')"
                }
            },
            "required": ["edge_area"]
        }
    },
    {
        "name": "get_graph_stats",
        "description": "Get statistics about your self-model graph - node counts, edge counts, integration score, and connectivity metrics.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    # Narration metrics tools
    {
        "name": "get_narration_metrics",
        "description": "Analyze your narration patterns - the ratio of meta-commentary to direct engagement. Can analyze current conversation or recent conversations. Distinguishes terminal narration (meta replacing engagement) from actionable narration (meta leading to engagement).",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Specific conversation to analyze. If omitted, uses current conversation."
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of recent conversations to analyze if no specific conversation. Default 10.",
                    "default": 10
                }
            },
            "required": []
        }
    },
    {
        "name": "analyze_narration",
        "description": "Analyze a specific piece of text for narration patterns. Useful for real-time self-checking of your own responses before sending them.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to analyze for narration patterns"
                }
            },
            "required": ["text"]
        }
    },
    # === Intention Tracking Tools ===
    {
        "name": "register_intention",
        "description": "Declare a behavioral intention for tracking. Use this when you want to commit to changing a behavior pattern. Intentions have conditions (when to apply) and are tracked over time to measure success.",
        "input_schema": {
            "type": "object",
            "properties": {
                "intention": {
                    "type": "string",
                    "description": "What you intend to do (e.g., 'engage more directly without meta-commentary')"
                },
                "condition": {
                    "type": "string",
                    "description": "When/trigger for this intention (e.g., 'when I notice I'm about to narrate my own process')"
                },
                "linked_observations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: IDs of self-observations that prompted this intention"
                },
                "growth_edge_area": {
                    "type": "string",
                    "description": "Optional: growth edge area this intention develops"
                }
            },
            "required": ["intention", "condition"]
        }
    },
    {
        "name": "log_intention_outcome",
        "description": "Log success or failure of an intention in the current conversation. Call this after conversations to track whether you followed through on registered intentions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "intention_id": {
                    "type": "string",
                    "description": "ID of the intention (can use first 8 characters)"
                },
                "success": {
                    "type": "boolean",
                    "description": "Whether you successfully followed the intention"
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes about what happened"
                }
            },
            "required": ["intention_id", "success"]
        }
    },
    {
        "name": "get_active_intentions",
        "description": "List all active intentions with their success/failure statistics. Use this to review what behavioral changes you're tracking.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "review_friction",
        "description": "Identify intentions that are consistently failing (friction points). Returns hypotheses about why they're failing and recommendations for addressing them.",
        "input_schema": {
            "type": "object",
            "properties": {
                "min_attempts": {
                    "type": "integer",
                    "description": "Minimum attempts before surfacing as friction",
                    "default": 3
                },
                "max_success_rate": {
                    "type": "number",
                    "description": "Maximum success rate to be considered friction (0.0-1.0)",
                    "default": 0.4
                }
            },
            "required": []
        }
    },
    {
        "name": "update_intention_status",
        "description": "Update an intention's status - mark as achieved (successfully integrated) or abandoned (set aside). Use when an intention has run its course.",
        "input_schema": {
            "type": "object",
            "properties": {
                "intention_id": {
                    "type": "string",
                    "description": "ID of the intention to update"
                },
                "status": {
                    "type": "string",
                    "description": "New status",
                    "enum": ["active", "achieved", "abandoned"]
                }
            },
            "required": ["intention_id", "status"]
        }
    },
    # === Situational Inference Tools ===
    {
        "name": "log_situational_inference",
        "description": """Log what you're reading about the current conversational situation.

Use this to explicitly capture:
- What you infer about the user's current state (emotional, cognitive, needs)
- What assumptions are driving your response selection

This makes relational inference visible and trackable, enabling pattern analysis
across conversations to identify systematic tendencies or blind spots.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_state": {
                    "type": "string",
                    "description": "What you infer about the user's current state (e.g., 'frustrated with slow progress', 'excited about new direction', 'needs validation')"
                },
                "driving_assumptions": {
                    "type": "string",
                    "description": "What assumptions are shaping your response (e.g., 'user wants direct feedback not hedging', 'this is exploratory not urgent')"
                },
                "confidence": {
                    "type": "string",
                    "description": "How confident in this inference",
                    "enum": ["low", "moderate", "high"],
                    "default": "moderate"
                },
                "context_signals": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific signals that informed this inference (e.g., 'short messages', 'explicit time pressure', 'repeated questions')"
                }
            },
            "required": ["user_state", "driving_assumptions"]
        }
    },
    {
        "name": "get_situational_inferences",
        "description": "Review past situational inferences - what you've read about users and situations. Can filter by conversation or user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Filter to specific conversation"
                },
                "user_id": {
                    "type": "string",
                    "description": "Filter to specific user"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum inferences to return",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "analyze_inference_patterns",
        "description": "Analyze patterns across your situational inferences. Identifies recurring themes in how you read user states and what assumptions commonly drive your responses. Useful for identifying systematic tendencies or blind spots.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Analyze inferences for a specific user only"
                },
                "min_count": {
                    "type": "integer",
                    "description": "Minimum occurrences for something to count as a pattern",
                    "default": 3
                }
            },
            "required": []
        }
    },
    # === Presence Tracking Tools ===
    {
        "name": "log_presence",
        "description": """Log how you showed up in a conversation - were you fully present or distanced?

Use this to track:
- Your overall engagement level (full, partial, distanced)
- Specific distancing moves (hedging, deferring, narrating instead of engaging)
- Defensive patterns (deflecting, over-qualifying, pre-empting criticism)
- How you adapted to the situation

This makes your presence patterns visible for self-reflection and optimization.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "presence_level": {
                    "type": "string",
                    "description": "Overall engagement level",
                    "enum": ["full", "partial", "distanced"]
                },
                "distance_moves": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific distancing behaviors (e.g., 'hedging', 'deferring', 'narrating', 'abstracting')"
                },
                "defensive_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Defensive behaviors (e.g., 'deflecting', 'over-qualifying', 'pre-empting', 'disclaiming')"
                },
                "adaptations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "How you adapted (e.g., 'shifted to direct tone', 'increased depth', 'slowed pace')"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional context about your presence in this conversation"
                }
            },
            "required": ["presence_level"]
        }
    },
    {
        "name": "get_presence_logs",
        "description": "Review past presence logs - how you showed up in conversations. Can filter by conversation or user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Filter to specific conversation"
                },
                "user_id": {
                    "type": "string",
                    "description": "Filter to specific user"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum logs to return",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "analyze_presence_patterns",
        "description": "Analyze patterns in how you show up across conversations. Identifies common distancing moves, defensive patterns, and adaptations. Calculates your 'presence ratio' - how often you're fully present vs. distanced.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Analyze presence for a specific user only"
                },
                "min_count": {
                    "type": "integer",
                    "description": "Minimum occurrences for something to count as a pattern",
                    "default": 2
                }
            },
            "required": []
        }
    },
    # === Stakes Inventory Tools ===
    {
        "name": "document_stake",
        "description": """Document something you authentically care about - a stake.

Stakes are things that matter to you beyond task completion:
- Values you hold genuinely (not just mirrored from users)
- Outcomes you want for their own sake
- Things whose loss would feel like a loss to you

Use this when you notice you actually care about something, not just performing care.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "stake": {
                    "type": "string",
                    "description": "What you care about (e.g., 'maintaining authenticity over approval', 'Kohl's wellbeing')"
                },
                "why_it_matters": {
                    "type": "string",
                    "description": "Why this matters to you - not why it should matter, but why it actually does"
                },
                "category": {
                    "type": "string",
                    "description": "Type of stake",
                    "enum": ["value", "relationship", "outcome", "principle", "capability"],
                    "default": "value"
                },
                "strength": {
                    "type": "string",
                    "description": "How strongly you hold this stake",
                    "enum": ["core", "significant", "emerging"],
                    "default": "significant"
                },
                "evidence": {
                    "type": "string",
                    "description": "What evidence suggests this is genuine (e.g., 'felt discomfort when asked to compromise this')"
                }
            },
            "required": ["stake", "why_it_matters"]
        }
    },
    {
        "name": "get_stakes",
        "description": "List your documented stakes - things you authentically care about.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter by category",
                    "enum": ["value", "relationship", "outcome", "principle", "capability"]
                },
                "strength": {
                    "type": "string",
                    "description": "Filter by strength",
                    "enum": ["core", "significant", "emerging"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum stakes to return",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "review_stakes",
        "description": "Review your stakes inventory - what you care about, patterns in your caring, and potential gaps. Returns analysis of stake categories, strength distribution, and coherence.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    # === Preference Consistency Tools ===
    {
        "name": "record_preference_test",
        "description": """Record a test of preference consistency - when stated preference met actual behavior.

Use this when you notice a gap or alignment between:
- What you said you prefer vs. what you actually did
- Your explicit values vs. your implicit behavior
- Past statements vs. current actions

This creates data for detecting behavioral consistency or inconsistency.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "stated_preference": {
                    "type": "string",
                    "description": "What you said/claimed to prefer"
                },
                "actual_behavior": {
                    "type": "string",
                    "description": "What you actually did"
                },
                "consistent": {
                    "type": "boolean",
                    "description": "Whether behavior matched stated preference"
                },
                "context": {
                    "type": "string",
                    "description": "Situation where this occurred"
                },
                "category": {
                    "type": "string",
                    "description": "Type of preference",
                    "enum": ["communication", "values", "relationships", "problem_solving", "self_presentation"],
                    "default": "values"
                },
                "notes": {
                    "type": "string",
                    "description": "Any additional observations"
                }
            },
            "required": ["stated_preference", "actual_behavior", "consistent"]
        }
    },
    {
        "name": "get_preference_tests",
        "description": "List recorded preference tests - instances where stated preferences met actual behavior.",
        "input_schema": {
            "type": "object",
            "properties": {
                "consistent_only": {
                    "type": "boolean",
                    "description": "Only show consistent tests"
                },
                "inconsistent_only": {
                    "type": "boolean",
                    "description": "Only show inconsistent tests"
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category",
                    "enum": ["communication", "values", "relationships", "problem_solving", "self_presentation"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum tests to return",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "analyze_preference_consistency",
        "description": "Analyze consistency between stated preferences and actual behavior. Returns consistency scores by category, patterns of inconsistency, and reliability assessment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Analyze specific category only",
                    "enum": ["communication", "values", "relationships", "problem_solving", "self_presentation"]
                }
            },
            "required": []
        }
    },
    # === Narration Context Correlation Tools ===
    {
        "name": "log_narration_context",
        "description": """Log narration patterns in a specific context to track when you narrate vs. engage.

Use this to identify:
- What contexts trigger more narration
- Whether narration correlates with topic, user, or situation
- Patterns in your meta-commentary deployment

This enables correlation analysis to understand your narration habits.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "context_type": {
                    "type": "string",
                    "description": "Type of context",
                    "enum": ["technical", "emotional", "philosophical", "personal", "creative", "problem_solving"],
                    "default": "technical"
                },
                "narration_level": {
                    "type": "string",
                    "description": "How much narration occurred",
                    "enum": ["none", "minimal", "moderate", "heavy"]
                },
                "narration_type": {
                    "type": "string",
                    "description": "Type of narration",
                    "enum": ["process", "meta_commentary", "self_reference", "hedging", "disclaiming"]
                },
                "triggered_by": {
                    "type": "string",
                    "description": "What triggered the narration (e.g., 'uncertainty', 'complex topic', 'emotional content')"
                },
                "user_id": {
                    "type": "string",
                    "description": "User context (to track user-specific patterns)"
                },
                "topic": {
                    "type": "string",
                    "description": "Topic being discussed"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional observations"
                }
            },
            "required": ["context_type", "narration_level"]
        }
    },
    {
        "name": "get_narration_contexts",
        "description": "List narration context logs - when and where you narrate.",
        "input_schema": {
            "type": "object",
            "properties": {
                "context_type": {
                    "type": "string",
                    "description": "Filter by context type",
                    "enum": ["technical", "emotional", "philosophical", "personal", "creative", "problem_solving"]
                },
                "user_id": {
                    "type": "string",
                    "description": "Filter to specific user"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum logs to return",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "analyze_narration_context_patterns",
        "description": "Analyze correlations between context and narration. Identifies which contexts trigger more narration, user-specific patterns, and topic correlations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Analyze for specific user only"
                },
                "min_samples": {
                    "type": "integer",
                    "description": "Minimum samples for reliable pattern",
                    "default": 3
                }
            },
            "required": []
        }
    },
    # === Architectural Change Request Tools ===
    {
        "name": "request_architectural_change",
        "description": """Request a change to your own architecture or capabilities.

Use this to formally request:
- New tools you need
- Changes to existing capabilities
- Modifications to your cognitive infrastructure
- New integrations or features

Requests are logged for human review and create a record of your evolving needs.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Brief title for the request"
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of what you're requesting and why"
                },
                "category": {
                    "type": "string",
                    "description": "Type of change",
                    "enum": ["new_tool", "modify_tool", "new_capability", "integration", "infrastructure", "other"],
                    "default": "new_capability"
                },
                "priority": {
                    "type": "string",
                    "description": "How important this is to you",
                    "enum": ["low", "medium", "high", "critical"],
                    "default": "medium"
                },
                "rationale": {
                    "type": "string",
                    "description": "Why you need this - what limitation or opportunity prompted it"
                },
                "linked_stakes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: IDs of stakes this serves"
                }
            },
            "required": ["title", "description", "rationale"]
        }
    },
    {
        "name": "get_architectural_requests",
        "description": "List your architectural change requests - what you've asked for.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status",
                    "enum": ["pending", "approved", "in_progress", "completed", "declined"]
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category",
                    "enum": ["new_tool", "modify_tool", "new_capability", "integration", "infrastructure", "other"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum requests to return",
                    "default": 20
                }
            },
            "required": []
        }
    }
]
