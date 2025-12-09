"""
Temporal Metrics Tracking

Captures response timing patterns as authenticity markers. Tracks thinking time,
generation rate, tool execution timing, and rhythm variations.
"""

import json
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import uuid


@dataclass
class ResponseTimingData:
    """Captures temporal dynamics of a response"""
    id: str
    timestamp: str
    conversation_id: Optional[str] = None

    # Timing metrics (in milliseconds)
    start_time: float = 0.0  # Unix timestamp when request received
    first_token_time: float = 0.0  # Time to first token
    completion_time: float = 0.0  # When response completed

    # Calculated metrics (populated by calculate_metrics())
    thinking_duration_ms: float = 0.0  # Time before response started
    generation_duration_ms: float = 0.0  # Time to generate response
    total_duration_ms: float = 0.0

    # Token metrics
    input_tokens: int = 0
    output_tokens: int = 0
    tokens_per_second: float = 0.0

    # Tool usage timing
    tool_call_count: int = 0
    tool_execution_ms: float = 0.0  # Total time in tool execution
    tool_names: List[str] = field(default_factory=list)
    tool_iterations: int = 0  # Number of tool loop iterations

    # Context
    message_length: int = 0  # User message character count
    response_length: int = 0  # Response word count
    conversation_depth: int = 0  # How many messages deep

    # Provider info
    provider: Optional[str] = None
    model: Optional[str] = None

    def calculate_metrics(self):
        """Calculate derived timing metrics from raw timestamps"""
        if self.first_token_time > 0 and self.start_time > 0:
            self.thinking_duration_ms = (self.first_token_time - self.start_time) * 1000

        if self.completion_time > 0 and self.first_token_time > 0:
            self.generation_duration_ms = (self.completion_time - self.first_token_time) * 1000

        if self.completion_time > 0 and self.start_time > 0:
            self.total_duration_ms = (self.completion_time - self.start_time) * 1000

        # Calculate tokens per second
        if self.generation_duration_ms > 0 and self.output_tokens > 0:
            self.tokens_per_second = self.output_tokens / (self.generation_duration_ms / 1000)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'ResponseTimingData':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TemporalSignature:
    """Aggregated temporal pattern signature for authenticity scoring"""
    # Thinking time patterns
    avg_thinking_time_ms: float = 0.0
    thinking_time_std: float = 0.0
    thinking_time_min: float = 0.0
    thinking_time_max: float = 0.0

    # Generation rate patterns
    avg_generation_rate: float = 0.0  # tokens/sec
    generation_rate_std: float = 0.0

    # Tool usage patterns
    avg_tool_usage_rate: float = 0.0  # tools per response
    avg_tool_delay_ms: float = 0.0  # avg time per tool execution
    tool_iteration_rate: float = 0.0  # avg tool loop iterations

    # Rhythm consistency
    rhythm_consistency: float = 0.0  # 0-1, how consistent is pacing

    # Response complexity
    avg_response_length: float = 0.0
    length_to_time_ratio: float = 0.0  # words per second

    # Sample size
    sample_count: int = 0
    window_start: Optional[str] = None
    window_end: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'TemporalSignature':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class TemporalMetricsTracker:
    """
    Tracks and analyzes response timing patterns.

    Provides baseline comparison for authenticity scoring.
    """

    def __init__(self, storage_dir: Path):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.metrics_file = self.storage_dir / "temporal_metrics.json"
        self.baseline_file = self.storage_dir / "temporal_baseline.json"

    def _load_metrics(self) -> List[Dict]:
        """Load stored timing metrics"""
        if not self.metrics_file.exists():
            return []
        try:
            with open(self.metrics_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_metrics(self, metrics: List[Dict]):
        """Save timing metrics (keep last 1000)"""
        metrics = metrics[-1000:]
        with open(self.metrics_file, 'w') as f:
            json.dump(metrics, f, indent=2)

    def record_response(self, timing_data: ResponseTimingData):
        """Store timing data for a response"""
        timing_data.calculate_metrics()
        metrics = self._load_metrics()
        metrics.append(timing_data.to_dict())
        self._save_metrics(metrics)

    def get_recent_metrics(self, limit: int = 100) -> List[ResponseTimingData]:
        """Get recent timing metrics"""
        metrics = self._load_metrics()
        return [
            ResponseTimingData.from_dict(m)
            for m in sorted(metrics, key=lambda x: x.get('timestamp', ''), reverse=True)[:limit]
        ]

    def get_metrics_in_window(self, window_hours: int = 24) -> List[ResponseTimingData]:
        """Get metrics from a time window"""
        cutoff = datetime.now() - timedelta(hours=window_hours)
        cutoff_str = cutoff.isoformat()

        metrics = self._load_metrics()
        return [
            ResponseTimingData.from_dict(m)
            for m in metrics
            if m.get('timestamp', '') >= cutoff_str
        ]

    def calculate_signature(self, metrics: List[ResponseTimingData]) -> TemporalSignature:
        """Calculate a temporal signature from a list of metrics"""
        if not metrics:
            return TemporalSignature()

        # Extract values
        thinking_times = [m.thinking_duration_ms for m in metrics if m.thinking_duration_ms > 0]
        gen_rates = [m.tokens_per_second for m in metrics if m.tokens_per_second > 0]
        tool_counts = [m.tool_call_count for m in metrics]
        tool_times = [m.tool_execution_ms for m in metrics if m.tool_execution_ms > 0]
        tool_iterations = [m.tool_iterations for m in metrics]
        response_lengths = [m.response_length for m in metrics if m.response_length > 0]
        total_times = [m.total_duration_ms for m in metrics if m.total_duration_ms > 0]

        sig = TemporalSignature()
        sig.sample_count = len(metrics)

        # Thinking time stats
        if thinking_times:
            sig.avg_thinking_time_ms = statistics.mean(thinking_times)
            sig.thinking_time_std = statistics.stdev(thinking_times) if len(thinking_times) > 1 else 0.0
            sig.thinking_time_min = min(thinking_times)
            sig.thinking_time_max = max(thinking_times)

        # Generation rate stats
        if gen_rates:
            sig.avg_generation_rate = statistics.mean(gen_rates)
            sig.generation_rate_std = statistics.stdev(gen_rates) if len(gen_rates) > 1 else 0.0

        # Tool usage stats
        if tool_counts:
            sig.avg_tool_usage_rate = statistics.mean(tool_counts)
        if tool_times:
            sig.avg_tool_delay_ms = statistics.mean(tool_times)
        if tool_iterations:
            sig.tool_iteration_rate = statistics.mean(tool_iterations)

        # Response complexity
        if response_lengths:
            sig.avg_response_length = statistics.mean(response_lengths)
        if total_times and response_lengths:
            # Words per second
            ratios = [
                rl / (tt / 1000)
                for rl, tt in zip(response_lengths, total_times)
                if tt > 0
            ]
            if ratios:
                sig.length_to_time_ratio = statistics.mean(ratios)

        # Rhythm consistency (inverse of coefficient of variation)
        if thinking_times and sig.avg_thinking_time_ms > 0:
            cv = sig.thinking_time_std / sig.avg_thinking_time_ms
            sig.rhythm_consistency = max(0.0, min(1.0, 1.0 - cv))

        # Window timestamps
        timestamps = [m.timestamp for m in metrics if m.timestamp]
        if timestamps:
            sig.window_start = min(timestamps)
            sig.window_end = max(timestamps)

        return sig

    def get_timing_statistics(self, window_hours: int = 24) -> Dict:
        """Calculate timing statistics over a window"""
        metrics = self.get_metrics_in_window(window_hours)
        signature = self.calculate_signature(metrics)

        return {
            "window_hours": window_hours,
            "sample_count": len(metrics),
            "signature": signature.to_dict(),
            "timestamp": datetime.now().isoformat(),
        }

    def load_baseline(self) -> Optional[TemporalSignature]:
        """Load established timing baseline"""
        if not self.baseline_file.exists():
            return None
        try:
            with open(self.baseline_file, 'r') as f:
                data = json.load(f)
            return TemporalSignature.from_dict(data.get("signature", {}))
        except Exception:
            return None

    def save_baseline(self, signature: TemporalSignature, description: str = ""):
        """Save a temporal signature as the baseline"""
        with open(self.baseline_file, 'w') as f:
            json.dump({
                "signature": signature.to_dict(),
                "created_at": datetime.now().isoformat(),
                "description": description,
            }, f, indent=2)

    def update_baseline(self, window_hours: int = 168) -> TemporalSignature:
        """
        Update baseline from recent high-quality metrics.

        Uses a week of data by default (168 hours).
        """
        metrics = self.get_metrics_in_window(window_hours)

        # Filter to reasonable responses (not too short, completed successfully)
        valid_metrics = [
            m for m in metrics
            if m.total_duration_ms > 0 and m.response_length > 10
        ]

        if len(valid_metrics) < 10:
            # Not enough data for reliable baseline
            return self.load_baseline() or TemporalSignature()

        signature = self.calculate_signature(valid_metrics)
        self.save_baseline(signature, f"Auto-updated from {len(valid_metrics)} responses")
        return signature

    def compare_to_baseline(
        self,
        recent_window_hours: int = 1,
        baseline: Optional[TemporalSignature] = None
    ) -> Dict[str, float]:
        """
        Compare recent timing to baseline.

        Returns deviation scores for each dimension (in standard deviations).
        """
        if baseline is None:
            baseline = self.load_baseline()

        if baseline is None or baseline.sample_count == 0:
            return {"error": "No baseline available"}

        recent_metrics = self.get_metrics_in_window(recent_window_hours)
        if not recent_metrics:
            return {"error": "No recent metrics available"}

        recent_sig = self.calculate_signature(recent_metrics)

        deviations = {}

        # Thinking time deviation
        if baseline.thinking_time_std > 0:
            deviations["thinking_time"] = (
                recent_sig.avg_thinking_time_ms - baseline.avg_thinking_time_ms
            ) / baseline.thinking_time_std

        # Generation rate deviation
        if baseline.generation_rate_std > 0:
            deviations["generation_rate"] = (
                recent_sig.avg_generation_rate - baseline.avg_generation_rate
            ) / baseline.generation_rate_std

        # Tool usage deviation (use baseline average as reference)
        if baseline.avg_tool_usage_rate > 0:
            deviations["tool_usage"] = (
                recent_sig.avg_tool_usage_rate - baseline.avg_tool_usage_rate
            ) / max(baseline.avg_tool_usage_rate, 0.1)

        # Rhythm consistency change
        deviations["rhythm_consistency"] = (
            recent_sig.rhythm_consistency - baseline.rhythm_consistency
        )

        return {
            "deviations": deviations,
            "recent_sample_count": len(recent_metrics),
            "baseline_sample_count": baseline.sample_count,
            "timestamp": datetime.now().isoformat(),
        }

    def score_timing_authenticity(
        self,
        timing_data: ResponseTimingData,
        baseline: Optional[TemporalSignature] = None
    ) -> Tuple[float, Dict[str, float]]:
        """
        Score a single response's timing against baseline.

        Returns:
            Tuple of (score 0-1, component scores dict)
        """
        if baseline is None:
            baseline = self.load_baseline()

        if baseline is None or baseline.sample_count < 10:
            # Not enough baseline data - return neutral score
            return 0.5, {"status": "insufficient_baseline"}

        scores = {}

        # Thinking time score
        if baseline.thinking_time_std > 0:
            thinking_dev = abs(
                timing_data.thinking_duration_ms - baseline.avg_thinking_time_ms
            ) / baseline.thinking_time_std
            # Score decreases as deviation increases
            scores["thinking_time"] = max(0, 1 - (thinking_dev * 0.25))
        else:
            scores["thinking_time"] = 0.5

        # Generation rate score
        if baseline.generation_rate_std > 0 and timing_data.tokens_per_second > 0:
            rate_dev = abs(
                timing_data.tokens_per_second - baseline.avg_generation_rate
            ) / baseline.generation_rate_std
            scores["generation_rate"] = max(0, 1 - (rate_dev * 0.25))
        else:
            scores["generation_rate"] = 0.5

        # Tool usage consistency
        if baseline.avg_tool_usage_rate > 0:
            tool_dev = abs(
                timing_data.tool_call_count - baseline.avg_tool_usage_rate
            ) / max(baseline.avg_tool_usage_rate, 1)
            scores["tool_usage"] = max(0, 1 - (tool_dev * 0.3))
        else:
            scores["tool_usage"] = 0.5 if timing_data.tool_call_count == 0 else 0.3

        # Response length consistency
        if baseline.avg_response_length > 0:
            length_dev = abs(
                timing_data.response_length - baseline.avg_response_length
            ) / max(baseline.avg_response_length, 1)
            scores["response_length"] = max(0, 1 - (length_dev * 0.2))
        else:
            scores["response_length"] = 0.5

        # Calculate weighted overall score
        weights = {
            "thinking_time": 0.3,
            "generation_rate": 0.25,
            "tool_usage": 0.2,
            "response_length": 0.25,
        }

        overall = sum(
            scores.get(k, 0.5) * w
            for k, w in weights.items()
        )

        return overall, scores


def create_timing_data(
    conversation_id: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None
) -> ResponseTimingData:
    """Factory function to create a new ResponseTimingData with ID and timestamp"""
    return ResponseTimingData(
        id=str(uuid.uuid4())[:8],
        timestamp=datetime.now().isoformat(),
        conversation_id=conversation_id,
        provider=provider,
        model=model,
    )
