#!/usr/bin/env python3
"""
Generate docs/tier1-status.md: benchmark Tier 1, "does every subsystem run?"
(epic #65, docs/ROADMAP-STABILIZATION.md).

It joins three things:
  - the lever registry (features.LEVERS): every subsystem's on/off switch;
  - the map from levers to smoke tests (tests/smoke/tier1_map.py);
  - one run of the smoke batteries against the fake LLM (pytest junit XML).

and writes one row per lever: default, which smoke tests cover it and how
deeply, their pass/fail/xfail/skip counts, and an UNCOVERED flag for levers
with no smoke test.

Usage (from backend/):
  python scripts/tier1_status.py                    # run tests/smoke, write the page
  python scripts/tier1_status.py --junit out.xml    # use an existing junit file instead
  python scripts/tier1_status.py --check-map        # only validate the map (no tests run)

The map is validated first; if a lever or smoke test is unclassified, the
script exits 1 without writing. Test failures do not make it exit non-zero:
they are what the page reports.
"""
from __future__ import annotations

import argparse
import ast
import os
import platform
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
SMOKE_DIR = BACKEND / "tests" / "smoke"
DEFAULT_OUTPUT = REPO / "docs" / "tier1-status.md"
PYTEST_MARKERS = "not slow and not tts"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

OUTCOMES = ("pass", "fail", "xfail", "skip")


# ---------------------------------------------------------------------------
# The map
# ---------------------------------------------------------------------------

def _load():
    import features
    from tests.smoke import tier1_map
    return features, tier1_map


def _is_fixture(node) -> bool:
    """`test_db` and friends are fixtures named like tests; pytest doesn't collect them."""
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if "fixture" in ast.unparse(target):
            return True
    return False


def smoke_test_units() -> dict:
    """{'tests/smoke/test_x.py': ['test_a', 'TestB', ...]} from the source, statically."""
    units = {}
    for path in sorted(SMOKE_DIR.glob("test_*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        names = []
        for node in tree.body:
            if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
                    and not _is_fixture(node)):
                names.append(node.name)
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                names.append(node.name)
        units[path.relative_to(BACKEND).as_posix()] = names
    return units


def _class_methods(rel_path: str, class_name: str) -> list:
    tree = ast.parse((BACKEND / rel_path).read_text())
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [n.name for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")]
    return []


def matches(nodeid: str, entry: str) -> bool:
    """Does a pytest node id fall under a map entry (file, file::test, file::Class[::test])?"""
    if nodeid == entry:
        return True
    return nodeid.startswith(entry + "::") or nodeid.startswith(entry + "[")


def all_entries(tier1_map) -> list:
    entries = [e for cov in tier1_map.LEVER_COVERAGE.values() for e in cov["tests"]]
    entries += [e for group in tier1_map.SPINE.values() for e in group]
    return entries


def validate_map(units: dict | None = None) -> list:
    """Every problem with the map, as strings. Empty means it's complete.

    `units` stands in for smoke_test_units() (tests use it to simulate a new
    smoke test without writing a file).
    """
    features, tier1_map = _load()
    errors = []
    coverage = tier1_map.LEVER_COVERAGE

    for name in features.LEVERS:
        if name not in coverage:
            errors.append(f"lever {name!r} has no entry in tests/smoke/tier1_map.py "
                          "(new subsystem = new lever + smoke test; add its tests, or "
                          "an entry with depth 'none' if it has none yet)")
    for name in coverage:
        if name not in features.LEVERS:
            errors.append(f"tier1_map entry {name!r} is not a lever in features.LEVERS")

    for name, cov in coverage.items():
        if set(cov) != {"depth", "tests", "note"}:
            errors.append(f"{name}: entry needs exactly the keys depth, tests, note")
            continue
        if cov["depth"] not in tier1_map.DEPTHS:
            errors.append(f"{name}: depth {cov['depth']!r} not one of {tier1_map.DEPTHS}")
        if cov["depth"] == "none" and cov["tests"]:
            errors.append(f"{name}: depth 'none' but tests are listed")
        if cov["depth"] != "none" and not cov["tests"]:
            errors.append(f"{name}: depth {cov['depth']!r} but no tests are listed")
        if cov["depth"] in ("partial", "gate") and not cov["note"]:
            errors.append(f"{name}: depth {cov['depth']!r} needs a note saying what isn't run")
        for entry in cov["tests"]:
            # Lever entries name single tests, so a test added to the file
            # later is unclassified (and fails) until someone maps it.
            _, _, rest = entry.partition("::")
            head = rest.partition("::")[0]
            if not rest or (head.startswith("Test") and "::" not in rest):
                errors.append(f"{name}: {entry!r}: lever entries must name a single test, "
                              "not a whole file or class")

    units = smoke_test_units() if units is None else units
    entries = all_entries(tier1_map)
    for entry in entries:
        rel, _, rest = entry.partition("::")
        if rel not in units:
            errors.append(f"tier1_map: {entry!r}: no such smoke test file")
            continue
        if rest:
            head, _, method = rest.partition("::")
            if head not in units[rel]:
                errors.append(f"tier1_map: {entry!r}: no test {head!r} in {rel}")
            elif method and method not in _class_methods(rel, head):
                errors.append(f"tier1_map: {entry!r}: no test {method!r} in {head}")

    for rel, names in units.items():
        for name in names:
            nodeid = f"{rel}::{name}"
            covered = any(matches(nodeid, e) for e in entries)
            # A class is classified if all its methods are.
            if not covered and name.startswith("Test"):
                methods = _class_methods(rel, name)
                covered = bool(methods) and all(
                    any(matches(f"{nodeid}::{m}", e) for e in entries) for m in methods)
            if not covered:
                errors.append(f"smoke test {nodeid} is not in tests/smoke/tier1_map.py "
                              "(list it under its lever, or under SPINE)")
    return errors


# ---------------------------------------------------------------------------
# Test results
# ---------------------------------------------------------------------------

def run_smoke(junit_path: Path) -> int:
    cmd = [sys.executable, "-m", "pytest", "tests/smoke", "-m", PYTEST_MARKERS,
           "-q", "-p", "no:cacheprovider", f"--junitxml={junit_path}"]
    print("running:", " ".join(cmd), file=sys.stderr)
    return subprocess.run(cmd, cwd=BACKEND).returncode


def _nodeid(classname: str, name: str) -> str:
    """Rebuild a pytest node id from junit's dotted classname + test name."""
    parts = classname.split(".") if classname else []
    for i in range(len(parts), 0, -1):
        rel = "/".join(parts[:i]) + ".py"
        if (BACKEND / rel).is_file():
            return "::".join([rel, *parts[i:], name])
    # Collection-level entries (a module skipped or failing to import).
    rel = name.replace(".", "/") + ".py"
    if (BACKEND / rel).is_file():
        return rel
    return "::".join([*parts, name])


def read_junit(path: Path) -> dict:
    """{nodeid: outcome} for tests under tests/smoke/."""
    results = {}
    root = ET.parse(path).getroot()
    for case in root.iter("testcase"):
        nodeid = _nodeid(case.get("classname", ""), case.get("name", ""))
        if not nodeid.startswith("tests/smoke/"):
            continue
        outcome = "pass"
        for child in case:
            if child.tag in ("failure", "error"):
                outcome = "fail"
                break
            if child.tag == "skipped":
                outcome = "xfail" if child.get("type") == "pytest.xfail" else "skip"
        # A teardown error is reported as a second testcase with the same id;
        # keep the worst outcome.
        if results.get(nodeid) != "fail":
            results[nodeid] = outcome
    return results


def tally(results: dict, entries: list) -> Counter:
    counts = Counter()
    for nodeid, outcome in results.items():
        if any(matches(nodeid, e) for e in entries):
            counts[outcome] += 1
    return counts


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

def _short(entry: str) -> str:
    return entry.removeprefix("tests/smoke/")


def _counts_cells(c: Counter) -> str:
    return " | ".join(str(c.get(k, 0)) for k in OUTCOMES)


def _git_head() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


DEPTH_LABEL = {"runs": "runs", "partial": "partial", "gate": "gate only", "none": "**UNCOVERED**"}


def render(results: dict, source: str) -> str:
    features, tier1_map = _load()
    coverage = tier1_map.LEVER_COVERAGE
    totals = Counter(results.values())
    depths = Counter(coverage[name]["depth"] for name in features.LEVERS)

    lines = [
        "# Tier 1 status: does every subsystem run?",
        "",
        "<!-- Generated by backend/scripts/tier1_status.py. Do not edit by hand. -->",
        "",
        "Generated by `backend/scripts/tier1_status.py` from the lever registry "
        "(`backend/features.py`), the lever-to-test map (`backend/tests/smoke/tier1_map.py`) "
        "and one run of the smoke batteries against the fake LLM. Part of the benchmark "
        "suite (#65, `docs/ROADMAP-STABILIZATION.md`). Tier 1 checks the machinery only; "
        "it makes no claim about how well any of it works with a real model.",
        "",
        f"- Commit: `{_git_head()}`; generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC; "
        f"Python {platform.python_version()}",
        f"- Results from: {source}",
        f"- Smoke tests: {sum(totals.values())} "
        f"({totals['pass']} pass, {totals['fail']} fail, {totals['xfail']} xfail, {totals['skip']} skip)",
        f"- Levers: {len(features.LEVERS)} "
        f"({depths['runs']} run in smoke, {depths['partial']} partial, "
        f"{depths['gate']} gate only, {depths['none']} uncovered)",
        "",
        "CI regenerates this page on every PR (the `full` job) and uploads it as the "
        "`tier1-status` artifact; this committed copy is a snapshot. xfail = a known bug "
        "pinned by a strict xfail test (see `backend/tests/README.md`).",
        "",
    ]
    if results and totals["skip"] == sum(totals.values()):
        lines += ["> **Every smoke test was skipped in this run** (runtime dependencies "
                  "missing?). The counts below say nothing about whether anything runs.", ""]

    lines += [
        "## Coverage key",
        "",
        "- **runs**: the subsystem's own work runs against the fake LLM and the test checks the result.",
        "- **partial**: some of it runs, but not the part the lever starts (a loop, a connection). The note says which.",
        "- **gate only**: the tests reach the entry point (or only check the lever gates it), but the work doesn't run: it is faked, or returns early on the test setup.",
        "- **UNCOVERED**: no smoke test. The rule is new subsystem = new lever + smoke test.",
        "",
        "## Levers",
        "",
        "| Lever | Default | Coverage | Smoke tests | Pass | Fail | Xfail | Skip | Note |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, lever in features.LEVERS.items():
        cov = coverage[name]
        tests = "<br>".join(f"`{_short(e)}`" for e in cov["tests"]) or "none"
        counts = tally(results, cov["tests"])
        lines.append(
            f"| `{name}` | {'on' if lever.default else 'off'} | {DEPTH_LABEL[cov['depth']]} | "
            f"{tests} | {_counts_cells(counts)} | {cov['note']} |")

    lines += [
        "",
        "## Spine (no lever)",
        "",
        "What runs with every lever off: boot, chat turns, tools, auth, routes.",
        "",
        "| Area | Smoke tests | Pass | Fail | Xfail | Skip |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for area, entries in tier1_map.SPINE.items():
        tests = "<br>".join(f"`{_short(e)}`" for e in entries)
        lines.append(f"| {area} | {tests} | {_counts_cells(tally(results, entries))} |")

    uncovered = [n for n in features.LEVERS if coverage[n]["depth"] == "none"]
    lines += ["", "## Uncovered levers", ""]
    lines += [f"- `{n}`: {features.LEVERS[n].description}" for n in uncovered] or ["None."]

    failed = sorted(n for n, o in results.items() if o == "fail")
    lines += ["", "## Failing smoke tests", ""]
    lines += [f"- `{n}`" for n in failed] or ["None in this run."]

    entries = all_entries(tier1_map)
    unmatched = sorted(n for n in results if not any(matches(n, e) for e in entries))
    if unmatched:
        lines += ["", "## Results not in the map", ""]
        lines += [f"- `{n}` ({results[n]})" for n in unmatched]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--junit", type=Path, help="read results from this junit XML instead of running pytest")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check-map", action="store_true", help="only validate tests/smoke/tier1_map.py")
    args = parser.parse_args(argv)

    errors = validate_map()
    if errors:
        print("tests/smoke/tier1_map.py is out of step:", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        return 1
    if args.check_map:
        print("tier1 map: complete")
        return 0

    if args.junit:
        junit, source = args.junit, f"`{args.junit.name}` (an existing pytest junit report)"
    else:
        junit = Path(tempfile.mkdtemp(prefix="tier1-")) / "smoke.xml"
        code = run_smoke(junit)
        if code not in (0, 1):  # 1 = some tests failed: that's data, not an error
            print(f"pytest exited {code}; not writing the page", file=sys.stderr)
            return code
        source = f"`pytest tests/smoke -m \"{PYTEST_MARKERS}\"`"
    if os.environ.get("CI"):
        source += " in CI"

    results = read_junit(junit)
    if not results:
        print(f"no smoke test results in {junit}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(results, source))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
