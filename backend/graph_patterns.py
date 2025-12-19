"""
Pattern analysis for SelfModelGraph.
Handles analyzing inference and presence patterns.
Extracted from SelfModelGraph for modularity.
"""
from typing import Dict, Optional, List, Callable


class PatternAnalyzer:
    """
    Analyzes patterns in the self-model graph.

    Extracted from SelfModelGraph to separate pattern analysis
    from graph structure and sync operations.
    """

    def __init__(
        self,
        get_situational_inferences_fn: Callable,
        get_presence_logs_fn: Callable
    ):
        """
        Args:
            get_situational_inferences_fn: Function to get situational inferences
            get_presence_logs_fn: Function to get presence logs
        """
        self._get_situational_inferences = get_situational_inferences_fn
        self._get_presence_logs = get_presence_logs_fn

    def analyze_inference_patterns(
        self,
        user_id: Optional[str] = None,
        min_count: int = 3
    ) -> Dict:
        """
        Analyze patterns across situational inferences.

        Identifies recurring themes in user state readings and
        assumptions to surface systematic patterns or blind spots.

        Args:
            user_id: Optional filter to specific user
            min_count: Minimum occurrences to count as pattern

        Returns:
            Dict with pattern analysis
        """
        inferences = self._get_situational_inferences(user_id=user_id, limit=100)

        if not inferences:
            return {
                "total_inferences": 0,
                "common_user_states": [],
                "common_assumptions": [],
                "confidence_distribution": {},
                "signal_frequency": {}
            }

        # Track patterns
        user_state_words = {}
        assumption_words = {}
        confidence_counts = {"low": 0, "moderate": 0, "high": 0}
        signal_counts = {}

        for inf in inferences:
            # Count confidence levels
            conf = inf.get("confidence", "moderate")
            confidence_counts[conf] = confidence_counts.get(conf, 0) + 1

            # Count context signals
            for signal in inf.get("context_signals", []):
                signal_counts[signal] = signal_counts.get(signal, 0) + 1

            # Extract key phrases (simple word frequency)
            for word in inf.get("user_state", "").lower().split():
                if len(word) > 4:  # Skip short words
                    user_state_words[word] = user_state_words.get(word, 0) + 1

            for word in inf.get("driving_assumptions", "").lower().split():
                if len(word) > 4:
                    assumption_words[word] = assumption_words.get(word, 0) + 1

        # Find common patterns
        common_states = [
            {"word": w, "count": c}
            for w, c in sorted(user_state_words.items(), key=lambda x: -x[1])
            if c >= min_count
        ][:10]

        common_assumptions = [
            {"word": w, "count": c}
            for w, c in sorted(assumption_words.items(), key=lambda x: -x[1])
            if c >= min_count
        ][:10]

        frequent_signals = [
            {"signal": s, "count": c}
            for s, c in sorted(signal_counts.items(), key=lambda x: -x[1])
            if c >= min_count
        ]

        return {
            "total_inferences": len(inferences),
            "common_user_states": common_states,
            "common_assumptions": common_assumptions,
            "confidence_distribution": confidence_counts,
            "signal_frequency": frequent_signals
        }

    def analyze_presence_patterns(
        self,
        user_id: Optional[str] = None,
        min_count: int = 2
    ) -> Dict:
        """
        Analyze patterns in presence/distancing behavior.

        Args:
            user_id: Optional filter to specific user
            min_count: Minimum occurrences to count as pattern

        Returns:
            Dict with presence pattern analysis
        """
        logs = self._get_presence_logs(user_id=user_id, limit=100)

        if not logs:
            return {
                "total_logs": 0,
                "presence_distribution": {},
                "common_distance_moves": [],
                "common_defensive_patterns": [],
                "common_adaptations": []
            }

        # Count presence levels
        presence_counts = {"full": 0, "partial": 0, "distanced": 0}
        distance_counts = {}
        defensive_counts = {}
        adaptation_counts = {}

        for log in logs:
            # Count presence level
            level = log.get("presence_level", "unknown")
            if level in presence_counts:
                presence_counts[level] += 1

            # Count distance moves
            for move in log.get("distance_moves", []):
                distance_counts[move] = distance_counts.get(move, 0) + 1

            # Count defensive patterns
            for pattern in log.get("defensive_patterns", []):
                defensive_counts[pattern] = defensive_counts.get(pattern, 0) + 1

            # Count adaptations
            for adapt in log.get("adaptations", []):
                adaptation_counts[adapt] = adaptation_counts.get(adapt, 0) + 1

        # Build pattern lists
        common_distance = [
            {"move": m, "count": c}
            for m, c in sorted(distance_counts.items(), key=lambda x: -x[1])
            if c >= min_count
        ]

        common_defensive = [
            {"pattern": p, "count": c}
            for p, c in sorted(defensive_counts.items(), key=lambda x: -x[1])
            if c >= min_count
        ]

        common_adaptations = [
            {"adaptation": a, "count": c}
            for a, c in sorted(adaptation_counts.items(), key=lambda x: -x[1])
            if c >= min_count
        ]

        # Calculate presence ratio
        total = sum(presence_counts.values())
        presence_ratio = presence_counts["full"] / total if total > 0 else 0

        return {
            "total_logs": len(logs),
            "presence_distribution": presence_counts,
            "presence_ratio": round(presence_ratio, 2),
            "common_distance_moves": common_distance,
            "common_defensive_patterns": common_defensive,
            "common_adaptations": common_adaptations
        }
