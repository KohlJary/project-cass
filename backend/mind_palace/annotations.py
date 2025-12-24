"""
Inline Annotation System for Mind Palace.

Phase 4: Bidirectional sync between code comments and palace structure.

Annotation syntax:
  # MAP:ROOM room_name - Marks function/class as a named room
  # MAP:HAZARD description - Documents an invariant or edge case
  # MAP:EXIT:DIRECTION target - Documents a call relationship
  # MAP:ENTITY entity_name - Associates code with an entity

Example:
  def spawn_daemon(config: DaemonConfig) -> Daemon:
      # MAP:ROOM spawn_daemon
      # MAP:HAZARD vows must be validated before context initialization

      validated = validate_vows(config.vows)  # MAP:EXIT:NORTH validate_vows
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class MapAnnotation:
    """A MAP: annotation found in code."""
    type: str  # ROOM, HAZARD, EXIT, ENTITY
    value: str  # The annotation content
    file: str  # Relative file path
    line: int  # Line number (1-indexed)
    # For EXIT annotations
    direction: Optional[str] = None
    # The code context (function/class name if determinable)
    context: Optional[str] = None


@dataclass
class AnnotatedFile:
    """All annotations found in a single file."""
    file: str
    annotations: List[MapAnnotation] = field(default_factory=list)
    # Room annotations grouped by name
    rooms: Dict[str, List[MapAnnotation]] = field(default_factory=dict)


# Regex patterns for annotation types
ANNOTATION_PATTERNS = {
    # Syntax: MAP:ROOM room_name
    "room": re.compile(r"#\s*MAP:ROOM\s+(\S+)"),
    # Syntax: MAP:HAZARD description
    "hazard": re.compile(r"#\s*MAP:HAZARD\s+(.+)$"),
    # Syntax: MAP:EXIT:DIRECTION target
    "exit": re.compile(r"#\s*MAP:EXIT:(\w+)\s+(\S+)"),
    # Syntax: MAP:ENTITY entity_name
    "entity": re.compile(r"#\s*MAP:ENTITY\s+(\S+)"),
    # Syntax: MAP:WHY explanation (for documenting design decisions)
    "why": re.compile(r"#\s*MAP:WHY\s+(.+)$"),
    # Syntax: MAP:CONTAINS name: type
    "contains": re.compile(r"#\s*MAP:CONTAINS\s+(.+)$"),
}


def parse_annotations(content: str, file_path: str) -> AnnotatedFile:
    """
    Parse all MAP: annotations from file content.

    Args:
        content: The file content to parse
        file_path: Relative path for reference

    Returns:
        AnnotatedFile with all discovered annotations
    """
    result = AnnotatedFile(file=file_path)
    current_context = None
    in_docstring = False
    docstring_delim = None

    lines = content.split("\n")

    for lineno, line in enumerate(lines, 1):
        # Track docstring state (skip annotations inside docstrings)
        stripped = line.strip()
        if not in_docstring:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                docstring_delim = stripped[:3]
                # Check if docstring closes on same line
                if stripped.count(docstring_delim) >= 2:
                    pass  # Single-line docstring
                else:
                    in_docstring = True
                continue
        else:
            if docstring_delim in stripped:
                in_docstring = False
                docstring_delim = None
            continue
        # Track context (class/function definitions)
        # Simple heuristic - look for def/class at start of line
        if re.match(r"^(?:async\s+)?def\s+(\w+)", line):
            match = re.match(r"^(?:async\s+)?def\s+(\w+)", line)
            if match:
                current_context = match.group(1)
        elif re.match(r"^class\s+(\w+)", line):
            match = re.match(r"^class\s+(\w+)", line)
            if match:
                current_context = match.group(1)

        # Check for MAP: annotations
        if "MAP:" not in line:
            continue

        # Skip template examples (contain {})
        if "{" in line and "}" in line:
            continue

        # Try each pattern
        for ann_type, pattern in ANNOTATION_PATTERNS.items():
            match = pattern.search(line)
            if match:
                if ann_type == "room":
                    ann = MapAnnotation(
                        type="ROOM",
                        value=match.group(1),
                        file=file_path,
                        line=lineno,
                        context=current_context,
                    )
                elif ann_type == "hazard":
                    ann = MapAnnotation(
                        type="HAZARD",
                        value=match.group(1).strip(),
                        file=file_path,
                        line=lineno,
                        context=current_context,
                    )
                elif ann_type == "exit":
                    ann = MapAnnotation(
                        type="EXIT",
                        value=match.group(2),
                        direction=match.group(1).upper(),
                        file=file_path,
                        line=lineno,
                        context=current_context,
                    )
                elif ann_type == "entity":
                    ann = MapAnnotation(
                        type="ENTITY",
                        value=match.group(1),
                        file=file_path,
                        line=lineno,
                        context=current_context,
                    )
                elif ann_type == "why":
                    ann = MapAnnotation(
                        type="WHY",
                        value=match.group(1).strip(),
                        file=file_path,
                        line=lineno,
                        context=current_context,
                    )
                elif ann_type == "contains":
                    ann = MapAnnotation(
                        type="CONTAINS",
                        value=match.group(1).strip(),
                        file=file_path,
                        line=lineno,
                        context=current_context,
                    )
                else:
                    continue

                result.annotations.append(ann)

                # Group ROOM annotations
                if ann.type == "ROOM":
                    if ann.value not in result.rooms:
                        result.rooms[ann.value] = []
                    result.rooms[ann.value].append(ann)

                break  # Only match one pattern per line

    return result


def scan_directory(
    directory: Path,
    project_root: Path,
    extensions: List[str] = None,
) -> Dict[str, AnnotatedFile]:
    """
    Scan a directory for MAP: annotations in all supported files.

    Args:
        directory: Directory to scan
        project_root: Project root for relative paths
        extensions: File extensions to scan (default: .py)

    Returns:
        Dict mapping relative file paths to their annotations
    """
    if extensions is None:
        extensions = [".py"]

    results = {}

    for ext in extensions:
        for file_path in directory.rglob(f"*{ext}"):
            # Skip common non-code directories
            if any(part.startswith(".") or part in ("__pycache__", "node_modules", "venv")
                   for part in file_path.parts):
                continue

            try:
                content = file_path.read_text()
                relative = str(file_path.relative_to(project_root))

                annotated = parse_annotations(content, relative)

                # Only include files with annotations
                if annotated.annotations:
                    results[relative] = annotated

            except Exception as e:
                logger.warning(f"Failed to parse {file_path}: {e}")

    return results


@dataclass
class SyncReport:
    """Report of annotation-to-palace synchronization."""
    # Annotations in code but not in palace
    missing_in_palace: List[MapAnnotation] = field(default_factory=list)
    # Rooms in palace but missing code annotations
    missing_in_code: List[str] = field(default_factory=list)
    # Matched annotations
    matched: List[Tuple[MapAnnotation, str]] = field(default_factory=list)
    # Total counts
    total_annotations: int = 0
    total_rooms: int = 0


def sync_with_palace(
    annotations: Dict[str, AnnotatedFile],
    palace: "Palace",
) -> SyncReport:
    """
    Compare annotations with palace structure.

    Args:
        annotations: Annotations from scan_directory
        palace: The Mind Palace to compare against

    Returns:
        SyncReport detailing matches and discrepancies
    """
    report = SyncReport()

    # Collect all ROOM annotations
    code_rooms = {}  # room_name -> annotation
    all_annotations = []

    for file_path, annotated in annotations.items():
        all_annotations.extend(annotated.annotations)
        for room_name, anns in annotated.rooms.items():
            code_rooms[room_name] = anns[0]  # Take first if multiple

    report.total_annotations = len(all_annotations)
    report.total_rooms = len(palace.rooms)

    # Check which code rooms are in palace
    for room_name, ann in code_rooms.items():
        if room_name in palace.rooms:
            report.matched.append((ann, room_name))
        else:
            report.missing_in_palace.append(ann)

    # Check which palace rooms have code annotations
    for palace_room in palace.rooms:
        if palace_room not in code_rooms:
            report.missing_in_code.append(palace_room)

    return report


def generate_annotation_stub(room_name: str, hazards: List[str] = None) -> str:
    """
    Generate annotation comment stub for a room.

    Useful for adding annotations to existing code.
    """
    lines = [f"# MAP:ROOM {room_name}"]
    if hazards:
        for hazard in hazards:
            lines.append(f"# MAP:HAZARD {hazard}")
    return "\n".join(lines)
