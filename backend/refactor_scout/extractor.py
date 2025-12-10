"""
Extraction execution for Refactor Scout.

Performs safe code extractions with rollback capability.
"""

import ast
import os
import re
import subprocess
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set, Tuple

from .models import ExtractionOpportunity, FileMetrics, ClassInfo, FunctionInfo


@dataclass
class ExtractionResult:
    """Result of an extraction operation."""
    success: bool
    source_file: str
    target_file: Optional[str] = None
    items_extracted: List[str] = field(default_factory=list)
    lines_moved: int = 0
    error: Optional[str] = None
    backup_path: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'source_file': self.source_file,
            'target_file': self.target_file,
            'items_extracted': self.items_extracted,
            'lines_moved': self.lines_moved,
            'error': self.error,
        }


class CodeExtractor:
    """Performs safe code extractions with verification."""

    def __init__(self, working_dir: str = '.'):
        self.working_dir = Path(working_dir)
        self.backup_dir = self.working_dir / '.scout_backups'

    def extract_class(
        self,
        source_path: str,
        class_name: str,
        target_path: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Extract a class to its own file.

        Args:
            source_path: Path to source file containing the class
            class_name: Name of the class to extract
            target_path: Target file path (auto-generated if not provided)

        Returns:
            ExtractionResult with success status and details
        """
        source_path = Path(source_path)

        if not source_path.exists():
            return ExtractionResult(
                success=False,
                source_file=str(source_path),
                error=f"Source file not found: {source_path}"
            )

        # Read source file
        source_content = source_path.read_text(encoding='utf-8')

        try:
            tree = ast.parse(source_content)
        except SyntaxError as e:
            return ExtractionResult(
                success=False,
                source_file=str(source_path),
                error=f"Syntax error in source file: {e}"
            )

        # Find the class
        class_node = None
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                class_node = node
                break

        if not class_node:
            return ExtractionResult(
                success=False,
                source_file=str(source_path),
                error=f"Class '{class_name}' not found in {source_path}"
            )

        # Generate target path if not provided
        if target_path is None:
            target_path = source_path.parent / self._class_to_filename(class_name)
        else:
            target_path = Path(target_path)

        if target_path.exists():
            return ExtractionResult(
                success=False,
                source_file=str(source_path),
                target_file=str(target_path),
                error=f"Target file already exists: {target_path}"
            )

        # Create backup
        backup_path = self._create_backup(source_path)

        try:
            # Extract class code
            lines = source_content.splitlines(keepends=True)
            class_start = class_node.lineno - 1  # 0-indexed
            class_end = self._get_node_end(class_node, lines)

            # Get decorators too
            if class_node.decorator_list:
                class_start = class_node.decorator_list[0].lineno - 1

            class_lines = lines[class_start:class_end]
            class_code = ''.join(class_lines)

            # Find imports needed by the class
            needed_imports = self._find_imports_for_code(class_code, tree)

            # Build target file content
            target_content = self._build_extracted_file(
                class_code,
                needed_imports,
                source_path,
            )

            # Remove class from source (keep import for backwards compat)
            new_source_lines = lines[:class_start] + lines[class_end:]

            # Add import statement to source for backwards compatibility
            import_stmt = f"from {self._path_to_module(target_path)} import {class_name}\n"
            new_source_content = self._add_import_to_source(
                ''.join(new_source_lines),
                import_stmt,
            )

            # Verify both files parse correctly before writing
            try:
                ast.parse(target_content)
                ast.parse(new_source_content)
            except SyntaxError as e:
                return ExtractionResult(
                    success=False,
                    source_file=str(source_path),
                    target_file=str(target_path),
                    error=f"Generated code has syntax error: {e}",
                    backup_path=str(backup_path),
                )

            # Write files
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(target_content, encoding='utf-8')
            source_path.write_text(new_source_content, encoding='utf-8')

            # Verify with py_compile
            if not self._verify_syntax(source_path) or not self._verify_syntax(target_path):
                self._rollback(source_path, backup_path, target_path)
                return ExtractionResult(
                    success=False,
                    source_file=str(source_path),
                    target_file=str(target_path),
                    error="Syntax verification failed after extraction",
                    backup_path=str(backup_path),
                )

            return ExtractionResult(
                success=True,
                source_file=str(source_path),
                target_file=str(target_path),
                items_extracted=[class_name],
                lines_moved=len(class_lines),
                backup_path=str(backup_path),
            )

        except Exception as e:
            # Rollback on any error
            self._rollback(source_path, backup_path, target_path if 'target_path' in dir() else None)
            return ExtractionResult(
                success=False,
                source_file=str(source_path),
                error=f"Extraction failed: {e}",
                backup_path=str(backup_path),
            )

    def extract_functions(
        self,
        source_path: str,
        function_names: List[str],
        target_path: str,
        module_docstring: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Extract multiple functions to a new module.

        Args:
            source_path: Path to source file
            function_names: Names of functions to extract
            target_path: Target file path
            module_docstring: Optional docstring for new module

        Returns:
            ExtractionResult with success status and details
        """
        source_path = Path(source_path)
        target_path = Path(target_path)

        if not source_path.exists():
            return ExtractionResult(
                success=False,
                source_file=str(source_path),
                error=f"Source file not found: {source_path}"
            )

        if target_path.exists():
            return ExtractionResult(
                success=False,
                source_file=str(source_path),
                target_file=str(target_path),
                error=f"Target file already exists: {target_path}"
            )

        source_content = source_path.read_text(encoding='utf-8')

        try:
            tree = ast.parse(source_content)
        except SyntaxError as e:
            return ExtractionResult(
                success=False,
                source_file=str(source_path),
                error=f"Syntax error in source file: {e}"
            )

        # Find all requested functions
        function_nodes = []
        found_names = set()

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in function_names:
                    function_nodes.append(node)
                    found_names.add(node.name)

        missing = set(function_names) - found_names
        if missing:
            return ExtractionResult(
                success=False,
                source_file=str(source_path),
                error=f"Functions not found: {missing}"
            )

        # Create backup
        backup_path = self._create_backup(source_path)

        try:
            lines = source_content.splitlines(keepends=True)

            # Collect function code and ranges to remove
            extracted_code_parts = []
            ranges_to_remove = []  # (start, end) tuples

            for node in sorted(function_nodes, key=lambda n: n.lineno):
                func_start = node.lineno - 1
                func_end = self._get_node_end(node, lines)

                # Include decorators
                if node.decorator_list:
                    func_start = node.decorator_list[0].lineno - 1

                func_lines = lines[func_start:func_end]
                extracted_code_parts.append(''.join(func_lines))
                ranges_to_remove.append((func_start, func_end))

            extracted_code = '\n'.join(extracted_code_parts)

            # Find imports needed by extracted functions
            needed_imports = self._find_imports_for_code(extracted_code, tree)

            # Build target file
            target_content = self._build_extracted_file(
                extracted_code,
                needed_imports,
                source_path,
                module_docstring,
            )

            # Remove functions from source (in reverse order to preserve line numbers)
            new_lines = list(lines)
            for start, end in sorted(ranges_to_remove, reverse=True):
                del new_lines[start:end]

            # Add import for backwards compatibility
            import_names = ', '.join(function_names)
            import_stmt = f"from {self._path_to_module(target_path)} import {import_names}\n"
            new_source_content = self._add_import_to_source(
                ''.join(new_lines),
                import_stmt,
            )

            # Verify syntax before writing
            try:
                ast.parse(target_content)
                ast.parse(new_source_content)
            except SyntaxError as e:
                return ExtractionResult(
                    success=False,
                    source_file=str(source_path),
                    target_file=str(target_path),
                    error=f"Generated code has syntax error: {e}",
                    backup_path=str(backup_path),
                )

            # Write files
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(target_content, encoding='utf-8')
            source_path.write_text(new_source_content, encoding='utf-8')

            # Verify with py_compile
            if not self._verify_syntax(source_path) or not self._verify_syntax(target_path):
                self._rollback(source_path, backup_path, target_path)
                return ExtractionResult(
                    success=False,
                    source_file=str(source_path),
                    target_file=str(target_path),
                    error="Syntax verification failed after extraction",
                    backup_path=str(backup_path),
                )

            total_lines = sum(end - start for start, end in ranges_to_remove)

            return ExtractionResult(
                success=True,
                source_file=str(source_path),
                target_file=str(target_path),
                items_extracted=function_names,
                lines_moved=total_lines,
                backup_path=str(backup_path),
            )

        except Exception as e:
            self._rollback(source_path, backup_path, target_path)
            return ExtractionResult(
                success=False,
                source_file=str(source_path),
                error=f"Extraction failed: {e}",
                backup_path=str(backup_path),
            )

    def rollback(self, backup_path: str, source_path: str, target_path: Optional[str] = None):
        """Rollback an extraction using backup."""
        self._rollback(Path(source_path), Path(backup_path), Path(target_path) if target_path else None)

    def _create_backup(self, path: Path) -> Path:
        """Create a backup of a file."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"{path.stem}_{timestamp}{path.suffix}"
        backup_path = self.backup_dir / backup_name
        shutil.copy2(path, backup_path)
        return backup_path

    def _rollback(self, source_path: Path, backup_path: Path, target_path: Optional[Path] = None):
        """Rollback changes using backup."""
        if backup_path and backup_path.exists():
            shutil.copy2(backup_path, source_path)
        if target_path and target_path.exists():
            target_path.unlink()

    def _verify_syntax(self, path: Path) -> bool:
        """Verify a Python file has valid syntax using py_compile."""
        try:
            result = subprocess.run(
                ['python', '-m', 'py_compile', str(path)],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _get_node_end(self, node: ast.AST, lines: List[str]) -> int:
        """Get the end line of an AST node."""
        if hasattr(node, 'end_lineno') and node.end_lineno:
            return node.end_lineno

        # Fallback: find by walking children
        max_line = node.lineno
        for child in ast.walk(node):
            if hasattr(child, 'lineno'):
                max_line = max(max_line, child.lineno)
            if hasattr(child, 'end_lineno') and child.end_lineno:
                max_line = max(max_line, child.end_lineno)

        return max_line

    def _find_imports_for_code(self, code: str, source_tree: ast.AST) -> List[str]:
        """Find imports from source that are needed by the extracted code."""
        # Get all names used in the extracted code
        try:
            extracted_tree = ast.parse(code)
        except SyntaxError:
            return []

        used_names = set()
        for node in ast.walk(extracted_tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                # Get the root name (e.g., 'os' from 'os.path.join')
                root = node
                while isinstance(root, ast.Attribute):
                    root = root.value
                if isinstance(root, ast.Name):
                    used_names.add(root.id)

        # Find matching imports in source
        imports = []
        for node in ast.iter_child_nodes(source_tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name.split('.')[0]
                    if name in used_names:
                        imports.append(ast.unparse(node))
                        break
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                for alias in node.names:
                    name = alias.asname or alias.name
                    if name in used_names or alias.name == '*':
                        imports.append(ast.unparse(node))
                        break

        return list(set(imports))

    def _build_extracted_file(
        self,
        code: str,
        imports: List[str],
        source_path: Path,
        docstring: Optional[str] = None,
    ) -> str:
        """Build the content for an extracted file."""
        parts = []

        # Docstring
        if docstring:
            parts.append(f'"""{docstring}"""\n')
        else:
            parts.append(f'"""Extracted from {source_path.name}"""\n')

        parts.append('')

        # Imports
        if imports:
            parts.extend(imports)
            parts.append('')

        # Extracted code
        parts.append(code.strip())
        parts.append('')

        return '\n'.join(parts)

    def _add_import_to_source(self, content: str, import_stmt: str) -> str:
        """Add an import statement to source file after existing imports."""
        lines = content.splitlines(keepends=True)

        # Find the last import line
        last_import_idx = 0
        in_docstring = False
        docstring_char = None

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Track docstrings
            if not in_docstring:
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    docstring_char = stripped[:3]
                    if stripped.count(docstring_char) >= 2:
                        continue  # Single-line docstring
                    in_docstring = True
                    continue
            else:
                if docstring_char in stripped:
                    in_docstring = False
                continue

            # Check for import statements
            if stripped.startswith('import ') or stripped.startswith('from '):
                last_import_idx = i + 1

        # Insert after last import (or at beginning if no imports)
        lines.insert(last_import_idx, import_stmt)

        return ''.join(lines)

    def _class_to_filename(self, class_name: str) -> str:
        """Convert CamelCase class name to snake_case filename."""
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', class_name)
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
        return s2.lower() + '.py'

    def _path_to_module(self, path: Path) -> str:
        """Convert a file path to a Python module path."""
        # Remove .py extension and convert path separators to dots
        parts = path.with_suffix('').parts

        # Remove leading 'backend' if present (adjust for your project structure)
        if parts and parts[0] == 'backend':
            parts = parts[1:]

        return '.'.join(parts)


class GitIntegration:
    """Git operations for safe refactoring branches."""

    def __init__(self, repo_path: str = '.'):
        self.repo_path = Path(repo_path)

    def create_refactor_branch(self, description: str = 'scout') -> Optional[str]:
        """Create a new refactor branch and switch to it."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        branch_name = f"refactor/scout-{description}-{timestamp}"

        try:
            # Check for uncommitted changes
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                return None  # Has uncommitted changes

            # Create and checkout branch
            subprocess.run(
                ['git', 'checkout', '-b', branch_name],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )

            return branch_name

        except subprocess.CalledProcessError:
            return None

    def commit_extraction(
        self,
        result: ExtractionResult,
        message: Optional[str] = None,
    ) -> bool:
        """Commit an extraction result."""
        if not result.success:
            return False

        try:
            # Stage modified files
            files_to_add = [result.source_file]
            if result.target_file:
                files_to_add.append(result.target_file)

            subprocess.run(
                ['git', 'add'] + files_to_add,
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )

            # Commit
            if message is None:
                items = ', '.join(result.items_extracted)
                message = f"refactor(scout): Extract {items} to {result.target_file}"

            subprocess.run(
                ['git', 'commit', '-m', message,
                 '--author', 'Daedalus <daedalus@cass-vessel.local>'],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )

            return True

        except subprocess.CalledProcessError:
            return False

    def get_current_branch(self) -> Optional[str]:
        """Get current git branch name."""
        try:
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    def switch_branch(self, branch_name: str) -> bool:
        """Switch to a branch."""
        try:
            subprocess.run(
                ['git', 'checkout', branch_name],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def has_uncommitted_changes(self) -> bool:
        """Check if there are uncommitted changes."""
        try:
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            return True  # Assume changes if we can't check
