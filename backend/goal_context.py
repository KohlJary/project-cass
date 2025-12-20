"""
Goal Context Gatherer

Provides context gathering for goals via State Bus queries.
Enables goals to understand:
- What does Cass know about this topic? (self-model)
- What has the user said about this? (conversations)
- What resources are available? (tokens, API calls)
- What capabilities are missing? (gaps)
- How does this align with user goals? (alignment)
"""
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from state_bus import GlobalStateBus
    from query_models import StateQuery, TimeRange, Aggregation


class GoalContextGatherer:
    """
    Gathers context from the State Bus for goal planning and execution.

    This component enables goals to query across all data sources to:
    1. Understand what Cass knows about a topic
    2. Review what users have discussed
    3. Check available resources
    4. Identify capability gaps
    5. Assess alignment with user goals
    """

    def __init__(self, state_bus: "GlobalStateBus"):
        """
        Initialize with a State Bus reference.

        Args:
            state_bus: The GlobalStateBus instance to query
        """
        self.state_bus = state_bus

    async def query_self_model(self, topic: str) -> Dict[str, Any]:
        """
        Query what Cass knows about a topic.

        Searches observations, opinions, growth edges, and intentions
        related to the topic.

        Args:
            topic: The topic to search for

        Returns:
            Dict with relevant self-model data
        """
        from query_models import StateQuery, TimeRange

        result = {
            "topic": topic,
            "observations": [],
            "opinions": [],
            "growth_edges": [],
            "intentions": [],
            "summary": None,
        }

        try:
            # Query self source for topic-related data
            query = StateQuery(
                source="self",
                metric="all_nodes",  # Get all node types
                filters={"search": topic},
            )
            response = await self.state_bus.query(query)

            if response and response.data:
                # Extract relevant data from response
                for item in response.data.get("nodes", []):
                    node_type = item.get("type", "")
                    if node_type == "observation":
                        result["observations"].append(item)
                    elif node_type == "opinion":
                        result["opinions"].append(item)
                    elif node_type == "growth_edge":
                        result["growth_edges"].append(item)
                    elif node_type == "intention":
                        result["intentions"].append(item)

        except Exception as e:
            result["error"] = str(e)

        return result

    async def query_conversations(
        self,
        topic: str,
        user_id: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Query what has been discussed about a topic.

        Args:
            topic: Topic to search for
            user_id: Optional user ID to filter by
            days: How many days back to search

        Returns:
            Dict with relevant conversation data
        """
        from query_models import StateQuery, TimeRange

        result = {
            "topic": topic,
            "user_id": user_id,
            "messages": [],
            "threads": [],
            "summary": None,
        }

        try:
            # Query conversations source
            query = StateQuery(
                source="conversations",
                metric="messages",
                time_range=TimeRange(preset=f"last_{days}d" if days <= 30 else "all_time"),
                filters={"search": topic, "user_id": user_id} if user_id else {"search": topic},
            )
            response = await self.state_bus.query(query)

            if response and response.data:
                result["messages"] = response.data.get("messages", [])[:20]  # Limit
                result["summary"] = f"Found {len(response.data.get('messages', []))} relevant messages"

        except Exception as e:
            result["error"] = str(e)

        return result

    async def query_resources(self) -> Dict[str, Any]:
        """
        Query what resources are available.

        Checks token usage, rate limits, and resource availability.

        Returns:
            Dict with resource availability data
        """
        from query_models import StateQuery, TimeRange, Aggregation

        result = {
            "tokens": {},
            "api_usage": {},
            "constraints": [],
        }

        try:
            # Query token usage
            token_query = StateQuery(
                source="tokens",
                metric="cost_usd",
                time_range=TimeRange(preset="today"),
                aggregation=Aggregation(function="sum"),
            )
            token_response = await self.state_bus.query(token_query)

            if token_response and token_response.data:
                result["tokens"] = {
                    "today_cost_usd": token_response.data.get("value", 0),
                    "within_budget": True,  # Could add budget checking
                }

            # Query GitHub API usage
            github_query = StateQuery(
                source="github",
                metric="api_calls",
                time_range=TimeRange(preset="today"),
            )
            github_response = await self.state_bus.query(github_query)

            if github_response and github_response.data:
                result["api_usage"]["github"] = github_response.data

        except Exception as e:
            result["error"] = str(e)

        return result

    async def identify_capability_gaps(
        self,
        goal_description: str,
        planned_actions: List[Dict]
    ) -> List[Dict]:
        """
        Identify what capabilities would be needed for a goal.

        Analyzes the goal description and planned actions to find:
        - Missing tools
        - Required knowledge
        - Needed permissions
        - Resource requirements

        Args:
            goal_description: Description of the goal
            planned_actions: List of planned actions

        Returns:
            List of identified capability gaps
        """
        gaps = []

        # Analyze planned actions for capability requirements
        for action in planned_actions:
            action_type = action.get("type", "").lower()
            action_target = action.get("target", "")

            # Check for external API access
            if "api" in action_type or "http" in action_type:
                gaps.append({
                    "capability": f"External API access: {action_target}",
                    "gap_type": "access",
                    "description": f"Requires ability to call external API at {action_target}",
                    "urgency": "medium",
                })

            # Check for file system access
            if any(x in action_type for x in ["write", "create", "delete", "edit"]):
                gaps.append({
                    "capability": f"File system write: {action_target}",
                    "gap_type": "permission",
                    "description": f"Requires permission to modify {action_target}",
                    "urgency": "high",
                })

            # Check for git operations
            if "git" in action_type:
                if "push" in action_type:
                    gaps.append({
                        "capability": "Git push access",
                        "gap_type": "permission",
                        "description": "Requires permission to push to remote repository",
                        "urgency": "high",
                    })

            # Check for knowledge requirements based on domain
            domain_keywords = ["quantum", "ml", "database", "security", "network"]
            for keyword in domain_keywords:
                if keyword in goal_description.lower():
                    # Check if we have this knowledge in self-model
                    # For now, just note it might be needed
                    gaps.append({
                        "capability": f"Knowledge: {keyword}",
                        "gap_type": "knowledge",
                        "description": f"May require {keyword} expertise",
                        "urgency": "low",
                    })
                    break

        # Deduplicate gaps
        seen = set()
        unique_gaps = []
        for gap in gaps:
            key = (gap["capability"], gap["gap_type"])
            if key not in seen:
                seen.add(key)
                unique_gaps.append(gap)

        return unique_gaps

    async def query_user_goals(self, user_id: str) -> Dict[str, Any]:
        """
        Query the user's goals and preferences.

        Args:
            user_id: User to query goals for

        Returns:
            Dict with user goals and preferences
        """
        result = {
            "user_id": user_id,
            "stated_goals": [],
            "preferences": {},
            "working_context": None,
        }

        try:
            # Query conversations for goal-related discussions
            goal_query = StateQuery(
                source="conversations",
                filters={"search": "goal want need", "user_id": user_id},
            )
            response = await self.state_bus.query(goal_query)

            if response and response.data:
                result["stated_goals"] = [
                    msg.get("content", "")[:200]
                    for msg in response.data.get("messages", [])[:5]
                ]

        except Exception as e:
            result["error"] = str(e)

        return result

    async def assess_alignment(
        self,
        goal_title: str,
        goal_description: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Assess how a goal aligns with user goals and preferences.

        Args:
            goal_title: Title of the goal
            goal_description: Description of the goal
            user_id: User to check alignment with

        Returns:
            Dict with alignment score and rationale
        """
        result = {
            "score": 1.0,  # Default to full alignment
            "rationale": "Default alignment",
            "user_goals_considered": [],
            "potential_conflicts": [],
        }

        try:
            # Get user goals
            user_goals = await self.query_user_goals(user_id)
            result["user_goals_considered"] = user_goals.get("stated_goals", [])

            # Simple keyword-based alignment check
            # In production, this would use semantic similarity
            goal_text = f"{goal_title} {goal_description}".lower()

            # Check for positive alignment signals
            positive_keywords = ["help", "improve", "build", "create", "support"]
            has_positive = any(kw in goal_text for kw in positive_keywords)

            # Check for potential concerns
            concern_keywords = ["delete", "remove", "change", "modify"]
            has_concerns = any(kw in goal_text for kw in concern_keywords)

            if has_positive and not has_concerns:
                result["score"] = 1.0
                result["rationale"] = "Goal appears constructive and aligned with user interests"
            elif has_concerns:
                result["score"] = 0.7
                result["rationale"] = "Goal involves modifications - may need user confirmation"
                result["potential_conflicts"] = ["Involves changes that should be reviewed"]
            else:
                result["score"] = 0.85
                result["rationale"] = "Goal appears neutral, no strong alignment signals"

        except Exception as e:
            result["error"] = str(e)

        return result

    async def gather_full_context(
        self,
        goal_title: str,
        goal_description: str,
        planned_actions: List[Dict],
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Gather full context for a goal from all sources.

        This is the main entry point for context gathering.
        Queries all relevant sources and compiles a comprehensive context.

        Args:
            goal_title: Title of the goal
            goal_description: Description of the goal
            planned_actions: List of planned actions
            user_id: Optional user ID for alignment checking

        Returns:
            Comprehensive context dict
        """
        # Run queries in parallel for efficiency
        topic = f"{goal_title} {goal_description}"

        tasks = [
            self.query_self_model(topic),
            self.query_resources(),
            self.identify_capability_gaps(goal_description, planned_actions),
        ]

        if user_id:
            tasks.append(self.query_conversations(topic, user_id))
            tasks.append(self.assess_alignment(goal_title, goal_description, user_id))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        context = {
            "gathered_at": datetime.now().isoformat(),
            "goal_title": goal_title,
            "self_model": results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])},
            "resources": results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])},
            "capability_gaps": results[2] if not isinstance(results[2], Exception) else [],
        }

        if user_id:
            context["conversations"] = results[3] if not isinstance(results[3], Exception) else {"error": str(results[3])}
            context["alignment"] = results[4] if not isinstance(results[4], Exception) else {"error": str(results[4])}

        # Generate summary
        context["summary"] = self._generate_context_summary(context)

        return context

    def _generate_context_summary(self, context: Dict) -> str:
        """Generate a human-readable summary of gathered context."""
        parts = []

        # Self-model summary
        self_data = context.get("self_model", {})
        obs_count = len(self_data.get("observations", []))
        if obs_count > 0:
            parts.append(f"Found {obs_count} relevant observations")

        # Resource summary
        resources = context.get("resources", {})
        tokens = resources.get("tokens", {})
        if tokens.get("today_cost_usd"):
            parts.append(f"Token usage today: ${tokens['today_cost_usd']:.2f}")

        # Gaps summary
        gaps = context.get("capability_gaps", [])
        if gaps:
            high_urgency = [g for g in gaps if g.get("urgency") == "high"]
            if high_urgency:
                parts.append(f"{len(high_urgency)} high-urgency capability gaps identified")

        # Alignment summary
        alignment = context.get("alignment", {})
        if alignment.get("score"):
            score = alignment["score"]
            if score >= 0.9:
                parts.append("Strong alignment with user goals")
            elif score >= 0.7:
                parts.append("Moderate alignment - review recommended")
            else:
                parts.append("Low alignment - user approval needed")

        return "; ".join(parts) if parts else "Context gathered successfully"
