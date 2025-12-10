"""Identifies extraction opportunities based on file metrics."""

import os
import re
from collections import defaultdict
from typing import List, Dict, Set
from .models import FileMetrics, ExtractionOpportunity, FunctionInfo, ClassInfo


class OpportunityIdentifier:
    """Identifies refactoring opportunities from file metrics."""

    def __init__(self):
        # Minimum items to suggest extraction
        self.min_cluster_size = 3
        # Minimum lines to suggest extraction
        self.min_extraction_lines = 50

    def identify(self, metrics: FileMetrics) -> List[ExtractionOpportunity]:
        """Identify all extraction opportunities for a file."""
        opportunities = []

        # Strategy 1: Large classes should be in their own files
        opportunities.extend(self._identify_class_extractions(metrics))

        # Strategy 2: Function clusters by prefix/suffix
        opportunities.extend(self._identify_function_clusters(metrics))

        # Strategy 3: Long functions need helper extraction
        opportunities.extend(self._identify_long_functions(metrics))

        # Strategy 4: Many related imports suggest module boundaries
        opportunities.extend(self._identify_import_clusters(metrics))

        # Sort by priority (high first) and estimated lines (larger first)
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        opportunities.sort(
            key=lambda o: (priority_order.get(o.priority, 3), -o.estimated_lines)
        )

        return opportunities

    def _identify_class_extractions(
        self, metrics: FileMetrics
    ) -> List[ExtractionOpportunity]:
        """Identify classes that should be in their own files."""
        opportunities = []

        for cls in metrics.classes:
            # Large classes (>200 lines) or multiple classes in file
            if cls.line_count > 200 or (
                metrics.class_count > 1 and cls.line_count > 100
            ):
                suggested_file = self._class_to_filename(cls.name)
                base_dir = os.path.dirname(metrics.path)
                suggested_path = os.path.join(base_dir, suggested_file)

                priority = 'high' if cls.line_count > 300 else 'medium'

                opportunities.append(ExtractionOpportunity(
                    type='extract_class',
                    description=f"Extract class '{cls.name}' to its own module",
                    target_items=[cls.name],
                    suggested_path=suggested_path,
                    estimated_lines=cls.line_count,
                    priority=priority,
                ))

        return opportunities

    def _identify_function_clusters(
        self, metrics: FileMetrics
    ) -> List[ExtractionOpportunity]:
        """Identify clusters of related functions by naming patterns."""
        opportunities = []

        # Group functions by prefix (e.g., handle_, process_, get_)
        prefix_clusters = self._cluster_by_prefix(metrics.functions)

        for prefix, functions in prefix_clusters.items():
            if len(functions) >= self.min_cluster_size:
                total_lines = sum(f.line_count for f in functions)

                if total_lines >= self.min_extraction_lines:
                    suggested_file = f"{prefix.rstrip('_')}.py"
                    base_dir = os.path.dirname(metrics.path)
                    suggested_path = os.path.join(base_dir, suggested_file)

                    priority = 'high' if total_lines > 200 else 'medium'

                    opportunities.append(ExtractionOpportunity(
                        type='extract_module',
                        description=(
                            f"Extract {len(functions)} '{prefix}*' functions "
                            f"to dedicated module"
                        ),
                        target_items=[f.name for f in functions],
                        suggested_path=suggested_path,
                        estimated_lines=total_lines,
                        priority=priority,
                    ))

        # Also check for suffix patterns (e.g., _handler, _manager)
        suffix_clusters = self._cluster_by_suffix(metrics.functions)

        for suffix, functions in suffix_clusters.items():
            if len(functions) >= self.min_cluster_size:
                total_lines = sum(f.line_count for f in functions)

                if total_lines >= self.min_extraction_lines:
                    suggested_file = f"{suffix.lstrip('_')}s.py"
                    base_dir = os.path.dirname(metrics.path)
                    suggested_path = os.path.join(base_dir, suggested_file)

                    priority = 'high' if total_lines > 200 else 'medium'

                    opportunities.append(ExtractionOpportunity(
                        type='extract_module',
                        description=(
                            f"Extract {len(functions)} '*{suffix}' functions "
                            f"to dedicated module"
                        ),
                        target_items=[f.name for f in functions],
                        suggested_path=suggested_path,
                        estimated_lines=total_lines,
                        priority=priority,
                    ))

        return opportunities

    def _identify_long_functions(
        self, metrics: FileMetrics
    ) -> List[ExtractionOpportunity]:
        """Identify functions that are too long and need decomposition."""
        opportunities = []

        # Check top-level functions
        for func in metrics.functions:
            if func.line_count > 50:
                priority = 'high' if func.line_count > 100 else 'medium'

                opportunities.append(ExtractionOpportunity(
                    type='extract_helpers',
                    description=(
                        f"Decompose function '{func.name}' ({func.line_count} lines) "
                        f"into smaller helpers"
                    ),
                    target_items=[func.name],
                    suggested_path=metrics.path,  # Same file, just refactor
                    estimated_lines=func.line_count,
                    priority=priority,
                ))

        # Check methods in classes
        for cls in metrics.classes:
            for method in cls.methods:
                if method.line_count > 50:
                    priority = 'high' if method.line_count > 100 else 'medium'

                    opportunities.append(ExtractionOpportunity(
                        type='extract_helpers',
                        description=(
                            f"Decompose method '{cls.name}.{method.name}' "
                            f"({method.line_count} lines) into smaller helpers"
                        ),
                        target_items=[f"{cls.name}.{method.name}"],
                        suggested_path=metrics.path,
                        estimated_lines=method.line_count,
                        priority=priority,
                    ))

        return opportunities

    def _identify_import_clusters(
        self, metrics: FileMetrics
    ) -> List[ExtractionOpportunity]:
        """Identify import clusters that suggest module boundaries."""
        opportunities = []

        if metrics.import_count < 15:
            return opportunities

        # Group imports by top-level package
        package_groups: Dict[str, List[str]] = defaultdict(list)
        for imp in metrics.imports:
            top_package = imp.split('.')[0]
            package_groups[top_package].append(imp)

        # If many imports from same package, might indicate focused responsibility
        for package, imports in package_groups.items():
            if len(imports) >= 5 and package not in ('typing', 'os', 'sys', 'json'):
                opportunities.append(ExtractionOpportunity(
                    type='extract_module',
                    description=(
                        f"Consider extracting '{package}'-related code "
                        f"({len(imports)} imports from this package)"
                    ),
                    target_items=imports,
                    suggested_path=f"<analyze {package} usage>",
                    estimated_lines=0,  # Unknown without deeper analysis
                    priority='low',
                ))

        return opportunities

    def _cluster_by_prefix(
        self, functions: List[FunctionInfo]
    ) -> Dict[str, List[FunctionInfo]]:
        """Group functions by common prefix."""
        clusters: Dict[str, List[FunctionInfo]] = defaultdict(list)

        for func in functions:
            # Skip private/dunder methods
            if func.name.startswith('__'):
                continue

            # Extract prefix (e.g., "handle_" from "handle_message")
            match = re.match(r'^([a-z]+_)', func.name)
            if match:
                prefix = match.group(1)
                clusters[prefix].append(func)

        return clusters

    def _cluster_by_suffix(
        self, functions: List[FunctionInfo]
    ) -> Dict[str, List[FunctionInfo]]:
        """Group functions by common suffix."""
        clusters: Dict[str, List[FunctionInfo]] = defaultdict(list)

        for func in functions:
            # Skip private/dunder methods
            if func.name.startswith('__'):
                continue

            # Extract suffix (e.g., "_handler" from "message_handler")
            match = re.search(r'(_[a-z]+)$', func.name)
            if match:
                suffix = match.group(1)
                clusters[suffix].append(func)

        return clusters

    def _class_to_filename(self, class_name: str) -> str:
        """Convert CamelCase class name to snake_case filename."""
        # Insert underscore before uppercase letters
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', class_name)
        # Insert underscore before uppercase followed by lowercase
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
        return s2.lower() + '.py'
