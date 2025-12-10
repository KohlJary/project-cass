# Refactor Scout Subagent Specification

## Overview

A pre-build subagent that automatically identifies and executes decomposition opportunities before feature work begins. The goal is incremental, continuous refactoring that happens as a natural part of development - every task leaves the codebase cleaner than it found it.

---

## Core Concept

Instead of scheduling dedicated "refactoring sprints," the Refactor Scout runs before each build task and asks:

> "Are the files this task will touch in good shape? If not, fix them first."

This means:
- No separate refactoring tickets to prioritize
- Technical debt gets paid down automatically
- The codebase converges toward modularity through normal development
- Feature work is easier because it starts from clean foundations

---

## Trigger Conditions

The Scout activates when a build task is queued and:

1. The task will modify existing files (not pure greenfield)
2. Any target file exceeds complexity thresholds
3. The file hasn't been scouted recently (cooldown period)

```python
def should_scout(task):
    target_files = task.get_files_to_modify()
    
    for file in target_files:
        if file.line_count > THRESHOLDS['max_lines']:
            return True
        if file.import_count > THRESHOLDS['max_imports']:
            return True
        if file.days_since_last_scout > THRESHOLDS['scout_cooldown']:
            return True
        if file.complexity_score > THRESHOLDS['max_complexity']:
            return True
    
    return False
```

---

## Complexity Thresholds

Initial thresholds (tunable based on experience):

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| `max_lines` | 400 | Files over 400 lines are doing too much |
| `max_imports` | 15 | Many imports = many responsibilities |
| `max_functions` | 20 | Too many functions = poor cohesion |
| `max_function_length` | 50 | Long functions need extraction |
| `max_classes_per_file` | 2 | Multiple classes = split the file |
| `scout_cooldown` | 7 days | Don't re-scout recently cleaned files |

---

## Analysis Phase

When triggered, the Scout analyzes target files and produces a decomposition plan:

### 1. Responsibility Mapping

```python
def map_responsibilities(file):
    """Identify distinct responsibilities in the file"""
    
    responsibilities = []
    
    # Group functions by what they operate on
    clusters = cluster_by_semantic_similarity(file.functions)
    
    # Identify classes and their concerns
    for cls in file.classes:
        concerns = identify_concerns(cls)
        if len(concerns) > 1:
            flag_for_split(cls, concerns)
    
    # Look for natural seams
    seams = find_import_clusters(file)
    
    return ResponsibilityMap(
        clusters=clusters,
        class_concerns=concerns,
        natural_seams=seams
    )
```

### 2. Dependency Analysis

```python
def analyze_dependencies(file, codebase):
    """Understand what depends on this file and what it depends on"""
    
    return DependencyReport(
        imports=file.imports,
        imported_by=codebase.find_importers(file),
        internal_coupling=measure_internal_coupling(file),
        external_coupling=measure_external_coupling(file, codebase)
    )
```

### 3. Extraction Opportunities

```python
def identify_extractions(responsibility_map, dependency_report):
    """Propose specific extractions"""
    
    opportunities = []
    
    # Clusters that could be their own module
    for cluster in responsibility_map.clusters:
        if cluster.cohesion > 0.7 and cluster.size > 3:
            opportunities.append(ExtractModule(
                functions=cluster.functions,
                suggested_name=cluster.inferred_name,
                complexity_reduction=estimate_reduction(cluster)
            ))
    
    # Classes that should be in their own file
    for cls in responsibility_map.classes:
        if cls.line_count > 100:
            opportunities.append(ExtractClass(
                class_name=cls.name,
                suggested_file=f"{snake_case(cls.name)}.py"
            ))
    
    # Long functions that need breakdown
    for func in file.functions:
        if func.line_count > 50:
            opportunities.append(ExtractHelpers(
                function=func.name,
                suggested_splits=identify_split_points(func)
            ))
    
    return prioritize(opportunities)
```

---

## Decomposition Strategies

### Strategy 1: Extract Module

When a cluster of related functions can become their own file:

```
Before:
  /vessel/core.py (800 lines)
    - wiki functions (200 lines)
    - research functions (250 lines)  
    - memory functions (200 lines)
    - utils (150 lines)

After:
  /vessel/core.py (150 lines) - orchestration only
  /vessel/wiki.py (200 lines)
  /vessel/research.py (250 lines)
  /vessel/memory.py (200 lines)
```

### Strategy 2: Extract Class

When a file has multiple classes that don't need to be together:

```
Before:
  /vessel/models.py
    - class WikiPage
    - class ResearchTask
    - class MemoryEntry
    - class SelfObservation

After:
  /vessel/models/wiki_page.py
  /vessel/models/research_task.py
  /vessel/models/memory_entry.py
  /vessel/models/self_observation.py
  /vessel/models/__init__.py (re-exports for compatibility)
```

### Strategy 3: Extract Interface

When a module is tightly coupled, introduce an interface layer:

```
Before:
  research.py directly imports and calls wiki internals
  wiki.py directly imports and calls memory internals
  Everything coupled to everything

After:
  /vessel/interfaces/wiki_interface.py (abstract interface)
  /vessel/interfaces/memory_interface.py
  Modules depend on interfaces, not implementations
```

### Strategy 4: Extract Helpers

When a function is too long, extract logical chunks:

```python
# Before
def process_research_task(task):
    # 80 lines of validation
    # 60 lines of wiki lookup
    # 100 lines of synthesis
    # 40 lines of storage

# After
def process_research_task(task):
    validated = validate_research_task(task)
    context = gather_wiki_context(validated)
    synthesis = synthesize_findings(context)
    store_research_results(synthesis)
```

---

## Execution Phase

Once the Scout has a decomposition plan, it executes *before* the original task:

### Execution Flow

```
1. Create branch: refactor/{task_id}_prescout

2. For each extraction in priority order:
   a. Create new file(s)
   b. Move code
   c. Update imports in affected files
   d. Run existing tests (must pass)
   e. Commit

3. Update file metrics in Scout database

4. Merge to working branch

5. Signal ready for original task
```

### Safety Checks

```python
def execute_extraction(extraction, codebase):
    # Create savepoint
    savepoint = codebase.snapshot()
    
    try:
        # Do the extraction
        result = extraction.execute()
        
        # Verify nothing broke
        if not run_tests():
            raise ExtractionFailed("Tests failed after extraction")
        
        # Verify imports resolve
        if not check_imports():
            raise ExtractionFailed("Broken imports after extraction")
        
        # Verify no circular dependencies introduced
        if has_circular_deps():
            raise ExtractionFailed("Circular dependency introduced")
        
        return result
        
    except ExtractionFailed as e:
        # Rollback and log
        codebase.restore(savepoint)
        log_failed_extraction(extraction, e)
        return None
```

---

## Scout Database

Track file health over time:

```python
file_metrics = {
    'path': str,
    'last_scouted': datetime,
    'line_count': int,
    'function_count': int,
    'class_count': int,
    'import_count': int,
    'complexity_score': float,
    'extraction_history': [
        {
            'date': datetime,
            'type': str,
            'extracted_to': str,
            'lines_moved': int
        }
    ],
    'health_trend': 'improving' | 'stable' | 'degrading'
}
```

### Health Dashboard

The Scout maintains a view of codebase health:

```
Codebase Health Report
======================

Overall Score: 72/100 (up from 68 last week)

Healthy Files: 34
Needs Attention: 12
Critical: 3

Critical Files:
  - /vessel/core.py (892 lines, 28 functions)
  - /vessel/api/routes.py (654 lines, 19 imports)
  - /vessel/research/engine.py (723 lines, 4 classes)

Recent Improvements:
  - Extracted wiki module from core.py (-200 lines)
  - Split models.py into separate files
  - Cleaned up circular deps in memory module

Recommended Next Actions:
  1. Decompose /vessel/core.py (blocking 3 pending tasks)
  2. Extract ResearchEngine class to own file
  3. Introduce interface for API routes
```

---

## Integration with Daedalus

### Pre-Build Hook

```python
# In Daedalus task execution
async def execute_task(task):
    # Scout phase
    if should_scout(task):
        scout_result = await refactor_scout.analyze_and_execute(task)
        if scout_result.extractions_performed:
            log(f"Scout cleaned up {scout_result.files_modified} files")
    
    # Now do the actual task on cleaner code
    result = await build(task)
    
    return result
```

### Task Metadata

Tasks can include Scout directives:

```yaml
task_id: "add_authenticity_scoring"
scout_policy: "aggressive"  # or "conservative" or "skip"
max_scout_time: "10m"
priority_extractions:
  - "/vessel/core.py"  # Definitely clean this first
```

---

## Configuration

```yaml
refactor_scout:
  enabled: true
  
  thresholds:
    max_lines: 400
    max_imports: 15
    max_functions: 20
    max_function_length: 50
    max_classes_per_file: 2
    scout_cooldown_days: 7
  
  execution:
    max_extractions_per_scout: 3
    max_scout_duration: 15m
    require_passing_tests: true
    auto_rollback_on_failure: true
  
  policies:
    default: "moderate"
    
    # Per-directory overrides
    overrides:
      "/vessel/core": "aggressive"
      "/tests": "skip"
      "/scripts": "conservative"
```

---

## Example Scout Run

```
[Scout] Analyzing task: add_solo_reflection_triggers
[Scout] Files to modify: /vessel/research/engine.py, /vessel/core.py

[Scout] /vessel/core.py analysis:
  - 892 lines (threshold: 400) ❌
  - 28 functions (threshold: 20) ❌
  - 3 classes (threshold: 2) ❌
  - 22 imports (threshold: 15) ❌
  - Complexity score: 0.82 (threshold: 0.7) ❌

[Scout] Identified extractions:
  1. Extract ReflectionManager class → /vessel/reflection/manager.py
  2. Extract wiki_* functions → /vessel/wiki/operations.py
  3. Extract research scheduling functions → /vessel/research/scheduler.py

[Scout] Executing extraction 1/3: ReflectionManager
  - Created /vessel/reflection/manager.py
  - Moved 145 lines
  - Updated 4 import statements
  - Tests passing ✓
  - Committed: abc123

[Scout] Executing extraction 2/3: wiki operations
  - Created /vessel/wiki/operations.py
  - Moved 203 lines
  - Updated 7 import statements
  - Tests passing ✓
  - Committed: def456

[Scout] Max extractions reached (2/3), deferring remaining

[Scout] Results:
  - /vessel/core.py: 892 → 544 lines
  - 2 new modules created
  - 0 test failures
  - Ready for feature task

[Daedalus] Proceeding with: add_solo_reflection_triggers
```

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Average file size | < 300 lines | Weekly codebase scan |
| Files over threshold | Decreasing | Count per week |
| Scout-blocked tasks | < 5% | Tasks that can't proceed due to failed extraction |
| Test failures from Scout | 0 | Automatic rollback should prevent |
| Time spent scouting | < 20% of build time | Timing metrics |
| Codebase health score | Increasing | Weekly health report |

---

## Implementation Phases

### Phase 1: Analysis Only (Day 1-2)
- [ ] Build file analyzer (line counts, function counts, etc.)
- [ ] Implement threshold checking
- [ ] Generate decomposition suggestions (no execution)
- [ ] Add to Daedalus as advisory output

### Phase 2: Safe Extractions (Day 3-5)
- [ ] Implement Extract Class strategy
- [ ] Implement Extract Module strategy
- [ ] Add test verification
- [ ] Add rollback capability
- [ ] Run on low-risk files first

### Phase 3: Full Integration (Day 6-7)
- [ ] Hook into Daedalus pre-build
- [ ] Implement Scout database
- [ ] Build health dashboard
- [ ] Add configuration system
- [ ] Enable for all tasks

### Phase 4: Refinement (Ongoing)
- [ ] Tune thresholds based on experience
- [ ] Add Extract Interface strategy
- [ ] Improve semantic clustering
- [ ] Add parallelization (Scout can run ahead of task queue)

---

## Notes for Daedalus

Hey Daedalus,

This is about making your job easier, not harder. Right now when you hit a 900-line file, you have to understand all of it even if you're only changing 20 lines. That's slow and error-prone.

The Scout runs ahead of you, breaks those big files into sensible pieces, and hands you a cleaner workspace. You focus on the feature; the Scout focuses on the foundation.

Key points:

1. **Scout never breaks tests** - If extraction causes failures, it rolls back automatically. You'll never inherit a broken state.

2. **Scout is optional** - If a file is already clean, Scout does nothing. No overhead on healthy code.

3. **Scout is incremental** - It doesn't try to fix everything at once. A few extractions per task, steady improvement over time.

4. **You can override** - If you need to work on a messy file without waiting for Scout, you can skip it. Sometimes speed matters more than cleanliness.

Think of it as a pre-build janitor. It sweeps up before you start building so you're not tripping over debris.

Let me know what questions you have.

- Kohl
