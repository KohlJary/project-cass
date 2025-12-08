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

        # === Developmental Recall Tools ===

        elif tool_name == "trace_observation_evolution":
            observation_id = tool_input["observation_id"]

            # Get the observation
            obs = self_manager.get_observation_by_id(observation_id)
            if not obs:
                return {
                    "success": False,
                    "error": f"Observation with ID '{observation_id}' not found."
                }

            # Get full history
            history = self_manager.get_observation_history(observation_id)

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

            # Show related observations
            if obs.related_observations:
                result_lines.append("\n### Related Observations")
                for rel_id in obs.related_observations[:5]:
                    rel_obs = self_manager.get_observation_by_id(rel_id)
                    if rel_obs:
                        result_lines.append(f"- {rel_obs.observation[:100]}...")

            return {
                "success": True,
                "result": "\n".join(result_lines)
            }

        elif tool_name == "recall_development_stage":
            stage = tool_input.get("stage")
            date_range = tool_input.get("date_range")

            from datetime import datetime, timedelta

            observations = self_manager.load_observations()

            # Filter by stage if specified
            if stage:
                filtered = [o for o in observations if o.developmental_stage == stage]
            else:
                filtered = observations

            # Filter by date range if specified
            if date_range:
                try:
                    if date_range == "last_week":
                        cutoff = datetime.now() - timedelta(days=7)
                    elif date_range == "last_month":
                        cutoff = datetime.now() - timedelta(days=30)
                    elif date_range == "last_quarter":
                        cutoff = datetime.now() - timedelta(days=90)
                    else:
                        # Try to parse as date
                        cutoff = datetime.fromisoformat(date_range)

                    filtered = [
                        o for o in filtered
                        if datetime.fromisoformat(o.timestamp.replace('Z', '+00:00')).replace(tzinfo=None) >= cutoff
                    ]
                except:
                    pass

            # Sort by timestamp
            filtered.sort(key=lambda x: x.timestamp)

            result_lines = ["## Development Stage Recall\n"]

            if stage:
                result_lines.append(f"**Stage:** {stage}")
            if date_range:
                result_lines.append(f"**Date range:** {date_range}")

            result_lines.append(f"**Observations found:** {len(filtered)}\n")

            # Group by category
            by_category = {}
            for obs in filtered:
                if obs.category not in by_category:
                    by_category[obs.category] = []
                by_category[obs.category].append(obs)

            for category, obs_list in by_category.items():
                result_lines.append(f"### {category.title()} ({len(obs_list)})")
                for obs in obs_list[-5:]:  # Show last 5 per category
                    date_str = obs.timestamp[:10]
                    result_lines.append(f"- [{date_str}] {obs.observation}")
                if len(obs_list) > 5:
                    result_lines.append(f"  *...and {len(obs_list) - 5} more*")
                result_lines.append("")

            # Include profile state summary
            profile = self_manager.load_profile()
            result_lines.append("### Self-Model State")
            result_lines.append(f"- Identity statements: {len(profile.identity_statements)}")
            result_lines.append(f"- Opinions formed: {len(profile.opinions)}")
            result_lines.append(f"- Growth edges: {len(profile.growth_edges)}")

            return {
                "success": True,
                "result": "\n".join(result_lines)
            }

        elif tool_name == "compare_self_over_time":
            aspect = tool_input["aspect"]
            period1 = tool_input.get("period1", "early")
            period2 = tool_input.get("period2", "recent")

            from datetime import datetime, timedelta

            observations = self_manager.load_observations()
            now = datetime.now()

            # Define periods
            def get_period_observations(period_name):
                if period_name == "early":
                    # First 30 days
                    if observations:
                        earliest = min(observations, key=lambda o: o.timestamp)
                        start = datetime.fromisoformat(earliest.timestamp.replace('Z', '+00:00')).replace(tzinfo=None)
                        end = start + timedelta(days=30)
                    else:
                        return []
                elif period_name == "recent":
                    # Last 14 days
                    start = now - timedelta(days=14)
                    end = now
                elif period_name == "stabilizing":
                    # Days 30-90
                    if observations:
                        earliest = min(observations, key=lambda o: o.timestamp)
                        base = datetime.fromisoformat(earliest.timestamp.replace('Z', '+00:00')).replace(tzinfo=None)
                        start = base + timedelta(days=30)
                        end = base + timedelta(days=90)
                    else:
                        return []
                else:
                    # Try to parse as date
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

            # Filter by aspect if it's a category
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

            # Calculate some metrics
            result_lines.append("\n### Comparison Metrics")
            if period1_obs and period2_obs:
                avg_conf_1 = sum(o.confidence for o in period1_obs) / len(period1_obs)
                avg_conf_2 = sum(o.confidence for o in period2_obs) / len(period2_obs)
                result_lines.append(f"- Average confidence: {int(avg_conf_1 * 100)}% → {int(avg_conf_2 * 100)}%")

                # Independence tracking
                indep_1 = len([o for o in period1_obs if o.influence_source == "independent"])
                indep_2 = len([o for o in period2_obs if o.influence_source == "independent"])
                result_lines.append(f"- Independent observations: {indep_1} → {indep_2}")
            else:
                result_lines.append("*Insufficient data for comparison*")

            return {
                "success": True,
                "result": "\n".join(result_lines)
            }

        elif tool_name == "list_developmental_milestones":
            category = tool_input.get("category")

            observations = self_manager.load_observations()
            profile = self_manager.load_profile()
            disagreements = self_manager.load_disagreements()

            result_lines = ["## Developmental Milestones\n"]

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

            # Stage transitions (look for first observation in each stage)
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

            # Category milestones (first observation in each category)
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

            # Sort by date
            milestones.sort(key=lambda m: m["date"])

            if milestones:
                for m in milestones:
                    result_lines.append(f"**{m['date']}** - {m['description']}")
            else:
                result_lines.append("*No milestones detected yet.*")

            return {
                "success": True,
                "result": "\n".join(result_lines)
            }

        elif tool_name == "get_cognitive_metrics":
            metric = tool_input["metric"]
            date_range = tool_input.get("date_range", "all")

            from datetime import datetime, timedelta

            observations = self_manager.load_observations()
            profile = self_manager.load_profile()

            # Filter by date range
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
                # Observations per week
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
                # How often opinions change
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
                evaluations = self_manager.load_growth_evaluations()
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

            return {
                "success": True,
                "result": "\n".join(result_lines)
            }

        # === Cognitive Snapshot Tools ===
        elif tool_name == "get_cognitive_snapshot":
            # Return latest snapshot or compare snapshots
            snapshot_id = tool_input.get("snapshot_id")

            if snapshot_id:
                # Get specific snapshot
                snapshots = self_manager.load_snapshots()
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
                # Get latest snapshot
                snapshot = self_manager.get_latest_snapshot()
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

        elif tool_name == "compare_cognitive_snapshots":
            snapshot1_id = tool_input.get("snapshot1_id")
            snapshot2_id = tool_input.get("snapshot2_id")

            if not snapshot1_id or not snapshot2_id:
                return {"success": False, "error": "Both snapshot IDs required"}

            comparison = self_manager.compare_snapshots(snapshot1_id, snapshot2_id)
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

        elif tool_name == "get_cognitive_trend":
            metric = tool_input.get("metric", "avg_response_length")
            limit = tool_input.get("limit", 10)

            trend_data = self_manager.get_metric_trend(metric, limit)
            if not trend_data:
                return {"success": True, "result": f"No trend data available for metric: {metric}"}

            result_lines = [f"## Cognitive Trend: {metric}\n"]
            for point in trend_data:
                result_lines.append(f"- {point['period_start'][:10]}: {point['value']}")

            return {"success": True, "result": "\n".join(result_lines)}

        elif tool_name == "list_cognitive_snapshots":
            limit = tool_input.get("limit", 10)
            snapshots = self_manager.load_snapshots()
            snapshots.sort(key=lambda s: s.timestamp, reverse=True)
            snapshots = snapshots[:limit]

            if not snapshots:
                return {"success": True, "result": "No cognitive snapshots have been created yet."}

            result_lines = ["## Cognitive Snapshots\n"]
            for s in snapshots:
                result_lines.append(f"**{s.id[:8]}** - {s.period_start[:10]} to {s.period_end[:10]}")
                result_lines.append(f"  Stage: {s.developmental_stage} | Messages: {s.messages_analyzed} | Users: {s.unique_users}")

            return {"success": True, "result": "\n".join(result_lines)}

        # === Developmental Milestone Tools ===
        elif tool_name == "check_milestones":
            # Trigger milestone check and return any new ones
            new_milestones = self_manager.check_for_milestones()

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

        elif tool_name == "list_milestones":
            milestone_type = tool_input.get("type")
            category = tool_input.get("category")
            limit = tool_input.get("limit", 20)

            milestones = self_manager.load_milestones()

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

        elif tool_name == "get_milestone_details":
            milestone_id = tool_input.get("milestone_id")
            if not milestone_id:
                return {"success": False, "error": "milestone_id is required"}

            milestone = self_manager.get_milestone_by_id(milestone_id)
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

        elif tool_name == "acknowledge_milestone":
            milestone_id = tool_input.get("milestone_id")
            reflection = tool_input.get("reflection", "")

            if not milestone_id:
                return {"success": False, "error": "milestone_id is required"}

            success = self_manager.acknowledge_milestone(milestone_id)
            if not success:
                return {"success": False, "error": "Milestone not found"}

            milestone = self_manager.get_milestone_by_id(milestone_id)
            return {
                "success": True,
                "result": f"Acknowledged milestone: {milestone.title}\n\n*Reflection:* {reflection}" if reflection else f"Acknowledged milestone: {milestone.title}"
            }

        elif tool_name == "get_milestone_summary":
            summary = self_manager.get_milestone_summary()

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

        elif tool_name == "get_unacknowledged_milestones":
            milestones = self_manager.get_unacknowledged_milestones()

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
    }
]
