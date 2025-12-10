"""
Refactor Scout - Code health analysis and decomposition advisor.

A pre-build analysis tool that identifies files needing refactoring and suggests
extraction opportunities to improve code organization.

Usage:
    from backend.refactor_scout import run_scout, analyze_file

    # Analyze a single file
    result = analyze_file("backend/main_sdk.py")
    print(result.health_status)  # "healthy", "warning", or "critical"

    # Scan a directory
    report = run_scout(["backend/"])
    print(f"Health score: {report.health_score}/100")
"""

from .models import (
    FileMetrics,
    FunctionInfo,
    ClassInfo,
    Violation,
    ExtractionOpportunity,
    AnalysisResult,
    ScoutReport,
)
from .analyzer import FileAnalyzer
from .thresholds import ThresholdChecker, DEFAULT_THRESHOLDS
from .opportunities import OpportunityIdentifier
from .reporter import Reporter
from .cli import analyze_file, scan_directory
from .extractor import CodeExtractor, GitIntegration, ExtractionResult
from .database import ScoutDatabase, FileRecord, ExtractionRecord, ScoutSnapshot
from .config import ScoutConfig, ThresholdConfig, load_config, save_config


def run_scout(
    paths: list[str],
    thresholds: dict | None = None
) -> ScoutReport:
    """
    Run Scout analysis on one or more paths.

    Args:
        paths: List of file or directory paths to analyze
        thresholds: Optional threshold overrides

    Returns:
        ScoutReport with analysis results for all files
    """
    import os

    report = ScoutReport()

    for path in paths:
        if os.path.isfile(path) and path.endswith('.py'):
            result = analyze_file(path, thresholds)
            report.results.append(result)
        elif os.path.isdir(path):
            dir_report = scan_directory(path, thresholds)
            report.results.extend(dir_report.results)

    return report


__all__ = [
    # Models
    'FileMetrics',
    'FunctionInfo',
    'ClassInfo',
    'Violation',
    'ExtractionOpportunity',
    'AnalysisResult',
    'ScoutReport',
    'ExtractionResult',
    'FileRecord',
    'ExtractionRecord',
    'ScoutSnapshot',
    # Core classes
    'FileAnalyzer',
    'ThresholdChecker',
    'OpportunityIdentifier',
    'Reporter',
    'CodeExtractor',
    'GitIntegration',
    'ScoutDatabase',
    'ScoutConfig',
    'ThresholdConfig',
    # Constants
    'DEFAULT_THRESHOLDS',
    # Functions
    'analyze_file',
    'scan_directory',
    'run_scout',
    'load_config',
    'save_config',
]
