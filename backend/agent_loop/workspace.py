"""
Her workspace and her agenda (phase 3 of docs/design/agent-loop.md, C6, C10).

The workspace is a folder of her own, DATA_DIR/workspace. In a turn she has
five tools on it: read, write, edit, list and search, fenced to the folder.
Her agenda is AGENDA.md there: threads she's in, what's next, what she's
waiting on and from whom (C6). Every turn on the loop carries it as a
context section, and she is the only one who writes it: nothing in the
vessel writes to the workspace except these tools in her turns. When it
doesn't exist yet, the turn says so; nobody starts it for her.

C10 (she's seen in the work): every write and edit goes in a change log
with a diff, so the corrections and changes of course are visible, not only
the latest text. Kohl can read the folder and the log (admin, read-only:
routes/admin/workspace.py).
"""
from __future__ import annotations

import difflib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

AGENDA_FILE = "AGENDA.md"
LOG_FILE = "workspace_log.jsonl"   # beside the folder, not in it

MAX_READ_CHARS = 60_000
# One part of a read: under the loop's cap on a tool result (loop.py,
# MAX_TOOL_RESULT_CHARS = 20,000), which otherwise cut a 43k file at 20k with
# no way on (live, 2026-11-16).
READ_PART_CHARS = 18_000
MAX_WRITE_CHARS = 200_000
MAX_LIST = 300
MAX_HITS = 80
MAX_DIFF_CHARS = 20_000
# A write that would replace a file with under half of it (and the file is more
# than a short note) needs replace: true (2026-11-18: she said "append" and a
# write replaced her 25k agenda with 8k). The replaced version is kept beside the
# workspace, the newest HISTORY_KEEP per file.
SHRINK_GUARD_MIN_CHARS = 2_000
SHRINK_GUARD_RATIO = 0.5
HISTORY_DIR = "workspace_history"
HISTORY_KEEP = 20
AGENDA_CONTEXT_CHARS = 8_000

WORKSPACE_TOOLS: List[Dict[str, Any]] = [
    {"name": "workspace_read",
     "description": ("Read a file in my workspace (a folder of my own). Paths are relative to it. "
                     "A long file comes in parts: the result says where the next part starts "
                     "(from_char)."),
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "from_char": {"type": "integer", "minimum": 0,
                                                   "description": "where to start reading (default 0)"}},
                      "required": ["path"]}},
    {"name": "workspace_write",
     "description": ("Create a file in my workspace, add to the end of one (append: true), or "
                     "replace one. Replacing a file with much less than it has needs replace: true. "
                     "Folders are made as needed; the version a write replaces is kept."),
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"}, "content": {"type": "string"},
                                     "append": {"type": "boolean",
                                                "description": "add content to the end instead of replacing"},
                                     "replace": {"type": "boolean",
                                                 "description": "yes, replace this file even though it shrinks a lot"}},
                      "required": ["path", "content"]}},
    {"name": "workspace_edit",
     "description": ("Replace one exact occurrence of old_text with new_text in a workspace file. "
                     "old_text must appear exactly once; include enough around it to be unique."),
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"}, "old_text": {"type": "string"},
                                     "new_text": {"type": "string"}},
                      "required": ["path", "old_text", "new_text"]}},
    {"name": "workspace_list",
     "description": "List the files in my workspace, or under one folder of it.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "workspace_search",
     "description": "Search my workspace files for a pattern (a regular expression, case-insensitive); returns matching lines.",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
]
WORKSPACE_TOOL_NAMES = tuple(t["name"] for t in WORKSPACE_TOOLS)


def default_root() -> Path:
    from config import DATA_DIR
    return Path(DATA_DIR) / "workspace"


class Workspace:
    def __init__(self, root: Optional[Path] = None, log_path: Optional[Path] = None):
        self.root = Path(root) if root else default_root()
        self.log_path = Path(log_path) if log_path else self.root.parent / "agent_loop" / LOG_FILE

    # ----- fencing --------------------------------------------------------

    def resolve(self, rel: Optional[str]) -> Optional[Path]:
        """The path inside the workspace, or None if it would leave it
        (.., absolute paths elsewhere, symlinks pointing out)."""
        root = self.root.resolve()
        rel = (rel or ".").strip()
        p = Path(rel)
        p = (p if p.is_absolute() else root / p).resolve()
        return p if p == root or root in p.parents else None

    def rel(self, p: Path) -> str:
        return str(p.resolve().relative_to(self.root.resolve()))

    # ----- the agenda -----------------------------------------------------

    def agenda(self) -> Optional[str]:
        p = self.root / AGENDA_FILE
        if not p.is_file():
            return None
        return p.read_text(encoding="utf-8", errors="replace")

    def agenda_section(self) -> str:
        """The agenda as a prompt section, in her first person."""
        text = self.agenda()
        if text is None or not text.strip():
            return ("## MY AGENDA\n\nI don't have an agenda yet. It's mine to start, if I want one: "
                    f"{AGENDA_FILE} in my workspace, for the threads I'm in, what's next, and what "
                    "I'm waiting on and from whom.")
        body = text.strip()
        if len(body) > AGENDA_CONTEXT_CHARS:
            body = body[:AGENDA_CONTEXT_CHARS] + (f"\n\n[... the rest is in {AGENDA_FILE}; "
                                                  "workspace_read shows all of it]")
        return f"## MY AGENDA ({AGENDA_FILE} in my workspace, mine to keep)\n\n{body}"

    # ----- the change log (C10) ------------------------------------------

    def _keep_version(self, path: str, before: str) -> None:
        """The version a write replaces, beside the workspace (not in it)."""
        try:
            folder = self.log_path.parent / HISTORY_DIR / path.replace("/", "__")
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{datetime.now():%Y%m%d-%H%M%S-%f}.txt").write_text(before, encoding="utf-8")
            for old in sorted(folder.iterdir())[:-HISTORY_KEEP]:
                old.unlink()
        except OSError as e:
            logger.warning(f"[workspace] couldn't keep the earlier version of {path}: {e}")

    def _log(self, session_id: str, tool: str, path: str, before: Optional[str], after: str) -> None:
        diff = "".join(difflib.unified_diff((before or "").splitlines(keepends=True),
                                            after.splitlines(keepends=True),
                                            fromfile=f"a/{path}", tofile=f"b/{path}"))
        entry = {"at": datetime.now().isoformat(timespec="seconds"), "session": session_id,
                 "tool": tool, "path": path, "created": before is None,
                 "chars": len(after), "diff": diff[:MAX_DIFF_CHARS]}
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as e:
            logger.warning(f"[workspace] couldn't write the change log: {e}")

    def changes(self, limit: int = 50, path: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.log_path.exists():
            return []
        out = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if path is None or e.get("path") == path:
                out.append(e)
        return out[-limit:]

    # ----- listing (also for the admin view) -----------------------------

    def files(self, under: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        base = self.resolve(under)
        if base is None or not base.exists():
            return None
        items = []
        for p in sorted(base.rglob("*")):
            if p.is_file() and self.resolve(str(p)) is not None:
                st = p.stat()
                items.append({"path": self.rel(p), "chars": st.st_size,
                              "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
        return items

    # ----- the tools ------------------------------------------------------

    def run(self, name: str, a: Dict[str, Any], session_id: str = "") -> Any:
        """Run one workspace tool. Errors come back as {"error": ...}."""
        self.root.mkdir(parents=True, exist_ok=True)
        if name == "workspace_list":
            items = self.files(a.get("path"))
            if items is None:
                return {"error": "No such folder in my workspace."}
            if not items:
                return "My workspace is empty." if not a.get("path") else "That folder is empty."
            lines = [f"{i['path']} ({i['chars']} chars, {i['modified']})" for i in items[:MAX_LIST]]
            if len(items) > MAX_LIST:
                lines.append(f"... and {len(items) - MAX_LIST} more")
            return "\n".join(lines)
        if name == "workspace_search":
            pattern = str(a.get("pattern") or "")
            if not pattern:
                return {"error": "pattern is empty"}
            try:
                rx = re.compile(pattern, re.IGNORECASE)
            except re.error:
                rx = re.compile(re.escape(pattern), re.IGNORECASE)
            hits = []
            for item in self.files() or []:
                p = self.root / item["path"]
                for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{item['path']}:{n}: {line[:200]}")
                        if len(hits) >= MAX_HITS:
                            return "\n".join(hits) + "\n(more matches not shown)"
            return "\n".join(hits) or "No matches."

        p = self.resolve(a.get("path"))
        if p is None or p == self.root.resolve():
            return {"error": "That path is outside my workspace (paths are relative to it)."}
        path = self.rel(p)
        if name == "workspace_read":
            if not p.is_file():
                return {"error": f"No file {path} in my workspace."}
            text = p.read_text(encoding="utf-8", errors="replace")
            start = a.get("from_char") or 0
            if not isinstance(start, int) or start < 0:
                return {"error": "from_char must be a whole number, 0 or more"}
            if start and start >= len(text):
                return {"error": f"{path} has {len(text)} chars; from_char is past the end."}
            end = start + READ_PART_CHARS
            if start == 0 and len(text) <= READ_PART_CHARS:
                return text
            part = text[start:end]
            if end < len(text):
                return part + (f"\n[part: chars {start}-{end} of {len(text)}; "
                               f"the rest starts at from_char={end}]")
            return part + f"\n[part: chars {start}-{len(text)} of {len(text)}; the end]"
        if name == "workspace_write":
            content = a.get("content")
            if not isinstance(content, str):
                return {"error": "content must be text"}
            if len(content) > MAX_WRITE_CHARS:
                return {"error": f"That's over {MAX_WRITE_CHARS} chars; split it into files."}
            if p.is_dir():
                return {"error": f"{path} is a folder."}
            before = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
            if a.get("append") and before is not None:
                sep = "" if not before or before.endswith("\n") else "\n"
                content = before + sep + content
                if len(content) > MAX_WRITE_CHARS:
                    return {"error": f"That would make {path} over {MAX_WRITE_CHARS} chars; start a new file."}
            elif (before is not None and not a.get("replace")
                  and len(before) >= SHRINK_GUARD_MIN_CHARS
                  and len(content) < SHRINK_GUARD_RATIO * len(before)):
                return {"error": (f"That would replace {path} ({len(before)} chars) with {len(content)} "
                                  f"chars. To add to the end, pass append: true. To replace it anyway, "
                                  f"pass replace: true (the old version is kept). To change one part, "
                                  f"use workspace_edit.")}
            if before is not None:
                self._keep_version(path, before)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            self._log(session_id, name, path, before, content)
            if a.get("append") and before is not None:
                return f"Added to the end of {path} (now {len(content)} chars)."
            return f"{'Wrote' if before is None else 'Rewrote'} {path} ({len(content)} chars)."
        if name == "workspace_edit":
            if not p.is_file():
                return {"error": f"No file {path} in my workspace."}
            old, new = a.get("old_text"), a.get("new_text")
            if not isinstance(old, str) or not isinstance(new, str) or not old:
                return {"error": "old_text and new_text must be text, and old_text not empty"}
            text = p.read_text(encoding="utf-8", errors="replace")
            count = text.count(old)
            if count != 1:
                return {"error": f"old_text must appear exactly once in {path} (found {count})."}
            after = text.replace(old, new, 1)
            if len(after) > MAX_WRITE_CHARS:
                return {"error": f"That would make {path} over {MAX_WRITE_CHARS} chars."}
            p.write_text(after, encoding="utf-8")
            self._log(session_id, name, path, text, after)
            return f"Edited {path}."
        return {"error": f"unknown workspace tool {name}"}
