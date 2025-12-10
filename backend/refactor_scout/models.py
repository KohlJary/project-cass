"""Data models for the Refactor Scout analysis system."""

from dataclasses import dataclass, field, asdict
from typing import List, Optional
import json


@dataclass
class FunctionInfo:
    """Information about a function in a Python file."""
    name: str
    line_start: int
    line_end: int
    line_count: int
    param_count: int
    is_async: bool
    decorators: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ClassInfo:
    """Information about a class in a Python file."""
    name: str
    line_start: int
    line_end: int
    line_count: int
    method_count: int
    base_classes: List[str] = field(default_factory=list)
    methods: List[FunctionInfo] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d['methods'] = [m.to_dict() if hasattr(m, 'to_dict') else m for m in self.methods]
        return d


@dataclass
class FileMetrics:
    """Metrics extracted from analyzing a Python file."""
    path: str
    line_count: int
    function_count: int
    class_count: int
    import_count: int
    avg_function_length: float
    max_function_length: int
    complexity_score: float  # 0.0 - 1.0

    functions: List[FunctionInfo] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'path': self.path,
            'line_count': self.line_count,
            'function_count': self.function_count,
            'class_count': self.class_count,
            'import_count': self.import_count,
            'avg_function_length': self.avg_function_length,
            'max_function_length': self.max_function_length,
            'complexity_score': self.complexity_score,
            'functions': [f.to_dict() for f in self.functions],
            'classes': [c.to_dict() for c in self.classes],
            'imports': self.imports,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class Violation:
    """A threshold violation detected during analysis."""
    metric: str           # "line_count", "function_count", etc.
    actual: float
    threshold: float
    severity: str         # "warning", "critical"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractionOpportunity:
    """A suggested extraction to improve code organization."""
    type: str             # "extract_module", "extract_class", "extract_helpers"
    description: str
    target_items: List[str]  # Function/class names to extract
    suggested_path: str
    estimated_lines: int
    priority: str         # "high", "medium", "low"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnalysisResult:
    """Complete analysis result for a single file."""
    metrics: FileMetrics
    violations: List[Violation] = field(default_factory=list)
    opportunities: List[ExtractionOpportunity] = field(default_factory=list)

    @property
    def has_violations(self) -> bool:
        return len(self.violations) > 0

    @property
    def has_critical_violations(self) -> bool:
        return any(v.severity == 'critical' for v in self.violations)

    @property
    def health_status(self) -> str:
        if self.has_critical_violations:
            return 'critical'
        elif self.has_violations:
            return 'warning'
        return 'healthy'

    def to_dict(self) -> dict:
        return {
            'metrics': self.metrics.to_dict(),
            'violations': [v.to_dict() for v in self.violations],
            'opportunities': [o.to_dict() for o in self.opportunities],
            'health_status': self.health_status,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class ScoutReport:
    """Complete Scout report for multiple files."""
    results: List[AnalysisResult] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.results)

    @property
    def healthy_files(self) -> int:
        return sum(1 for r in self.results if r.health_status == 'healthy')

    @property
    def warning_files(self) -> int:
        return sum(1 for r in self.results if r.health_status == 'warning')

    @property
    def critical_files(self) -> int:
        return sum(1 for r in self.results if r.health_status == 'critical')

    @property
    def total_lines(self) -> int:
        return sum(r.metrics.line_count for r in self.results)

    @property
    def health_score(self) -> int:
        """Overall health score 0-100."""
        if not self.results:
            return 100
        # Weight: healthy=100, warning=50, critical=0
        score_sum = sum(
            100 if r.health_status == 'healthy' else
            50 if r.health_status == 'warning' else 0
            for r in self.results
        )
        return int(score_sum / len(self.results))

    def get_critical_files(self) -> List[AnalysisResult]:
        return [r for r in self.results if r.health_status == 'critical']

    def get_all_opportunities(self) -> List[tuple]:
        """Return all opportunities with their source file."""
        opportunities = []
        for result in self.results:
            for opp in result.opportunities:
                opportunities.append((result.metrics.path, opp))
        return opportunities

    def get_summary_stats(self) -> dict:
        """Get summary statistics compatible with database recording."""
        return {
            'total_files': self.total_files,
            'healthy_files': self.healthy_files,
            'needs_attention': self.warning_files,
            'critical_files': self.critical_files,
            'total_lines': self.total_lines,
            'avg_lines': self.total_lines / self.total_files if self.total_files else 0,
            'health_score': self.health_score,
        }

    def to_dict(self) -> dict:
        return {
            'summary': {
                'total_files': self.total_files,
                'healthy_files': self.healthy_files,
                'warning_files': self.warning_files,
                'critical_files': self.critical_files,
                'total_lines': self.total_lines,
                'health_score': self.health_score,
            },
            'results': [r.to_dict() for r in self.results],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
