"""Report generation for Refactor Scout analysis results."""

from typing import List, Optional
from .models import AnalysisResult, ScoutReport, Violation, ExtractionOpportunity


class Reporter:
    """Generates text and JSON reports from Scout analysis."""

    def generate_file_report(self, result: AnalysisResult) -> str:
        """Generate a text report for a single file analysis."""
        lines = []
        metrics = result.metrics

        # Header
        lines.append(f"File: {metrics.path}")
        lines.append("=" * 60)
        lines.append("")

        # Metrics section
        lines.append("Metrics:")
        lines.append(self._format_metric(
            "Lines", metrics.line_count, 400,
            self._find_violation(result.violations, "line_count")
        ))
        lines.append(self._format_metric(
            "Functions", metrics.function_count, 20,
            self._find_violation(result.violations, "function_count")
        ))
        lines.append(self._format_metric(
            "Classes", metrics.class_count, 2,
            self._find_violation(result.violations, "class_count")
        ))
        lines.append(self._format_metric(
            "Imports", metrics.import_count, 15,
            self._find_violation(result.violations, "import_count")
        ))
        lines.append(self._format_metric(
            "Max Func Length", metrics.max_function_length, 50,
            self._find_violation(result.violations, "max_function_length")
        ))
        lines.append(self._format_metric(
            "Complexity", f"{metrics.complexity_score:.2f}", "0.70",
            self._find_violation(result.violations, "complexity_score")
        ))
        lines.append("")

        # Violations summary
        if result.violations:
            critical = [v for v in result.violations if v.severity == 'critical']
            warnings = [v for v in result.violations if v.severity == 'warning']

            lines.append(f"Status: {'CRITICAL' if critical else 'WARNING'}")
            if critical:
                lines.append(f"  Critical violations: {len(critical)}")
            if warnings:
                lines.append(f"  Warnings: {len(warnings)}")
            lines.append("")
        else:
            lines.append("Status: HEALTHY")
            lines.append("")

        # Extraction opportunities
        if result.opportunities:
            lines.append("Extraction Opportunities:")
            for i, opp in enumerate(result.opportunities, 1):
                priority_icon = {
                    'high': '[HIGH]',
                    'medium': '[MED]',
                    'low': '[LOW]'
                }.get(opp.priority, '[???]')

                lines.append(f"  {i}. {priority_icon} {opp.description}")
                if opp.suggested_path and not opp.suggested_path.startswith('<'):
                    lines.append(f"      -> {opp.suggested_path}")
                if opp.estimated_lines > 0:
                    lines.append(f"      (~{opp.estimated_lines} lines)")
            lines.append("")

        # Top functions by size
        if metrics.functions:
            sorted_funcs = sorted(
                metrics.functions, key=lambda f: f.line_count, reverse=True
            )[:5]
            lines.append("Largest Functions:")
            for func in sorted_funcs:
                async_tag = " (async)" if func.is_async else ""
                lines.append(f"  - {func.name}{async_tag}: {func.line_count} lines")
            lines.append("")

        # Top classes by size
        if metrics.classes:
            sorted_classes = sorted(
                metrics.classes, key=lambda c: c.line_count, reverse=True
            )[:3]
            lines.append("Largest Classes:")
            for cls in sorted_classes:
                lines.append(
                    f"  - {cls.name}: {cls.line_count} lines, "
                    f"{cls.method_count} methods"
                )
            lines.append("")

        return "\n".join(lines)

    def generate_health_report(self, report: ScoutReport) -> str:
        """Generate a codebase-wide health report."""
        lines = []

        # Header
        lines.append("Codebase Health Report")
        lines.append("=" * 60)
        lines.append("")

        # Overall score
        score = report.health_score
        score_bar = self._score_bar(score)
        lines.append(f"Overall Score: {score}/100 {score_bar}")
        lines.append("")

        # Summary stats
        lines.append("Summary:")
        lines.append(f"  Total Files Analyzed: {report.total_files}")
        lines.append(f"  Total Lines: {report.total_lines:,}")
        lines.append(f"  Healthy Files: {report.healthy_files}")
        lines.append(f"  Needs Attention: {report.warning_files}")
        lines.append(f"  Critical: {report.critical_files}")
        lines.append("")

        # Critical files
        critical = report.get_critical_files()
        if critical:
            lines.append("Critical Files (require immediate attention):")
            for result in sorted(
                critical, key=lambda r: r.metrics.line_count, reverse=True
            ):
                m = result.metrics
                violations = ", ".join(
                    v.metric for v in result.violations if v.severity == 'critical'
                )
                lines.append(f"  - {m.path}")
                lines.append(f"    {m.line_count} lines, {m.function_count} functions")
                lines.append(f"    Issues: {violations}")
            lines.append("")

        # Top opportunities
        all_opps = report.get_all_opportunities()
        high_priority = [
            (path, opp) for path, opp in all_opps if opp.priority == 'high'
        ]

        if high_priority:
            lines.append("Recommended Extractions (High Priority):")
            for i, (path, opp) in enumerate(high_priority[:10], 1):
                lines.append(f"  {i}. {opp.description}")
                lines.append(f"     Source: {path}")
                if opp.estimated_lines > 0:
                    lines.append(f"     Impact: ~{opp.estimated_lines} lines")
            lines.append("")

        # Files by size
        by_size = sorted(
            report.results, key=lambda r: r.metrics.line_count, reverse=True
        )[:10]

        lines.append("Largest Files:")
        for result in by_size:
            m = result.metrics
            status = result.health_status.upper()
            lines.append(f"  {m.line_count:>6} lines  [{status:<8}]  {m.path}")
        lines.append("")

        return "\n".join(lines)

    def _format_metric(
        self,
        name: str,
        value,
        threshold,
        violation: Optional[Violation]
    ) -> str:
        """Format a single metric line."""
        value_str = str(value).rjust(6)
        threshold_str = f"(threshold: {threshold})"

        if violation:
            icon = "X" if violation.severity == 'critical' else "!"
            severity = violation.severity.upper()
            return f"  {name}: {value_str} {threshold_str} {icon} {severity}"
        else:
            return f"  {name}: {value_str} {threshold_str} OK"

    def _find_violation(
        self, violations: List[Violation], metric: str
    ) -> Optional[Violation]:
        """Find a violation by metric name."""
        for v in violations:
            if v.metric == metric or v.metric.startswith(f"{metric}:"):
                return v
        return None

    def _score_bar(self, score: int, width: int = 20) -> str:
        """Generate a visual score bar."""
        filled = int(score / 100 * width)
        empty = width - filled

        if score >= 80:
            char = "="
        elif score >= 50:
            char = "-"
        else:
            char = "."

        return f"[{char * filled}{' ' * empty}]"
