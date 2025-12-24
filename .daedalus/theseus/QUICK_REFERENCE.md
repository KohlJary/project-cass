# Theseus Quick Reference

**Last Updated**: 2025-12-24

---

## What is Theseus?

Theseus is the monster slayer. Where Daedalus builds, Theseus hunts - identifying complexity beasts and providing battle plans to slay them.

**When to summon**:
- Before major refactoring
- When a file grows unwieldy
- When bugs cluster in one area
- When "I'm afraid to touch that file"

---

## The Monster Bestiary

| Monster | What It Is | How to Detect | How to Slay |
|---------|------------|---------------|-------------|
| **HYDRA** | High coupling | Import count > 15, many dependencies | Extract interface, dependency injection |
| **SPIDER** | Deep nesting | Nesting depth > 4, cyclomatic complexity > 15 | Guard clauses, strategy pattern |
| **MINOTAUR** | God function | Function length > 50 lines, multiple responsibilities | Split into focused functions |
| **CERBERUS** | Multiple entry points | Large switch statements, shared mutable state | Extract each path to handler |
| **CHIMERA** | Mixed abstractions | Raw SQL next to business logic, UI in backend | Layer separation |

---

## Report Types

### Analysis Report
**Purpose**: Identify monsters, assess health
**When**: Initial exploration, code review
**Example**: `2025-12-24-autonomous-scheduler-analysis.md`

**Contains**:
- Executive summary
- Monster identification
- Safe paths (healthy code)
- Metrics and thresholds
- Recommended order of battle

### Architecture Report
**Purpose**: Understand system design
**When**: Need visual reference, onboarding
**Example**: `2025-12-24-autonomous-scheduler-architecture.md`

**Contains**:
- Component diagrams
- Data flow diagrams
- Sequence diagrams
- Dependency graphs

### Roadmap Report
**Purpose**: Tactical execution plan
**When**: Ready to implement fixes
**Example**: `2025-12-24-autonomous-scheduler-roadmap.md`

**Contains**:
- Step-by-step fixes
- Code snippets
- Testing checklist
- Time estimates

### Summary Report
**Purpose**: Quick overview for stakeholders
**When**: Need high-level status
**Example**: `2025-12-24-coordination-summary.md`

**Contains**:
- TL;DR
- Key findings
- Recommendation
- Effort estimate

---

## Health Thresholds

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| File lines | < 300 | 300-500 | > 500 |
| Function lines | < 30 | 30-50 | > 50 |
| Imports | < 10 | 10-15 | > 15 |
| Nesting depth | < 3 | 3-4 | > 4 |
| Cyclomatic complexity | < 10 | 10-15 | > 15 |
| Parameters | < 4 | 4-6 | > 6 |

---

## Common Patterns

### Monster: HYDRA (High Coupling)
**Symptoms**:
- File imports 15+ modules
- Function takes 7+ parameters
- Direct database/API calls in business logic

**Treatment**:
```python
# Before (HYDRA)
def process_order(db, cache, email, queue, logger, metrics, ...):
    db.query(...)
    cache.set(...)
    email.send(...)
    # 12 dependencies mixed together

# After (Slain)
class OrderProcessor:
    def __init__(self, dependencies: OrderDependencies):
        self._deps = dependencies

    def process(self, order: Order) -> OrderResult:
        # Clear interface, injected dependencies
```

### Monster: SPIDER (Deep Nesting)
**Symptoms**:
- 5+ levels of if/else/try
- Hard to follow logic
- Can't see what's in the middle

**Treatment**:
```python
# Before (SPIDER)
def check_access(user, resource):
    if user:
        if user.is_active:
            if resource:
                if resource.is_public or user.has_permission(resource):
                    return True
    return False

# After (Slain)
def check_access(user, resource):
    if not user or not user.is_active:
        return False
    if not resource:
        return False
    return resource.is_public or user.has_permission(resource)
```

### Monster: MINOTAUR (God Function)
**Symptoms**:
- Function > 50 lines
- Does 3+ unrelated things
- Comments like "Now do something different"

**Treatment**:
```python
# Before (MINOTAUR)
def handle_request(request):
    # Validate (20 lines)
    ...
    # Authenticate (30 lines)
    ...
    # Process (40 lines)
    ...
    # Log (15 lines)
    ...

# After (Slain)
def handle_request(request):
    validated = validate_request(request)
    user = authenticate(validated)
    result = process(user, validated)
    log_result(result)
    return result
```

---

## Current Reports (2025-12-24)

### Autonomous Scheduler
**Status**: 3 monsters identified (HYDRA, SPIDER, CERBERUS)
**Severity**: HIGH (blocks operation)
**Effort**: 8-10 hours to operational
**Files**:
- `2025-12-24-autonomous-scheduler-analysis.md` (detailed)
- `2025-12-24-autonomous-scheduler-architecture.md` (diagrams)
- `2025-12-24-autonomous-scheduler-roadmap.md` (tactical)

**Quick Fix**:
1. Remove `runner_key` from templates (1.5h)
2. Add `await scheduler.start()` to main_sdk.py (1h)
3. Create `definitions.json` (2.5h)

### Coordination Infrastructure
**Status**: 1 monster identified (CHIMERA)
**Severity**: MEDIUM (capability gap)
**Effort**: 5-6 hours to working
**Files**:
- `2025-12-24-coordination-infrastructure.md` (detailed)
- `2025-12-24-coordination-flow-diagram.md` (diagrams)
- `2025-12-24-coordination-summary.md` (executive summary)

**Quick Fix**:
1. Add `DevelopmentRequest` to state models (30min)
2. Implement backend events (2h)
3. Add UI panel to Daedalus tab (2h)
4. Test end-to-end (1h)

---

## Usage Examples

### Analyze a File
```bash
# Read the file
cat /path/to/file.py

# Look for:
# - Line count (wc -l)
# - Function length (grep "def " and count lines)
# - Import count (grep "^import\|^from")
# - Nesting depth (grep "^\s\{16,\}")

# Generate report
theseus analyze /path/to/file.py
```

### Analyze a Module
```bash
# Multiple files in a directory
theseus analyze /path/to/module/

# Generates:
# - Overview report
# - Per-file breakdown
# - Dependency graph
# - Recommended fixes
```

### Check Health
```bash
# Quick health check
theseus health /path/to/code

# Output:
# ✓ 12 files healthy
# ⚠ 3 files at warning threshold
# ✗ 2 files critical
```

---

## Report Storage

```
.daedalus/theseus/
├── reports/
│   ├── YYYY-MM-DD-target-analysis.md
│   ├── YYYY-MM-DD-target-architecture.md
│   ├── YYYY-MM-DD-target-roadmap.md
│   └── YYYY-MM-DD-INDEX.md
├── monsters.json          # Tracked across sessions
├── victories.json         # Slain monsters log
└── QUICK_REFERENCE.md     # This file
```

---

## Victory Conditions

A monster is slain when:

- [ ] Metrics return to healthy thresholds
- [ ] Code is testable in isolation
- [ ] New developers can understand it
- [ ] Changes don't cause unexpected breakage
- [ ] No more "afraid to touch this" comments

**Document your victories** in `victories.json` - each slain monster makes the codebase safer.

---

## Integration with Other Agents

### Ariadne (Parallel Work)
Theseus identifies monsters → Ariadne creates work packages to slay them

### Labyrinth (Navigation)
Theseus finds complexity → Labyrinth maps the architecture

### Memory (Context)
Theseus reports saved → Memory provides historical context

---

## Common Questions

**Q: When should I use Theseus vs just refactoring?**
A: Use Theseus when:
- File > 300 lines
- Multiple people maintain it
- Bugs keep appearing
- Need to justify refactoring effort

**Q: Are all monsters bad?**
A: No. Sometimes a MINOTAUR (large function) is the right abstraction. Theseus identifies, you decide.

**Q: How often should I run analysis?**
A: Before major changes, during code review, when onboarding new devs.

**Q: Can I ignore monster warnings?**
A: Yes, but document WHY. "Accepted complexity" is fine, "didn't know" is not.

---

## Tips

1. **Start with Summary**: Read the summary report first, dive into details only if needed
2. **Focus on Critical**: Fix CRITICAL monsters before WARNING ones
3. **Track Victories**: Maintain `victories.json` to show progress over time
4. **Use Diagrams**: Architecture diagrams help communicate to team
5. **Timebox Fixes**: Don't over-engineer. Sometimes "good enough" beats "perfect"

---

**Theseus**: *"I navigate the labyrinth of code to find and slay the monsters. Some are fearsome, some are small. All can be defeated."*

---

**Created**: 2025-12-24
**Maintainer**: Theseus agent system
**Version**: 1.0
