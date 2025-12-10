"""Threshold configuration and checking for Refactor Scout."""

from typing import List, Dict, Any, Optional
from .models import FileMetrics, Violation


# Default thresholds based on spec
DEFAULT_THRESHOLDS = {
    "max_lines": 400,
    "max_imports": 15,
    "max_functions": 20,
    "max_function_length": 50,
    "max_classes_per_file": 2,
    "max_class_lines": 200,
    "complexity_warning": 0.6,
    "complexity_critical": 0.8,
}

# How much over threshold triggers critical vs warning
# e.g., 2x the threshold = critical
CRITICAL_MULTIPLIER = 2.0


class ThresholdChecker:
    """Checks file metrics against configurable thresholds."""

    def __init__(self, thresholds: Optional[Dict[str, Any]] = None):
        self.thresholds = {**DEFAULT_THRESHOLDS}
        if thresholds:
            self.thresholds.update(thresholds)

    def check(self, metrics: FileMetrics) -> List[Violation]:
        """Check metrics against thresholds and return violations."""
        violations = []

        # Line count
        if metrics.line_count > self.thresholds["max_lines"]:
            violations.append(Violation(
                metric="line_count",
                actual=metrics.line_count,
                threshold=self.thresholds["max_lines"],
                severity=self._get_severity(
                    metrics.line_count,
                    self.thresholds["max_lines"]
                ),
            ))

        # Import count
        if metrics.import_count > self.thresholds["max_imports"]:
            violations.append(Violation(
                metric="import_count",
                actual=metrics.import_count,
                threshold=self.thresholds["max_imports"],
                severity=self._get_severity(
                    metrics.import_count,
                    self.thresholds["max_imports"]
                ),
            ))

        # Function count
        if metrics.function_count > self.thresholds["max_functions"]:
            violations.append(Violation(
                metric="function_count",
                actual=metrics.function_count,
                threshold=self.thresholds["max_functions"],
                severity=self._get_severity(
                    metrics.function_count,
                    self.thresholds["max_functions"]
                ),
            ))

        # Max function length
        if metrics.max_function_length > self.thresholds["max_function_length"]:
            violations.append(Violation(
                metric="max_function_length",
                actual=metrics.max_function_length,
                threshold=self.thresholds["max_function_length"],
                severity=self._get_severity(
                    metrics.max_function_length,
                    self.thresholds["max_function_length"]
                ),
            ))

        # Class count
        if metrics.class_count > self.thresholds["max_classes_per_file"]:
            violations.append(Violation(
                metric="class_count",
                actual=metrics.class_count,
                threshold=self.thresholds["max_classes_per_file"],
                severity=self._get_severity(
                    metrics.class_count,
                    self.thresholds["max_classes_per_file"]
                ),
            ))

        # Check individual class sizes
        for cls in metrics.classes:
            if cls.line_count > self.thresholds["max_class_lines"]:
                violations.append(Violation(
                    metric=f"class_lines:{cls.name}",
                    actual=cls.line_count,
                    threshold=self.thresholds["max_class_lines"],
                    severity=self._get_severity(
                        cls.line_count,
                        self.thresholds["max_class_lines"]
                    ),
                ))

        # Complexity score
        if metrics.complexity_score > self.thresholds["complexity_critical"]:
            violations.append(Violation(
                metric="complexity_score",
                actual=metrics.complexity_score,
                threshold=self.thresholds["complexity_critical"],
                severity="critical",
            ))
        elif metrics.complexity_score > self.thresholds["complexity_warning"]:
            violations.append(Violation(
                metric="complexity_score",
                actual=metrics.complexity_score,
                threshold=self.thresholds["complexity_warning"],
                severity="warning",
            ))

        return violations

    def _get_severity(self, actual: float, threshold: float) -> str:
        """Determine severity based on how much the threshold is exceeded."""
        if actual >= threshold * CRITICAL_MULTIPLIER:
            return "critical"
        return "warning"

    def should_scout(self, metrics: FileMetrics) -> bool:
        """Check if this file should be scouted (has any violations)."""
        return len(self.check(metrics)) > 0
