"""
Language Support for Mind Palace Cartographer.

Provides language-specific code analysis and anchor pattern generation.
Each language implementation knows how to:
1. Parse source files and extract code elements
2. Generate anchor patterns that match actual code syntax
3. Verify anchors exist in source files
"""

import ast
import hashlib
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type

logger = logging.getLogger(__name__)


@dataclass
class CodeElement:
    """A discovered code element (function, class, etc.)."""
    name: str
    element_type: str  # "function", "class", "method"
    file: str
    line: int
    signature: str
    docstring: Optional[str] = None
    calls: List[str] = field(default_factory=list)
    called_by: List[str] = field(default_factory=list)
    parameters: List[Tuple[str, str]] = field(default_factory=list)
    returns: Optional[str] = None
    # For methods, store class info separately
    class_name: Optional[str] = None
    # The simple name without class prefix
    simple_name: Optional[str] = None

    def __post_init__(self):
        # Derive simple_name from name if not set
        if self.simple_name is None:
            if "." in self.name and self.element_type == "method":
                self.simple_name = self.name.split(".")[-1]
            else:
                self.simple_name = self.name


@dataclass
class AnchorPattern:
    """Pattern for locating code in source files."""
    pattern: str
    is_regex: bool = False
    # For display purposes
    description: str = ""

    def matches(self, content: str) -> bool:
        """Check if this pattern matches the content."""
        if self.is_regex:
            return bool(re.search(self.pattern, content, re.MULTILINE))
        return self.pattern in content

    def find_line(self, content: str) -> Optional[int]:
        """Find the line number where this pattern matches (1-indexed)."""
        lines = content.split("\n")
        if self.is_regex:
            regex = re.compile(self.pattern)
            for i, line in enumerate(lines, 1):
                if regex.search(line):
                    return i
        else:
            for i, line in enumerate(lines, 1):
                if self.pattern in line:
                    return i
        return None


class LanguageSupport(ABC):
    """
    Base class for language-specific code analysis.

    Subclasses implement parsing and pattern generation for specific languages.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable language name."""
        pass

    @property
    @abstractmethod
    def extensions(self) -> List[str]:
        """File extensions this language handles (e.g., ['.py', '.pyi'])."""
        pass

    @abstractmethod
    def analyze_file(self, file_path: Path, project_root: Path) -> List[CodeElement]:
        """
        Analyze a source file and extract code elements.

        Args:
            file_path: Absolute path to the source file
            project_root: Project root for computing relative paths

        Returns:
            List of discovered code elements
        """
        pass

    @abstractmethod
    def generate_anchor_pattern(self, element: CodeElement) -> AnchorPattern:
        """
        Generate an anchor pattern for locating this element in source.

        Args:
            element: The code element to create an anchor for

        Returns:
            AnchorPattern that can locate this element
        """
        pass

    def compute_signature_hash(self, element: CodeElement) -> str:
        """Compute a hash of the element's signature for drift detection."""
        return hashlib.md5(element.signature.encode()).hexdigest()[:8]


class PythonSupport(LanguageSupport):
    """Python language support for the Cartographer."""

    @property
    def name(self) -> str:
        return "Python"

    @property
    def extensions(self) -> List[str]:
        return [".py", ".pyi"]

    def analyze_file(self, file_path: Path, project_root: Path) -> List[CodeElement]:
        """Analyze a Python file using AST parsing."""
        elements = []

        try:
            with open(file_path) as f:
                source = f.read()
            tree = ast.parse(source)
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return elements

        relative_path = str(file_path.relative_to(project_root))

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Skip methods - they're handled with their classes
                # Check if this function is at module level
                # (ast.walk doesn't preserve hierarchy, so we check later)
                pass

            elif isinstance(node, ast.ClassDef):
                # Extract class
                element = self._extract_class(node, relative_path, source)
                elements.append(element)

                # Extract methods from this class
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method = self._extract_function(
                            item, relative_path, source,
                            class_name=node.name
                        )
                        elements.append(method)

        # Extract top-level functions (need a second pass to avoid class methods)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                element = self._extract_function(node, relative_path, source)
                elements.append(element)

        return elements

    def _extract_function(
        self,
        node: ast.FunctionDef,
        file_path: str,
        source: str,
        class_name: Optional[str] = None,
    ) -> CodeElement:
        """Extract a function/method as a CodeElement."""
        # Build argument list
        args = []
        for arg in node.args.args:
            arg_type = ""
            if arg.annotation:
                arg_type = ast.unparse(arg.annotation)
            args.append((arg.arg, arg_type))

        # Get return type
        returns = None
        if node.returns:
            returns = ast.unparse(node.returns)

        # Build signature
        signature = f"def {node.name}({', '.join(a[0] for a in args)})"
        if returns:
            signature += f" -> {returns}"

        # Get docstring
        docstring = ast.get_docstring(node)

        # Find function calls within this function
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)

        element_type = "method" if class_name else "function"
        full_name = f"{class_name}.{node.name}" if class_name else node.name

        return CodeElement(
            name=full_name,
            element_type=element_type,
            file=file_path,
            line=node.lineno,
            signature=signature,
            docstring=docstring,
            calls=list(set(calls)),
            parameters=args,
            returns=returns,
            class_name=class_name,
            simple_name=node.name,
        )

    def _extract_class(self, node: ast.ClassDef, file_path: str, source: str) -> CodeElement:
        """Extract a class as a CodeElement."""
        # Get base classes
        bases = [ast.unparse(b) for b in node.bases]
        signature = f"class {node.name}"
        if bases:
            signature += f"({', '.join(bases)})"

        docstring = ast.get_docstring(node)

        return CodeElement(
            name=node.name,
            element_type="class",
            file=file_path,
            line=node.lineno,
            signature=signature,
            docstring=docstring,
            simple_name=node.name,
        )

    def generate_anchor_pattern(self, element: CodeElement) -> AnchorPattern:
        """
        Generate Python-appropriate anchor patterns.

        Patterns:
        - Functions: "def function_name(" (literal)
        - Classes: "class ClassName" (literal, handles inheritance variations)
        - Methods: regex to match "def method_name(" with leading whitespace
        """
        if element.element_type == "class":
            # Classes: match "class Name" - handles "(bases)" and ":" variations
            return AnchorPattern(
                pattern=f"class {element.simple_name}",
                is_regex=False,
                description=f"Class definition: {element.simple_name}",
            )

        elif element.element_type == "method":
            # Methods: need regex to handle indentation and async
            # Match "def method_name(" or "async def method_name(" with leading whitespace
            # Using simple_name to avoid "ClassName.method_name"
            pattern = rf"^\s+(?:async\s+)?def {re.escape(element.simple_name)}\("
            return AnchorPattern(
                pattern=pattern,
                is_regex=True,
                description=f"Method: {element.class_name}.{element.simple_name}",
            )

        else:  # function
            # Top-level functions: handle both sync and async
            # "def name(" or "async def name(" at start of line
            pattern = rf"^(?:async\s+)?def {re.escape(element.simple_name)}\("
            return AnchorPattern(
                pattern=pattern,
                is_regex=True,
                description=f"Function: {element.simple_name}",
            )


class TypeScriptSupport(LanguageSupport):
    """TypeScript/JavaScript language support (basic implementation)."""

    @property
    def name(self) -> str:
        return "TypeScript"

    @property
    def extensions(self) -> List[str]:
        return [".ts", ".tsx", ".js", ".jsx"]

    def analyze_file(self, file_path: Path, project_root: Path) -> List[CodeElement]:
        """
        Basic TypeScript analysis using regex patterns.

        For production use, consider using a proper TS parser like
        tree-sitter or typescript compiler API.
        """
        elements = []
        relative_path = str(file_path.relative_to(project_root))

        try:
            with open(file_path) as f:
                content = f.read()
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            return elements

        # Function patterns
        # export function name(
        # function name(
        # const name = ( or const name = async (
        # export const name = (
        func_patterns = [
            (r"^(?:export\s+)?function\s+(\w+)\s*\(", "function"),
            (r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(", "function"),
            (r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function", "function"),
        ]

        # Class patterns
        class_pattern = r"^(?:export\s+)?class\s+(\w+)"

        # Method patterns (inside classes)
        method_patterns = [
            (r"^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*[:{]", "method"),
            (r"^\s+(?:public|private|protected)?\s*(?:async\s+)?(\w+)\s*\(", "method"),
        ]

        lines = content.split("\n")
        current_class = None

        for lineno, line in enumerate(lines, 1):
            # Check for class
            class_match = re.match(class_pattern, line)
            if class_match:
                class_name = class_match.group(1)
                current_class = class_name
                elements.append(CodeElement(
                    name=class_name,
                    element_type="class",
                    file=relative_path,
                    line=lineno,
                    signature=f"class {class_name}",
                    simple_name=class_name,
                ))
                continue

            # Check for end of class (simplified - looks for closing brace at start)
            if current_class and re.match(r"^}", line):
                current_class = None
                continue

            # Check for functions
            for pattern, elem_type in func_patterns:
                match = re.match(pattern, line)
                if match:
                    func_name = match.group(1)
                    elements.append(CodeElement(
                        name=func_name,
                        element_type=elem_type,
                        file=relative_path,
                        line=lineno,
                        signature=f"function {func_name}()",
                        simple_name=func_name,
                    ))
                    break

            # Check for methods if inside a class
            if current_class:
                for pattern, elem_type in method_patterns:
                    match = re.match(pattern, line)
                    if match:
                        method_name = match.group(1)
                        # Skip constructor and common non-method matches
                        if method_name in ("if", "for", "while", "switch", "catch"):
                            continue
                        full_name = f"{current_class}.{method_name}"
                        elements.append(CodeElement(
                            name=full_name,
                            element_type="method",
                            file=relative_path,
                            line=lineno,
                            signature=f"{method_name}()",
                            class_name=current_class,
                            simple_name=method_name,
                        ))
                        break

        return elements

    def generate_anchor_pattern(self, element: CodeElement) -> AnchorPattern:
        """Generate TypeScript-appropriate anchor patterns."""
        if element.element_type == "class":
            return AnchorPattern(
                pattern=f"class {element.simple_name}",
                is_regex=False,
                description=f"Class: {element.simple_name}",
            )

        elif element.element_type == "method":
            # Methods can have various signatures in TS
            # Use regex to match method name followed by (
            pattern = rf"^\s+(?:async\s+)?{re.escape(element.simple_name)}\s*\("
            return AnchorPattern(
                pattern=pattern,
                is_regex=True,
                description=f"Method: {element.class_name}.{element.simple_name}",
            )

        else:  # function
            # Match various function declaration styles
            pattern = rf"(?:function\s+{re.escape(element.simple_name)}|(?:const|let|var)\s+{re.escape(element.simple_name)}\s*=)"
            return AnchorPattern(
                pattern=pattern,
                is_regex=True,
                description=f"Function: {element.simple_name}",
            )


class LanguageRegistry:
    """
    Registry of available language support implementations.

    Use this to get the appropriate language handler for a file.
    """

    def __init__(self):
        self._languages: Dict[str, LanguageSupport] = {}
        self._extension_map: Dict[str, LanguageSupport] = {}

        # Register built-in languages
        self.register(PythonSupport())
        self.register(TypeScriptSupport())

    def register(self, language: LanguageSupport) -> None:
        """Register a language support implementation."""
        self._languages[language.name.lower()] = language
        for ext in language.extensions:
            self._extension_map[ext.lower()] = language

    def get_by_extension(self, file_path: Path) -> Optional[LanguageSupport]:
        """Get language support for a file based on its extension."""
        ext = file_path.suffix.lower()
        return self._extension_map.get(ext)

    def get_by_name(self, name: str) -> Optional[LanguageSupport]:
        """Get language support by language name."""
        return self._languages.get(name.lower())

    def supported_extensions(self) -> List[str]:
        """Get all supported file extensions."""
        return list(self._extension_map.keys())

    def supported_languages(self) -> List[str]:
        """Get all supported language names."""
        return list(self._languages.keys())


# Global registry instance
_registry: Optional[LanguageRegistry] = None


def get_language_registry() -> LanguageRegistry:
    """Get the global language registry."""
    global _registry
    if _registry is None:
        _registry = LanguageRegistry()
    return _registry
