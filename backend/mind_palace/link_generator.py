"""
Link Generator - Automatically generate cross-palace links from Theseus reports.

Parses API mapping reports and creates Link objects for each cross-palace
connection, storing them in the corresponding source room.

Works with any project structure - discovers sub-palaces dynamically via
PalaceRegistry and finds reports in .mind-palace/theseus/reports/.

Usage:
    from mind_palace.link_generator import update_palace_links

    result = update_palace_links(project_root)
    print(f"Added {result['total_links']} links")
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import Link, LinkType
from .registry import PalaceRegistry, DEFAULT_SUB_PALACES
from .storage import PalaceStorage

logger = logging.getLogger(__name__)


def find_api_mapping_reports(project_root: Path) -> List[Path]:
    """
    Find all API mapping reports in the project.

    Searches for reports in:
    - .mind-palace/theseus/reports/*api*.md
    - {sub-palace}/.mind-palace/theseus/reports/*api*.md

    Returns:
        List of paths to API mapping report files
    """
    reports = []

    # Check root .mind-palace
    root_reports = project_root / ".mind-palace" / "theseus" / "reports"
    if root_reports.exists():
        reports.extend(root_reports.glob("*api*.md"))

    # Check each sub-palace
    for subdir in project_root.iterdir():
        if subdir.is_dir():
            sub_reports = subdir / ".mind-palace" / "theseus" / "reports"
            if sub_reports.exists():
                reports.extend(sub_reports.glob("*api*.md"))

    return sorted(reports)


def get_palaces_with_references(project_root: Path) -> Dict[str, List[str]]:
    """
    Get all palaces that have references to other palaces.

    Uses palace.yaml references (like C# project references) instead of
    language-based detection.

    Returns:
        Dict mapping palace name to list of referenced palace names
    """
    palace_refs: Dict[str, List[str]] = {}

    # Check each subdirectory for a palace with references
    for subdir in project_root.iterdir():
        if not subdir.is_dir():
            continue

        palace_yaml = subdir / ".mind-palace" / "palace.yaml"
        if not palace_yaml.exists():
            continue

        try:
            import yaml
            with open(palace_yaml) as f:
                data = yaml.safe_load(f)

            refs = data.get("references", [])
            if refs:
                palace_refs[subdir.name] = [
                    ref.get("palace") for ref in refs if ref.get("palace")
                ]
        except Exception as e:
            logger.warning(f"Error reading {palace_yaml}: {e}")

    return palace_refs


def parse_api_mapping_report(report_path: Path) -> List[Dict[str, str]]:
    """
    Parse the Theseus API mapping report markdown file.

    Extracts table rows with format:
    | Frontend File | API Call | Backend Route | Handler | Method |

    Args:
        report_path: Path to frontend-api-mapping.md

    Returns:
        List of dicts with keys: frontend_file, api_call, backend_route, handler, method
    """
    if not report_path.exists():
        logger.warning(f"Report not found: {report_path}")
        return []

    content = report_path.read_text()
    mappings = []

    # Match table rows (skip header and separator rows)
    # Format: | Frontend File | API Call | Backend Route | Handler | Method |
    table_row_pattern = re.compile(
        r'^\|\s*([^|]+\.tsx?)\s*\|\s*`?([^|`]+)`?\s*\|\s*`?([^|`]+)`?\s*\|\s*([^|]+)\s*\|\s*(\w+)\s*\|',
        re.MULTILINE
    )

    for match in table_row_pattern.finditer(content):
        frontend_file = match.group(1).strip()
        api_call = match.group(2).strip()
        backend_route = match.group(3).strip()
        handler = match.group(4).strip()
        method = match.group(5).strip()

        mappings.append({
            "frontend_file": frontend_file,
            "api_call": api_call,
            "backend_route": backend_route,
            "handler": handler,
            "method": method,
        })

    logger.info(f"Parsed {len(mappings)} API mappings from {report_path}")
    return mappings


def filename_to_room_slug(filename: str) -> str:
    """
    Convert a frontend filename to a room slug.

    Examples:
        AuthContext.tsx -> authcontext
        UserProfile.tsx -> userprofile
        DataManagement.tsx -> datamanagement
    """
    # Remove extension and convert to lowercase
    stem = Path(filename).stem.lower()
    # Remove common suffixes that don't add meaning
    for suffix in ['context', 'provider']:
        if stem.endswith(suffix) and len(stem) > len(suffix):
            stem = stem[:-len(suffix)]
    return stem


def route_to_room_path(route: str, handler: str) -> str:
    """
    Convert a backend route and handler to a room path.

    Examples:
        /admin/auth/register, auth.py -> routes/admin/auth
        /admin/users/{id}, auth.py -> routes/admin/auth
        /cass/self-model, main_sdk.py -> main-sdk
    """
    # Clean up handler name
    handler_stem = Path(handler).stem.replace('_', '-')

    # Parse route parts
    parts = [p for p in route.strip('/').split('/') if p and not p.startswith('{')]

    if parts and parts[0] == 'admin':
        # Admin routes -> routes/admin/{handler}
        return f"routes/admin/{handler_stem}"
    elif parts and parts[0] == 'cass':
        # Cass routes -> handled in main_sdk
        return handler_stem
    else:
        # Other routes
        return handler_stem


def determine_link_type(api_call: str, backend_route: str) -> LinkType:
    """Determine the appropriate link type based on the API call."""
    api_call_lower = api_call.lower()
    route_lower = backend_route.lower()

    if 'websocket' in api_call_lower or 'ws' in route_lower:
        return LinkType.WEBSOCKET
    elif 'graphql' in api_call_lower or 'graphql' in route_lower:
        return LinkType.GRAPHQL
    else:
        return LinkType.API_CALL


def generate_links_from_mappings(
    mappings: List[Dict[str, str]],
    source_palace: str,
    target_palace: str,
) -> Dict[str, List[Link]]:
    """
    Generate Link objects grouped by room for a specific palace pair.

    Args:
        mappings: List of parsed API mappings
        source_palace: Name of source palace (from palace.yaml references)
        target_palace: Name of target palace (from palace.yaml references)

    Returns:
        Dict: {room_slug: [Link, ...]}
    """
    room_links: Dict[str, List[Link]] = {}

    for mapping in mappings:
        frontend_file = mapping["frontend_file"]
        api_call = mapping["api_call"]
        backend_route = mapping["backend_route"]
        handler = mapping["handler"]
        method = mapping["method"]

        # Determine source room from filename
        room_slug = filename_to_room_slug(frontend_file)

        # Determine target path
        to_path = route_to_room_path(backend_route, handler)

        # Create link
        link = Link(
            from_room=room_slug,
            to_palace=target_palace,
            to_path=to_path,
            link_type=determine_link_type(api_call, backend_route),
            metadata={
                "method": method,
                "endpoint": backend_route,
                "api_call": api_call,
                "handler": handler,
                "source_file": frontend_file,
            }
        )

        if room_slug not in room_links:
            room_links[room_slug] = []

        # Avoid duplicates (same endpoint can be called multiple times)
        existing_endpoints = {l.metadata.get("endpoint") for l in room_links[room_slug]}
        if backend_route not in existing_endpoints:
            room_links[room_slug].append(link)

    return room_links


def update_palace_links(
    project_root: Path,
    report_path: Optional[Path] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Main entry point: Parse Theseus reports and update room links.

    Uses palace.yaml references (like C# project references) to determine
    which palaces connect to which others. Completely language-agnostic.

    Args:
        project_root: Root of the project
        report_path: Specific report path (default: auto-discover)
        dry_run: If True, don't save changes

    Returns:
        Summary dict with stats
    """
    project_root = Path(project_root)

    # Find palaces that have references to other palaces
    palace_refs = get_palaces_with_references(project_root)
    if not palace_refs:
        return {"success": False, "error": "No palaces with references found"}

    # Find reports
    if report_path:
        reports = [Path(report_path)]
    else:
        reports = find_api_mapping_reports(project_root)

    if not reports:
        return {"success": False, "error": "No API mapping reports found"}

    # Parse all reports
    all_mappings = []
    for report in reports:
        mappings = parse_api_mapping_report(report)
        all_mappings.extend(mappings)
        logger.info(f"Parsed {len(mappings)} mappings from {report.name}")

    if not all_mappings:
        return {"success": False, "error": "No mappings found in reports"}

    result = {
        "success": True,
        "reports_parsed": len(reports),
        "mappings_parsed": len(all_mappings),
        "palaces_with_refs": list(palace_refs.keys()),
        "by_palace": {},
    }

    total_links = 0
    total_rooms = 0

    # Process each palace that has references
    for source_palace, target_palaces in palace_refs.items():
        palace_path = project_root / source_palace
        if not palace_path.exists():
            logger.warning(f"Palace directory not found: {palace_path}")
            continue

        storage = PalaceStorage(palace_path)
        if not storage.exists():
            logger.warning(f"No palace initialized at {palace_path}")
            continue

        # Generate links for each target palace this source references
        all_palace_links = []
        rooms_with_links = set()

        for target_palace in target_palaces:
            room_links = generate_links_from_mappings(
                all_mappings, source_palace, target_palace
            )
            for room_slug, links in room_links.items():
                all_palace_links.extend(links)
                rooms_with_links.add(room_slug)

        if not all_palace_links:
            continue

        if dry_run:
            result["by_palace"][source_palace] = {
                "would_add": len(all_palace_links),
                "rooms": len(rooms_with_links),
                "targets": target_palaces,
            }
        else:
            # Update the links index
            added = storage.add_links(all_palace_links)
            result["by_palace"][source_palace] = {
                "links_added": added,
                "total_links": len(all_palace_links),
                "rooms": len(rooms_with_links),
                "targets": target_palaces,
            }
            logger.info(
                f"Updated {source_palace}: added {added} new links "
                f"across {len(rooms_with_links)} rooms -> {target_palaces}"
            )

        total_links += len(all_palace_links)
        total_rooms += len(rooms_with_links)

    result["total_links"] = total_links
    result["rooms_with_links"] = total_rooms

    if dry_run:
        result["dry_run"] = True
        logger.info(f"Dry run: would add {total_links} links to {total_rooms} rooms")

    return result


def rebuild_links_index(storage: PalaceStorage, palace) -> int:
    """
    Rebuild links.yaml from all room links.

    Args:
        storage: PalaceStorage instance
        palace: Palace instance with rooms

    Returns:
        Number of links in rebuilt index
    """
    all_links = []

    for room in palace.rooms.values():
        if room.links:
            # Add from_room to each link for the index
            for link in room.links:
                # Ensure from_room is set
                if not link.from_room:
                    link.from_room = room.slug
                all_links.append(link)

    if all_links:
        storage.save_links(all_links)

    return len(all_links)
