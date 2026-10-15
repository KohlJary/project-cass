"""
Filesystem access policy shared by /files, /git and Cass's read_file /
list_directory tools.

Before this, all three accepted any absolute path the process could reach
(including backend/.env and users/*/auth.json). Now a path must resolve inside
an allowed root, and secret-looking files are refused even inside a root.

Allowed roots:
  - DATA_DIR
  - the Cass repo checkout this backend runs from
  - every project's working_directory (projects table)
  - extra roots from CASS_FILE_ROOTS (os.pathsep-separated), for anything else
"""
import fnmatch
import os
from pathlib import Path
from typing import List, Optional

from config import DATA_DIR

REPO_ROOT = Path(__file__).resolve().parent.parent

# Matched against every path component (case-insensitive). Anything that
# looks like a credential store is off-limits, wherever it lives.
DENIED_NAME_PATTERNS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ed25519*",
    "id_ecdsa*",
    ".secrets",            # DATA_DIR/.secrets (generated JWT secrets)
    "auth.json",           # per-user password hashes
    "daedalus_credentials.json",
    "credentials*.json",
    "*secret*",
    ".netrc",
    ".git-credentials",
    ".ssh",
    ".aws",
    ".gnupg",
)


class PathNotAllowed(Exception):
    """Raised when a path is outside the allowed roots or names a secret."""


def _project_roots() -> List[Path]:
    roots = []
    try:
        from database import get_db
        with get_db() as conn:
            rows = conn.execute(
                "SELECT working_directory FROM projects WHERE working_directory IS NOT NULL"
            ).fetchall()
        for row in rows:
            wd = row[0]
            if wd:
                roots.append(Path(os.path.expanduser(wd)))
    except Exception:
        # No DB yet (early startup) - fall back to the static roots.
        pass
    return roots


def allowed_roots() -> List[Path]:
    roots = [Path(DATA_DIR), REPO_ROOT]
    roots.extend(_project_roots())
    extra = os.getenv("CASS_FILE_ROOTS", "")
    roots.extend(Path(os.path.expanduser(p)) for p in extra.split(os.pathsep) if p.strip())

    resolved = []
    for root in roots:
        try:
            r = root.resolve()
        except Exception:
            continue
        # A root of "/" (or the home dir itself) would allow everything.
        if r == Path(r.anchor) or r == Path.home().resolve():
            continue
        if r not in resolved:
            resolved.append(r)
    return resolved


def is_denied_name(path: Path) -> bool:
    for part in path.parts:
        lower = part.lower()
        for pattern in DENIED_NAME_PATTERNS:
            if fnmatch.fnmatch(lower, pattern):
                return True
    return False


def check_path(path: str, roots: Optional[List[Path]] = None) -> Path:
    """Resolve `path` and verify it is allowed. Returns the resolved Path.

    resolve() follows symlinks, so a link inside a root that points outside
    it is rejected too.
    """
    if not path:
        raise PathNotAllowed("Empty path")
    resolved = Path(os.path.expanduser(path)).resolve()
    roots = roots if roots is not None else allowed_roots()

    root = next((r for r in roots if resolved == r or resolved.is_relative_to(r)), None)
    if root is None:
        raise PathNotAllowed(f"Path is outside the allowed roots: {resolved}")

    # Only check the part below the root, so a root that happens to live
    # under e.g. ~/keys/ is not rejected wholesale.
    if is_denied_name(resolved.relative_to(root)):
        raise PathNotAllowed(f"Access to this file is not allowed: {resolved.name}")
    return resolved
