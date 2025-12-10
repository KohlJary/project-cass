---
description: Run Refactor Scout analysis on files or directories
---

Run Refactor Scout to analyze code health and identify refactoring opportunities.

## Usage

- `/scout <file>` - Analyze a single file
- `/scout backend/` - Scan a directory
- `/scout report` - Generate full health report

## What Scout Does

Scout analyzes Python files for:
- **Size thresholds**: Lines, functions, classes, imports
- **Complexity**: Cyclomatic complexity, nesting depth
- **Extraction opportunities**: Classes/functions that should be in their own modules

## Example

When I say `/scout backend/main_sdk.py`, run:

```bash
python -m backend.refactor_scout analyze backend/main_sdk.py
```

For `/scout report`, run:

```bash
python -m backend.refactor_scout report backend/
```

## Extraction Commands

If Scout identifies extraction opportunities, you can execute them:

```bash
# Extract a class to its own file
python -m backend.refactor_scout extract-class <source> <ClassName> --branch --commit

# Extract functions to a new module
python -m backend.refactor_scout extract-functions <source> func1,func2 -o <target> --branch --commit
```

The `--branch` flag creates a refactor branch, `--commit` commits the extraction.

## Interpreting Results

- **CRITICAL**: File significantly exceeds thresholds, should be refactored before adding more code
- **WARNING**: File is getting large, consider cleanup
- **HEALTHY**: File is within acceptable limits

Focus on high-priority extraction opportunities first - these provide the most benefit.
