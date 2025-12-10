"""File analyzer using Python's AST module for code metrics extraction."""

import ast
import os
from typing import List, Optional
from .models import FileMetrics, FunctionInfo, ClassInfo


class ComplexityVisitor(ast.NodeVisitor):
    """AST visitor to calculate complexity metrics."""

    def __init__(self):
        self.complexity = 0
        self.max_depth = 0
        self._current_depth = 0

    def _increment_depth(self):
        self._current_depth += 1
        self.max_depth = max(self.max_depth, self._current_depth)

    def _decrement_depth(self):
        self._current_depth -= 1

    def visit_If(self, node):
        self.complexity += 1
        self._increment_depth()
        self.generic_visit(node)
        self._decrement_depth()

    def visit_For(self, node):
        self.complexity += 1
        self._increment_depth()
        self.generic_visit(node)
        self._decrement_depth()

    def visit_While(self, node):
        self.complexity += 1
        self._increment_depth()
        self.generic_visit(node)
        self._decrement_depth()

    def visit_Try(self, node):
        self.complexity += 1
        self._increment_depth()
        self.generic_visit(node)
        self._decrement_depth()

    def visit_ExceptHandler(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_With(self, node):
        self.complexity += 1
        self._increment_depth()
        self.generic_visit(node)
        self._decrement_depth()

    def visit_BoolOp(self, node):
        # and/or add complexity
        self.complexity += len(node.values) - 1
        self.generic_visit(node)

    def visit_comprehension(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_Lambda(self, node):
        self.complexity += 1
        self.generic_visit(node)


class FileAnalyzer:
    """Analyzes Python files for metrics and structure."""

    def analyze(self, path: str) -> FileMetrics:
        """Analyze a Python file and return metrics."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")

        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            lines = content.splitlines()

        line_count = len(lines)

        # Parse AST
        try:
            tree = ast.parse(content, filename=path)
        except SyntaxError as e:
            # Return basic metrics if we can't parse
            return FileMetrics(
                path=path,
                line_count=line_count,
                function_count=0,
                class_count=0,
                import_count=0,
                avg_function_length=0.0,
                max_function_length=0,
                complexity_score=0.0,
                functions=[],
                classes=[],
                imports=[],
            )

        # Extract functions (top-level only)
        functions = self._extract_functions(tree)

        # Extract classes
        classes = self._extract_classes(tree)

        # Extract imports
        imports = self._extract_imports(tree)

        # Calculate function stats
        function_lengths = [f.line_count for f in functions]
        # Also include methods from classes
        for cls in classes:
            function_lengths.extend(m.line_count for m in cls.methods)

        avg_function_length = (
            sum(function_lengths) / len(function_lengths)
            if function_lengths else 0.0
        )
        max_function_length = max(function_lengths) if function_lengths else 0

        # Calculate complexity score
        complexity_score = self._calculate_complexity(tree, line_count)

        return FileMetrics(
            path=path,
            line_count=line_count,
            function_count=len(functions),
            class_count=len(classes),
            import_count=len(imports),
            avg_function_length=round(avg_function_length, 1),
            max_function_length=max_function_length,
            complexity_score=round(complexity_score, 2),
            functions=functions,
            classes=classes,
            imports=imports,
        )

    def _extract_functions(self, tree: ast.AST) -> List[FunctionInfo]:
        """Extract top-level function definitions."""
        functions = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(self._function_info(node))

        return functions

    def _extract_classes(self, tree: ast.AST) -> List[ClassInfo]:
        """Extract class definitions."""
        classes = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(self._class_info(node))

        return classes

    def _extract_imports(self, tree: ast.AST) -> List[str]:
        """Extract import statements."""
        imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                imports.append(module)

        return list(set(imports))  # Deduplicate

    def _function_info(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
        """Extract information about a function."""
        line_start = node.lineno
        line_end = self._get_end_lineno(node)
        line_count = line_end - line_start + 1

        decorators = [
            self._get_decorator_name(d) for d in node.decorator_list
        ]

        return FunctionInfo(
            name=node.name,
            line_start=line_start,
            line_end=line_end,
            line_count=line_count,
            param_count=len(node.args.args),
            is_async=isinstance(node, ast.AsyncFunctionDef),
            decorators=decorators,
        )

    def _class_info(self, node: ast.ClassDef) -> ClassInfo:
        """Extract information about a class."""
        line_start = node.lineno
        line_end = self._get_end_lineno(node)
        line_count = line_end - line_start + 1

        # Extract methods
        methods = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(self._function_info(item))

        base_classes = [
            self._get_base_name(base) for base in node.bases
        ]

        return ClassInfo(
            name=node.name,
            line_start=line_start,
            line_end=line_end,
            line_count=line_count,
            method_count=len(methods),
            base_classes=base_classes,
            methods=methods,
        )

    def _get_end_lineno(self, node: ast.AST) -> int:
        """Get the end line number of a node."""
        if hasattr(node, 'end_lineno') and node.end_lineno:
            return node.end_lineno
        # Fallback: find max line number in children
        max_line = node.lineno
        for child in ast.walk(node):
            if hasattr(child, 'lineno') and child.lineno:
                max_line = max(max_line, child.lineno)
            if hasattr(child, 'end_lineno') and child.end_lineno:
                max_line = max(max_line, child.end_lineno)
        return max_line

    def _get_decorator_name(self, node: ast.expr) -> str:
        """Get the name of a decorator."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_decorator_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return "unknown"

    def _get_base_name(self, node: ast.expr) -> str:
        """Get the name of a base class."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_base_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Subscript):
            return self._get_base_name(node.value)
        return "unknown"

    def _calculate_complexity(self, tree: ast.AST, line_count: int) -> float:
        """Calculate a normalized complexity score (0.0 - 1.0)."""
        visitor = ComplexityVisitor()
        visitor.visit(tree)

        # Normalize complexity based on file size
        # Base complexity per line expectation
        expected_complexity = line_count / 10  # 1 complexity point per 10 lines

        if expected_complexity == 0:
            return 0.0

        # Actual vs expected ratio, capped at 1.0
        complexity_ratio = min(visitor.complexity / expected_complexity, 2.0) / 2.0

        # Depth penalty (deeper nesting = higher complexity)
        depth_penalty = min(visitor.max_depth / 10, 0.3)  # Max 0.3 from depth

        # Combined score
        score = min(complexity_ratio + depth_penalty, 1.0)

        return score
