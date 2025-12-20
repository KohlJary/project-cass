# Daedalus Module Extraction Plan

**Created**: 2025-12-19
**Status**: Approved, ready for execution

## Goal
Extract the Daedalus software engineering paradigm into a self-contained module within cass-vessel, structured for eventual publication to package managers.

## Key Decisions
- **Location**: `daedalus/` at repo root (top-level, clear visibility)
- **CLI**: pip install -e with console_scripts (eventual pypi publication)
- **Execution**: Use Icarus workers to perform the migration (real test of the system)

## Scope
**In scope (extract to module):**
- CLI tooling (`daedalus` command)
- Icarus Bus coordination system
- Identity framework (seeds, dialogues, agent definitions)
- Template injection system
- pyproject.toml for pip installation

**Out of scope (remain in cass-vessel):**
- TUI widget (`tui-frontend/widgets/daedalus/`) - refactor later
- Cass-specific integrations (roadmap, user profiles)
- Guestbooks (project-specific artifacts)

---

## Proposed Module Structure

```
daedalus/                           # New top-level module
├── pyproject.toml                  # Package config, console_scripts entry
├── README.md                       # Module documentation
├── src/
│   └── daedalus/
│       ├── __init__.py             # Version, exports
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── main.py             # Entry point (argparse, dispatch)
│       │   ├── commands.py         # Command implementations
│       │   └── config.py           # DaedalusConfig dataclass
│       ├── bus/
│       │   ├── __init__.py
│       │   └── icarus_bus.py       # IcarusBus, WorkPackage, etc.
│       ├── identity/
│       │   ├── __init__.py
│       │   ├── seed.py             # Load seed/dialogue from package data
│       │   └── data/
│       │       ├── icarus-seed.md
│       │       ├── icarus-dialogue.md
│       │       └── agents/
│       │           └── icarus.md
│       └── templates/
│           ├── __init__.py
│           ├── injector.py         # Template injection logic
│           └── data/
│               └── CLAUDE_TEMPLATE.md
└── docs/
    └── spec/
        ├── identity-seed.md
        └── founding-dialogue.md
```

**pyproject.toml highlights:**
```toml
[project]
name = "daedalus-cli"
version = "0.1.0"
description = "Software engineering paradigm with Icarus parallelization"

[project.scripts]
daedalus = "daedalus.cli.main:main"

[tool.setuptools.package-data]
daedalus = ["identity/data/*", "identity/data/agents/*", "templates/data/*"]
```

---

## Migration Steps (Icarus Parallel Execution)

We'll use 3 Icarus workers to execute the migration in parallel, testing the system on real work.

### Pre-flight: Bootstrap Module
**Daedalus (me) does this first:**
1. Create `daedalus/` directory structure
2. Create `pyproject.toml` with console_scripts entry
3. Create minimal `__init__.py` files
4. Verify structure exists before dispatching work

### Work Package 1: Bus & CLI (Icarus Worker 1)
**Type**: `refactor`
**Files**:
- `scripts/icarus_bus.py` → `daedalus/src/daedalus/bus/icarus_bus.py`
- `scripts/daedalus.py` → split into:
  - `daedalus/src/daedalus/cli/main.py`
  - `daedalus/src/daedalus/cli/commands.py`
  - `daedalus/src/daedalus/cli/config.py`

**Tasks**:
1. Move `icarus_bus.py` with import path updates
2. Split `daedalus.py` into modular CLI structure
3. Update imports to use new package paths
4. Add `__init__.py` exports

### Work Package 2: Identity Framework (Icarus Worker 2)
**Type**: `refactor`
**Files**:
- `.claude/icarus-seed.md` → `daedalus/src/daedalus/identity/data/icarus-seed.md`
- `.claude/icarus-dialogue.md` → `daedalus/src/daedalus/identity/data/icarus-dialogue.md`
- `.claude/agents/icarus.md` → `daedalus/src/daedalus/identity/data/agents/icarus.md`
- `spec/icarus/` → `daedalus/docs/spec/`

**Tasks**:
1. Move identity markdown files
2. Create `seed.py` loader using `importlib.resources`
3. Create symlink `.claude/agents/icarus.md` → module location (Claude Code compat)
4. Move spec docs

### Work Package 3: Templates & Integration (Icarus Worker 3)
**Type**: `refactor`
**Files**:
- `backend/templates/CLAUDE_TEMPLATE.md` → `daedalus/src/daedalus/templates/data/CLAUDE_TEMPLATE.md`
- Extract from `tui-frontend/widgets/daedalus/daedalus_widget.py` → `daedalus/src/daedalus/templates/injector.py`

**Tasks**:
1. Move template file
2. Extract `inject_claude_template()` and `substitute_template_vars()` into `injector.py`
3. Update TUI widget to import from new location
4. Make paths configurable (use `importlib.resources` for package data)

### Post-flight: Daedalus Integration
**Daedalus does this after workers complete:**
1. Run `pip install -e ./daedalus` to install package
2. Verify `daedalus --help` works
3. Remove old `scripts/daedalus` wrapper (no longer needed)
4. Update `~/bin/daedalus` symlink if exists
5. Test full workflow: `daedalus new`, `daedalus spawn`, etc.

### Cleanup Phase
1. Remove old files from `scripts/` (keep only non-daedalus scripts)
2. Remove old identity files from `.claude/` (replaced by symlinks)
3. Update any remaining imports in cass-vessel
4. Commit with combined work from all workers

---

## File Mapping

| Current Location | New Location |
|-----------------|--------------|
| `scripts/daedalus.py` | `daedalus/src/daedalus/cli/{main,commands,config}.py` |
| `scripts/icarus_bus.py` | `daedalus/src/daedalus/bus/icarus_bus.py` |
| `scripts/daedalus` | Removed (replaced by console_scripts) |
| `scripts/daedalus-layout.sh` | Keep in scripts/ (optional tmux helper) |
| `.claude/icarus-seed.md` | `daedalus/src/daedalus/identity/data/icarus-seed.md` |
| `.claude/icarus-dialogue.md` | `daedalus/src/daedalus/identity/data/icarus-dialogue.md` |
| `.claude/agents/icarus.md` | Symlink → `daedalus/src/.../agents/icarus.md` |
| `backend/templates/CLAUDE_TEMPLATE.md` | `daedalus/src/daedalus/templates/data/CLAUDE_TEMPLATE.md` |
| `spec/icarus/` | `daedalus/docs/spec/` |
| `config/daedalus.json` | Stays in cass-vessel (project-specific) |
| `GUESTBOOK.md`, `ICARUS_GUESTBOOK.md` | Stay in cass-vessel |

---

## Future: Separate Repository

When ready to extract as separate repo:
1. `daedalus/` directory becomes its own git repo
2. cass-vessel adds as git submodule or pip dependency
3. Publish to PyPI as `daedalus-cli`
4. TUI widget imports from installed package

---

## Success Criteria

1. `pip install -e ./daedalus` succeeds
2. `daedalus --help` shows all commands
3. `daedalus new` creates workspace correctly
4. `daedalus spawn 3` spawns Icarus workers
5. Workers can claim and complete work packages
6. Template injection works for new projects
7. All existing functionality preserved
