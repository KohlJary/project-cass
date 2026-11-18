"""
code_search: Cass searches her own code (her ask "Code search capability for
self-understanding", 2026-11-18).

Read-only, grep-like, over the repository's tracked files at HEAD: the same
`git archive` snapshot ask_daedalus reads (daedalus_bridge.snapshot), so her
data, .env and keys are never in scope. Returns paths (relative to the repo),
line numbers and a little context, and says how to read a whole file.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

MAX_HITS = 60
MAX_LINE_CHARS = 240
MAX_FILE_BYTES = 1_000_000
MAX_CONTEXT = 3
TEXT_SUFFIXES = {".py", ".md", ".json", ".txt", ".toml", ".yaml", ".yml", ".ts", ".tsx", ".js",
                 ".jsx", ".gd", ".sh", ".cfg", ".ini", ".html", ".css", ".sql", ".template", ""}

TOOL = {
    "name": "code_search",
    "description": (
        "Search my own code: every tracked file of the vessel at its current commit (not my data, "
        "and never secrets). Like grep: a pattern (a regular expression, or plain text), optionally a "
        "folder (e.g. backend/thymos) and a file glob (e.g. *.py). Gives each match's path, line number "
        "and the lines around it, and how to read the whole file with read_file."),
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "What to look for (case-insensitive)"},
            "path": {"type": "string", "description": "A folder or file to search in, relative to the repo"},
            "glob": {"type": "string", "description": "Only files whose name matches, e.g. *.py"},
            "context": {"type": "integer", "minimum": 0, "maximum": MAX_CONTEXT,
                        "description": "Lines around each match (default 1)"},
        },
        "required": ["pattern"],
    },
}


def _repo_root() -> Path:
    from daedalus_bridge import REPO
    return REPO


def search(pattern: str, path: Optional[str] = None, glob: Optional[str] = None,
           context: Any = 1, root: Optional[Path] = None) -> Dict[str, Any]:
    pattern = (pattern or "").strip()
    if not pattern:
        return {"error": "code_search needs a pattern"}
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error:
        rx = re.compile(re.escape(pattern), re.IGNORECASE)
    try:
        context = max(0, min(MAX_CONTEXT, int(context if context is not None else 1)))
    except (TypeError, ValueError):
        context = 1
    if root is None:
        from daedalus_bridge import snapshot
        root = snapshot()
    from daedalus_bridge import outside
    base = root
    if path:
        if outside(root, path.strip("/")):
            return {"error": "That path is outside my code."}
        base = (root / path.strip("/")).resolve()
        if not base.exists():
            return {"error": f"No {path} in my code."}
    files = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
    hits: List[str] = []
    matched_files = 0
    for f in files:
        rel = str(f.relative_to(root))
        if rel == ".snapshot-complete" or (glob and not fnmatch.fnmatch(f.name, glob)):
            continue
        if f.suffix.lower() not in TEXT_SUFFIXES or f.stat().st_size > MAX_FILE_BYTES:
            continue
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        found = [n for n, line in enumerate(lines) if rx.search(line)]
        if not found:
            continue
        matched_files += 1
        shown = set()
        for n in found:
            if len(hits) >= MAX_HITS:
                break
            block = []
            for k in range(max(0, n - context), min(len(lines), n + context + 1)):
                if k in shown:
                    continue
                shown.add(k)
                mark = ":" if k == n else "-"
                block.append(f"{rel}{mark}{k + 1}{mark} {lines[k][:MAX_LINE_CHARS]}")
            hits.append("\n".join(block))
        if len(hits) >= MAX_HITS:
            break
    if not hits:
        return {"matches": 0, "text": "No matches."}
    more = len(hits) >= MAX_HITS
    return {
        "matches": len(hits), "files": matched_files,
        "text": "\n--\n".join(hits) + ("\n(more matches not shown; narrow it with path or glob)" if more else ""),
        "read_a_file": f"read_file with file_path {_repo_root()}/<path>",
    }


async def execute(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    import asyncio
    try:
        out = await asyncio.to_thread(search, tool_input.get("pattern", ""), tool_input.get("path"),
                                      tool_input.get("glob"), tool_input.get("context", 1))
    except Exception as e:
        return {"success": False, "error": f"code_search failed: {type(e).__name__}: {e}"}
    if out.get("error"):
        return {"success": False, "error": out["error"]}
    return {"success": True, **out}
