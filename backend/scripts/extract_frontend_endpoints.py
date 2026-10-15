#!/usr/bin/env python3
"""
Extract the HTTP endpoints each frontend calls, for the frontend-drift smoke test.

Scans admin-frontend, mobile-frontend, tui-frontend and godot-frontend sources
for literal API calls and writes them to a JSON fixture that is committed:

    python scripts/extract_frontend_endpoints.py           # rewrite the fixture
    python scripts/extract_frontend_endpoints.py --check   # exit 1 if it's stale

tests/smoke/test_frontend_endpoints.py then asserts every (method, path) in the
fixture exists in the app's route table. Re-run this script whenever a
frontend's API calls change; the test also fails if the fixture is stale.

What it understands (deliberately simple; it reads literals, not types):
  admin/mobile (TS):  api.get('/x'), api.post(`/x/${id}`), fetch(`${API_BASE}/x`, {method}),
                      this.fetch('/x', {method})
  tui (Python):       client.get("/x"), http_client.post(f"/x/{id}")
  godot (C#):         GetAsync("/x"), PostAsync("/x", ...)
Path parameters become {param}; query strings are dropped. WebSocket URLs are
not HTTP routes and are skipped.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "backend" / "tests" / "smoke" / "fixtures" / "frontend_endpoints.json"

FRONTENDS = {
    "admin-frontend": {"root": "admin-frontend/src", "exts": (".ts", ".tsx")},
    "mobile-frontend": {"root": "mobile-frontend/src", "exts": (".ts", ".tsx")},
    "tui-frontend": {"root": "tui-frontend", "exts": (".py",)},
    "godot-frontend": {"root": "godot-frontend/scripts", "exts": (".cs",)},
}

SKIP_DIRS = {"node_modules", "dist", "build", ".expo", "__pycache__", ".godot"}

STRING = r"""(?P<q>['"`])(?P<path>/[^'"`]*)(?P=q)"""

# api.get('/x'  |  api.post(\n  `/x`  (axios instance named `api` in admin)
TS_AXIOS = re.compile(r"\bapi\.(?P<verb>get|post|put|patch|delete)\s*(?:<[^>]*>)?\(\s*" + STRING)
# fetch(`${API_BASE}/x`, { method: 'POST' })  (admin hooks)
TS_FETCH_BASE = re.compile(r"\bfetch\(\s*`\$\{API_BASE\}(?P<path>/[^`]*)`")
# this.fetch('/x', { method: 'POST' })  (mobile api client)
TS_THIS_FETCH = re.compile(r"\bthis\.fetch\s*(?:<[^()]*?>)?\(\s*" + STRING)
# client.get("/x")  /  http_client.post(f"/x/{id}")  (tui, httpx)
PY_HTTPX = re.compile(r"\.(?P<verb>get|post|put|patch|delete)\(\s*f?" + r"""(?P<q>['"])(?P<path>/[^'"]*)(?P=q)""")
# _httpClient.GetAsync("/x")  (godot)
CS_HTTP = re.compile(r"\b(?P<verb>Get|Post|Put|Patch|Delete)Async\(\s*\"(?P<path>/[^\"]*)\"")

METHOD_OPTION = re.compile(r"""method:\s*['"](?P<m>[A-Za-z]+)['"]""")


def normalize(path: str) -> str | None:
    """Turn a literal call path into a route-shaped path, or None to skip it."""
    path = path.split("?", 1)[0]
    # ${expr} or {expr} filling a whole segment is a path parameter.
    path = re.sub(r"/\$\{[^}]*\}", "/{param}", path)
    path = re.sub(r"/\{[^}]*\}", "/{param}", path)
    # Anything else interpolated mid-segment is a query string or suffix: drop it.
    path = re.sub(r"\$\{.*$", "", path)
    path = re.sub(r"(?<!/)\{(?!param\}).*$", "", path)
    path = path.rstrip("/") or "/"
    if not path.startswith("/") or path.startswith("//"):
        return None
    if re.search(r"\.(css|png|svg|jpg|ico|js|json|html)$", path):
        return None
    return path


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _method_after(text: str, start: int, default: str) -> str:
    """Look for `method: 'X'` in the options object of the fetch call at `start`.

    Scans forward to the call's closing paren (tracking nesting) so the
    method of the *next* call is never picked up.
    """
    depth = 1
    end = start
    while end < len(text) and depth:
        ch = text[end]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        end += 1
    match = METHOD_OPTION.search(text[start:end])
    return match.group("m").upper() if match else default


def extract_file(path: Path, rel: str):
    text = path.read_text(errors="ignore")
    found = []

    def add(method, raw_path, index):
        norm = normalize(raw_path)
        if norm:
            found.append((method.upper(), norm, f"{rel}:{_line_of(text, index)}"))

    if path.suffix in (".ts", ".tsx"):
        for m in TS_AXIOS.finditer(text):
            add(m.group("verb"), m.group("path"), m.start())
        for m in TS_FETCH_BASE.finditer(text):
            add(_method_after(text, m.end(), "GET"), m.group("path"), m.start())
        for m in TS_THIS_FETCH.finditer(text):
            add(_method_after(text, m.end(), "GET"), m.group("path"), m.start())
    elif path.suffix == ".py":
        for m in PY_HTTPX.finditer(text):
            add(m.group("verb"), m.group("path"), m.start())
    elif path.suffix == ".cs":
        for m in CS_HTTP.finditer(text):
            add(m.group("verb"), m.group("path"), m.start())
    return found


def extract(repo_root: Path = REPO_ROOT) -> list[dict]:
    endpoints: dict[tuple, dict] = {}
    for frontend, spec in FRONTENDS.items():
        root = repo_root / spec["root"]
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in spec["exts"]:
                continue
            if SKIP_DIRS & set(path.relative_to(repo_root).parts):
                continue
            rel = str(path.relative_to(repo_root))
            for method, norm, where in extract_file(path, rel):
                key = (frontend, method, norm)
                entry = endpoints.setdefault(key, {
                    "frontend": frontend, "method": method, "path": norm, "sources": []})
                entry["sources"].append(where)
    return sorted(endpoints.values(), key=lambda e: (e["frontend"], e["path"], e["method"]))


def render(endpoints: list[dict]) -> str:
    return json.dumps({
        "_comment": "Generated by backend/scripts/extract_frontend_endpoints.py - do not edit by hand.",
        "endpoints": endpoints,
    }, indent=2) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if the fixture is out of date")
    args = parser.parse_args(argv)

    content = render(extract())
    if args.check:
        current = FIXTURE.read_text() if FIXTURE.exists() else ""
        if current != content:
            print(f"{FIXTURE} is stale; run scripts/extract_frontend_endpoints.py", file=sys.stderr)
            return 1
        print("frontend endpoint fixture is up to date")
        return 0

    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(content)
    counts = {}
    for e in json.loads(content)["endpoints"]:
        counts[e["frontend"]] = counts.get(e["frontend"], 0) + 1
    print(f"wrote {FIXTURE.relative_to(REPO_ROOT)}: " +
          ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
