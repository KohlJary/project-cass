"""
Daedalus integration for Refactor Scout.

Provides pre-task analysis and advisory output for Claude Code sessions.
"""

import os
from pathlib import Path
from typing import List, Optional, Tuple

from .analyzer import FileAnalyzer
from .thresholds import ThresholdChecker, DEFAULT_THRESHOLDS
from .opportunities import OpportunityIdentifier
from .models import AnalysisResult, ExtractionOpportunity


class ScoutAdvisor:
    """
    Advisory system for Daedalus pre-task analysis.

    Analyzes files before a task begins and provides recommendations
    for cleanup that would make the task easier.
    """

    def __init__(self, thresholds: Optional[dict] = None):
        self.analyzer = FileAnalyzer()
        self.checker = ThresholdChecker(thresholds)
        self.identifier = OpportunityIdentifier()

    def analyze_for_task(
        self,
        target_files: List[str],
        task_description: Optional[str] = None,
    ) -> str:
        """
        Analyze files that will be modified by a task.

        Returns advisory text suitable for including in Claude Code context.
        """
        results = []

        for path in target_files:
            if not os.path.exists(path) or not path.endswith('.py'):
                continue

            try:
                metrics = self.analyzer.analyze(path)
                violations = self.checker.check(metrics)

                if violations:
                    opportunities = self.identifier.identify(metrics)
                    results.append(AnalysisResult(
                        metrics=metrics,
                        violations=violations,
                        opportunities=opportunities,
                    ))
            except Exception:
                continue

        if not results:
            return ""

        return self._format_advisory(results, task_description)

    def should_scout(self, file_path: str) -> Tuple[bool, List[str]]:
        """
        Check if a file should be scouted before modification.

        Returns (should_scout, list_of_reasons)
        """
        if not os.path.exists(file_path) or not file_path.endswith('.py'):
            return False, []

        try:
            metrics = self.analyzer.analyze(file_path)
            violations = self.checker.check(metrics)

            if violations:
                reasons = [
                    f"{v.metric}: {v.actual} (threshold: {v.threshold})"
                    for v in violations
                ]
                return True, reasons

            return False, []
        except Exception:
            return False, []

    def get_quick_summary(self, file_path: str) -> Optional[str]:
        """Get a one-line summary of file health."""
        if not os.path.exists(file_path) or not file_path.endswith('.py'):
            return None

        try:
            metrics = self.analyzer.analyze(file_path)
            violations = self.checker.check(metrics)

            if not violations:
                return f"{file_path}: HEALTHY ({metrics.line_count} lines)"

            critical = sum(1 for v in violations if v.severity == 'critical')
            warnings = sum(1 for v in violations if v.severity == 'warning')

            status = "CRITICAL" if critical else "WARNING"
            return f"{file_path}: {status} ({metrics.line_count} lines, {critical} critical, {warnings} warnings)"
        except Exception:
            return None

    def _format_advisory(
        self,
        results: List[AnalysisResult],
        task_description: Optional[str] = None,
    ) -> str:
        """Format analysis results as advisory text."""
        lines = []

        lines.append("## Scout Advisory")
        lines.append("")

        if task_description:
            lines.append(f"*Analyzing files for task: {task_description}*")
            lines.append("")

        # Summary
        critical_count = sum(1 for r in results if r.has_critical_violations)
        warning_count = sum(1 for r in results if r.has_violations and not r.has_critical_violations)

        if critical_count:
            lines.append(f"**{critical_count} file(s) need attention before this task.**")
        elif warning_count:
            lines.append(f"**{warning_count} file(s) could benefit from cleanup.**")
        lines.append("")

        # Per-file details
        for result in sorted(results, key=lambda r: -r.metrics.line_count):
            m = result.metrics
            status = "CRITICAL" if result.has_critical_violations else "WARNING"

            lines.append(f"### {m.path} [{status}]")
            lines.append(f"- Lines: {m.line_count}")
            lines.append(f"- Functions: {m.function_count}")
            lines.append(f"- Classes: {m.class_count}")
            lines.append(f"- Complexity: {m.complexity_score:.2f}")
            lines.append("")

            # Violations
            if result.violations:
                lines.append("**Issues:**")
                for v in result.violations:
                    icon = "X" if v.severity == 'critical' else "!"
                    lines.append(f"- [{icon}] {v.metric}: {v.actual} (threshold: {v.threshold})")
                lines.append("")

            # Top opportunities
            high_priority = [o for o in result.opportunities if o.priority == 'high'][:3]
            if high_priority:
                lines.append("**Suggested extractions:**")
                for opp in high_priority:
                    lines.append(f"- {opp.description}")
                    if opp.suggested_path and not opp.suggested_path.startswith('<'):
                        lines.append(f"  -> {opp.suggested_path}")
                lines.append("")

        # Footer
        lines.append("---")
        lines.append("*Run `python -m backend.refactor_scout analyze <file>` for detailed analysis*")
        lines.append("*Run `python -m backend.refactor_scout extract-class <file> <class>` to extract*")

        return "\n".join(lines)


def pre_task_hook(
    task_files: List[str],
    task_description: Optional[str] = None,
    thresholds: Optional[dict] = None,
) -> str:
    """
    Pre-task hook for Daedalus integration.

    Call this before starting a task to get Scout advisory.

    Args:
        task_files: List of files the task will modify
        task_description: Optional description of the task
        thresholds: Optional custom thresholds

    Returns:
        Advisory text (empty string if no issues found)
    """
    advisor = ScoutAdvisor(thresholds)
    return advisor.analyze_for_task(task_files, task_description)


def check_file(file_path: str) -> Tuple[bool, str]:
    """
    Quick check if a file needs attention.

    Returns (needs_attention, summary_line)
    """
    advisor = ScoutAdvisor()
    summary = advisor.get_quick_summary(file_path)

    if summary is None:
        return False, ""

    needs_attention = "CRITICAL" in summary or "WARNING" in summary
    return needs_attention, summary
