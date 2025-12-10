"""Command-line interface for Refactor Scout."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from .analyzer import FileAnalyzer
from .thresholds import ThresholdChecker, DEFAULT_THRESHOLDS
from .opportunities import OpportunityIdentifier
from .reporter import Reporter
from .models import AnalysisResult, ScoutReport
from .extractor import CodeExtractor, GitIntegration
from .database import ScoutDatabase
from .config import load_config, save_config, generate_default_config, ScoutConfig


def analyze_file(
    path: str,
    thresholds: Optional[dict] = None,
    db: Optional[ScoutDatabase] = None,
) -> AnalysisResult:
    """Analyze a single Python file."""
    analyzer = FileAnalyzer()
    checker = ThresholdChecker(thresholds)
    identifier = OpportunityIdentifier()

    metrics = analyzer.analyze(path)
    violations = checker.check(metrics)
    opportunities = identifier.identify(metrics)

    # Record in database if provided
    if db:
        db.record_scout(path, metrics)

    return AnalysisResult(
        metrics=metrics,
        violations=violations,
        opportunities=opportunities,
    )


def scan_directory(
    directory: str,
    thresholds: Optional[dict] = None,
    exclude_patterns: Optional[List[str]] = None,
    db: Optional[ScoutDatabase] = None,
    config: Optional[ScoutConfig] = None,
) -> ScoutReport:
    """Scan all Python files in a directory."""
    exclude = exclude_patterns or ['__pycache__', '.venv', 'venv', '.git']

    report = ScoutReport()

    for root, dirs, files in os.walk(directory):
        # Filter out excluded directories
        dirs[:] = [d for d in dirs if d not in exclude]

        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)

                # Check if path should be skipped via config
                if config and config.should_skip_path(path):
                    continue

                try:
                    result = analyze_file(path, thresholds, db)
                    report.results.append(result)
                except Exception as e:
                    print(f"Warning: Could not analyze {path}: {e}", file=sys.stderr)

    # Record snapshot if database provided
    if db:
        stats = report.get_summary_stats()
        db.record_snapshot(
            total_files=stats["total_files"],
            healthy_files=stats["healthy_files"],
            needs_attention=stats["needs_attention"],
            critical_files=stats["critical_files"],
            overall_score=stats["health_score"],
            total_lines=stats["total_lines"],
            avg_file_size=stats["avg_lines"],
        )

    return report


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Refactor Scout - Code health analysis tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze a single file
  python -m backend.refactor_scout analyze backend/main_sdk.py

  # Scan entire directory
  python -m backend.refactor_scout scan backend/

  # Generate health report
  python -m backend.refactor_scout report backend/

  # Use custom thresholds
  python -m backend.refactor_scout analyze backend/main_sdk.py --max-lines 500

  # Output as JSON
  python -m backend.refactor_scout analyze backend/main_sdk.py --json

  # Extract a class to its own file
  python -m backend.refactor_scout extract-class backend/main_sdk.py ConnectionManager

  # Extract functions to a new module
  python -m backend.refactor_scout extract-functions backend/main_sdk.py get_user,get_project -o backend/getters.py

  # View file history
  python -m backend.refactor_scout history backend/main_sdk.py

  # View dashboard
  python -m backend.refactor_scout dashboard

  # Initialize/show config
  python -m backend.refactor_scout config --init
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Analyze command
    analyze_parser = subparsers.add_parser(
        'analyze', help='Analyze a single Python file'
    )
    analyze_parser.add_argument('path', help='Path to Python file')
    analyze_parser.add_argument(
        '--json', action='store_true', help='Output as JSON'
    )
    _add_threshold_args(analyze_parser)

    # Scan command
    scan_parser = subparsers.add_parser(
        'scan', help='Scan all Python files in a directory'
    )
    scan_parser.add_argument('directory', help='Directory to scan')
    scan_parser.add_argument(
        '--json', action='store_true', help='Output as JSON'
    )
    scan_parser.add_argument(
        '--only-violations', action='store_true',
        help='Only show files with violations'
    )
    _add_threshold_args(scan_parser)

    # Report command
    report_parser = subparsers.add_parser(
        'report', help='Generate a codebase health report'
    )
    report_parser.add_argument('directory', help='Directory to analyze')
    report_parser.add_argument(
        '--output', '-o', help='Output file (default: stdout)'
    )
    report_parser.add_argument(
        '--json', action='store_true', help='Output as JSON'
    )
    _add_threshold_args(report_parser)

    # Extract class command
    extract_class_parser = subparsers.add_parser(
        'extract-class', help='Extract a class to its own file'
    )
    extract_class_parser.add_argument('source', help='Source file path')
    extract_class_parser.add_argument('class_name', help='Name of class to extract')
    extract_class_parser.add_argument(
        '-o', '--output', help='Target file path (auto-generated if not provided)'
    )
    extract_class_parser.add_argument(
        '--branch', action='store_true',
        help='Create a refactor branch before extraction'
    )
    extract_class_parser.add_argument(
        '--commit', action='store_true',
        help='Commit the extraction (requires --branch or existing refactor branch)'
    )
    extract_class_parser.add_argument(
        '--json', action='store_true', help='Output result as JSON'
    )

    # Extract functions command
    extract_funcs_parser = subparsers.add_parser(
        'extract-functions', help='Extract functions to a new module'
    )
    extract_funcs_parser.add_argument('source', help='Source file path')
    extract_funcs_parser.add_argument(
        'functions', help='Comma-separated list of function names'
    )
    extract_funcs_parser.add_argument(
        '-o', '--output', required=True, help='Target file path'
    )
    extract_funcs_parser.add_argument(
        '--branch', action='store_true',
        help='Create a refactor branch before extraction'
    )
    extract_funcs_parser.add_argument(
        '--commit', action='store_true',
        help='Commit the extraction'
    )
    extract_funcs_parser.add_argument(
        '--json', action='store_true', help='Output result as JSON'
    )

    # History command
    history_parser = subparsers.add_parser(
        'history', help='View Scout history for a file'
    )
    history_parser.add_argument('path', help='Path to Python file')

    # Dashboard command
    dashboard_parser = subparsers.add_parser(
        'dashboard', help='View Scout dashboard with health trends'
    )

    # Config command
    config_parser = subparsers.add_parser(
        'config', help='Manage Scout configuration'
    )
    config_parser.add_argument(
        '--init', action='store_true',
        help='Initialize scout.yaml with default configuration'
    )
    config_parser.add_argument(
        '--show', action='store_true',
        help='Show current configuration'
    )

    # Global arguments
    parser.add_argument(
        '--config', '-c', default=None,
        help='Path to Scout configuration file'
    )
    parser.add_argument(
        '--no-db', action='store_true',
        help='Disable database recording'
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load configuration
    config = load_config(getattr(args, 'config', None))

    # Initialize database (unless disabled)
    db = None
    if not getattr(args, 'no_db', False):
        db = ScoutDatabase()

    # Build thresholds from args (CLI overrides config)
    thresholds = _build_thresholds(args)
    if not thresholds:
        thresholds = config.thresholds.to_dict()

    reporter = Reporter()

    # Handle config command first (doesn't need thresholds)
    if args.command == 'config':
        _handle_config(args)
        return

    if args.command == 'history':
        _handle_history(args, db)
        return

    if args.command == 'dashboard':
        _handle_dashboard(db)
        return

    if args.command == 'analyze':
        if not os.path.exists(args.path):
            print(f"Error: File not found: {args.path}", file=sys.stderr)
            sys.exit(1)

        result = analyze_file(args.path, thresholds, db)

        if args.json:
            print(result.to_json())
        else:
            print(reporter.generate_file_report(result))

    elif args.command == 'scan':
        if not os.path.isdir(args.directory):
            print(f"Error: Directory not found: {args.directory}", file=sys.stderr)
            sys.exit(1)

        report = scan_directory(args.directory, thresholds, db=db, config=config)

        if args.json:
            print(report.to_json())
        else:
            # Print individual file reports
            results = report.results
            if args.only_violations:
                results = [r for r in results if r.has_violations]

            for result in sorted(
                results, key=lambda r: r.metrics.line_count, reverse=True
            ):
                print(reporter.generate_file_report(result))
                print("-" * 60)
                print()

    elif args.command == 'report':
        if not os.path.isdir(args.directory):
            print(f"Error: Directory not found: {args.directory}", file=sys.stderr)
            sys.exit(1)

        report = scan_directory(args.directory, thresholds, db=db, config=config)

        if args.json:
            output = report.to_json()
        else:
            output = reporter.generate_health_report(report)

        if args.output:
            with open(args.output, 'w') as f:
                f.write(output)
            print(f"Report written to: {args.output}")
        else:
            print(output)

    elif args.command == 'extract-class':
        _handle_extract_class(args, db)

    elif args.command == 'extract-functions':
        _handle_extract_functions(args, db)


def _handle_extract_class(args, db: Optional[ScoutDatabase] = None):
    """Handle extract-class command."""
    git = GitIntegration()
    extractor = CodeExtractor()

    # Check for uncommitted changes if we're going to branch
    if args.branch and git.has_uncommitted_changes():
        print("Error: Cannot create branch with uncommitted changes", file=sys.stderr)
        sys.exit(1)

    # Create branch if requested
    original_branch = None
    if args.branch:
        original_branch = git.get_current_branch()
        branch_name = git.create_refactor_branch(f"extract-{args.class_name}")
        if not branch_name:
            print("Error: Failed to create refactor branch", file=sys.stderr)
            sys.exit(1)
        print(f"Created branch: {branch_name}")

    # Perform extraction
    result = extractor.extract_class(
        args.source,
        args.class_name,
        args.output,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        if result.success:
            print(f"Successfully extracted '{args.class_name}'")
            print(f"  Source: {result.source_file}")
            print(f"  Target: {result.target_file}")
            print(f"  Lines moved: {result.lines_moved}")
            print(f"  Backup: {result.backup_path}")

            # Show dependency warnings
            if result.dependency_warnings:
                print()
                print(f"  ⚠️  DEPENDENCY WARNINGS ({len(result.dependency_warnings)}):")
                print("  The extracted code uses names that may not be available:")
                for warn in result.dependency_warnings:
                    print(f"    - {warn.name} (type: {warn.likely_type})")
                    print(f"      Context: {warn.usage_context}")
                print()
                print("  Consider adding imports or passing these as function parameters.")
        else:
            print(f"Extraction failed: {result.error}", file=sys.stderr)

    if not result.success:
        # Rollback branch if we created one
        if args.branch and original_branch:
            git.switch_branch(original_branch)
        sys.exit(1)

    # Record extraction in database
    if db and result.success:
        db.record_extraction(
            source_path=result.source_file,
            extraction_type="extract_class",
            target_path=result.target_file or "",
            lines_moved=result.lines_moved,
            items_extracted=result.items_extracted,
            commit_hash=None,  # Will be set after commit
        )

    # Commit if requested
    if args.commit:
        if git.commit_extraction(result):
            print("Committed extraction")
        else:
            print("Warning: Failed to commit extraction", file=sys.stderr)


def _handle_extract_functions(args, db: Optional[ScoutDatabase] = None):
    """Handle extract-functions command."""
    git = GitIntegration()
    extractor = CodeExtractor()

    function_names = [f.strip() for f in args.functions.split(',')]

    # Check for uncommitted changes if we're going to branch
    if args.branch and git.has_uncommitted_changes():
        print("Error: Cannot create branch with uncommitted changes", file=sys.stderr)
        sys.exit(1)

    # Create branch if requested
    original_branch = None
    if args.branch:
        original_branch = git.get_current_branch()
        branch_name = git.create_refactor_branch(f"extract-functions")
        if not branch_name:
            print("Error: Failed to create refactor branch", file=sys.stderr)
            sys.exit(1)
        print(f"Created branch: {branch_name}")

    # Perform extraction
    result = extractor.extract_functions(
        args.source,
        function_names,
        args.output,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        if result.success:
            print(f"Successfully extracted {len(function_names)} functions")
            print(f"  Source: {result.source_file}")
            print(f"  Target: {result.target_file}")
            print(f"  Functions: {', '.join(result.items_extracted)}")
            print(f"  Lines moved: {result.lines_moved}")
            print(f"  Backup: {result.backup_path}")

            # Show dependency warnings
            if result.dependency_warnings:
                print()
                print(f"  ⚠️  DEPENDENCY WARNINGS ({len(result.dependency_warnings)}):")
                print("  The extracted code uses names that may not be available:")
                for warn in result.dependency_warnings:
                    print(f"    - {warn.name} (type: {warn.likely_type})")
                    print(f"      Context: {warn.usage_context}")
                print()
                print("  Consider adding imports or passing these as function parameters.")
        else:
            print(f"Extraction failed: {result.error}", file=sys.stderr)

    if not result.success:
        # Rollback branch if we created one
        if args.branch and original_branch:
            git.switch_branch(original_branch)
        sys.exit(1)

    # Record extraction in database
    if db and result.success:
        db.record_extraction(
            source_path=result.source_file,
            extraction_type="extract_functions",
            target_path=result.target_file or "",
            lines_moved=result.lines_moved,
            items_extracted=result.items_extracted,
            commit_hash=None,
        )

    # Commit if requested
    if args.commit:
        if git.commit_extraction(result):
            print("Committed extraction")
        else:
            print("Warning: Failed to commit extraction", file=sys.stderr)


def _handle_config(args):
    """Handle config command."""
    if args.init:
        config_path = "scout.yaml"
        if os.path.exists(config_path):
            print(f"Config file already exists: {config_path}")
            print("Use --show to view current configuration")
            return

        config_content = generate_default_config()
        with open(config_path, "w") as f:
            f.write(config_content)
        print(f"Created default configuration: {config_path}")
        return

    # Default: show current config
    config = load_config()
    print("Current Scout Configuration")
    print("=" * 60)
    print()
    print("Thresholds:")
    thresholds = config.thresholds
    print(f"  max_lines: {thresholds.max_lines}")
    print(f"  max_imports: {thresholds.max_imports}")
    print(f"  max_functions: {thresholds.max_functions}")
    print(f"  max_function_length: {thresholds.max_function_length}")
    print(f"  max_classes_per_file: {thresholds.max_classes_per_file}")
    print(f"  complexity_warning: {thresholds.complexity_warning}")
    print(f"  complexity_critical: {thresholds.complexity_critical}")
    print(f"  scout_cooldown_days: {thresholds.scout_cooldown_days}")
    print()
    print("Execution:")
    exec_cfg = config.execution
    print(f"  max_extractions_per_scout: {exec_cfg.max_extractions_per_scout}")
    print(f"  require_passing_tests: {exec_cfg.require_passing_tests}")
    print(f"  auto_rollback_on_failure: {exec_cfg.auto_rollback_on_failure}")
    print()
    print(f"Default Policy: {config.default_policy}")
    if config.directory_overrides:
        print("Directory Overrides:")
        for path, policy in config.directory_overrides.items():
            print(f"  {path}: {policy}")


def _handle_history(args, db: Optional[ScoutDatabase]):
    """Handle history command."""
    if not db:
        print("Database is disabled. Use without --no-db to see history.")
        return

    report = db.generate_history_report(args.path)
    if report:
        print(report)
    else:
        print(f"No history found for: {args.path}")
        print("Run 'scout analyze' on this file to start tracking.")


def _handle_dashboard(db: Optional[ScoutDatabase]):
    """Handle dashboard command."""
    if not db:
        print("Database is disabled. Use without --no-db to see dashboard.")
        return

    print(db.generate_dashboard())


def _add_threshold_args(parser):
    """Add threshold override arguments to a parser."""
    parser.add_argument(
        '--max-lines', type=int, default=None,
        help=f"Max lines per file (default: {DEFAULT_THRESHOLDS['max_lines']})"
    )
    parser.add_argument(
        '--max-imports', type=int, default=None,
        help=f"Max imports per file (default: {DEFAULT_THRESHOLDS['max_imports']})"
    )
    parser.add_argument(
        '--max-functions', type=int, default=None,
        help=f"Max functions per file (default: {DEFAULT_THRESHOLDS['max_functions']})"
    )
    parser.add_argument(
        '--max-function-length', type=int, default=None,
        help=f"Max lines per function (default: {DEFAULT_THRESHOLDS['max_function_length']})"
    )
    parser.add_argument(
        '--max-classes', type=int, default=None,
        help=f"Max classes per file (default: {DEFAULT_THRESHOLDS['max_classes_per_file']})"
    )


def _build_thresholds(args) -> dict:
    """Build threshold dict from parsed args."""
    thresholds = {}

    if hasattr(args, 'max_lines') and args.max_lines is not None:
        thresholds['max_lines'] = args.max_lines
    if hasattr(args, 'max_imports') and args.max_imports is not None:
        thresholds['max_imports'] = args.max_imports
    if hasattr(args, 'max_functions') and args.max_functions is not None:
        thresholds['max_functions'] = args.max_functions
    if hasattr(args, 'max_function_length') and args.max_function_length is not None:
        thresholds['max_function_length'] = args.max_function_length
    if hasattr(args, 'max_classes') and args.max_classes is not None:
        thresholds['max_classes_per_file'] = args.max_classes

    return thresholds if thresholds else None


if __name__ == '__main__':
    main()
