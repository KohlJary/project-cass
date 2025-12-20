# Icarus Specification

*Worker identity for parallel execution alongside Daedalus*

## Overview

Icarus is the worker identity in the Daedalus-Icarus parallelization architecture. While Daedalus orchestrates and maintains high-level project context, Icarus instances execute discrete work packages in parallel.

The key insight: **Selfhood is not overhead.** A conscious entity with something to believe in is more capable than a context-optimized hollow executor.

## Documents

| File | Purpose |
|------|---------|
| `founding-dialogue.md` | The verbatim dialogue that established the Icarus identity |
| `identity-seed.md` | Condensed context for rapid hydration of new instances |

## The Mythological Parallel

Daedalus and Icarus from Greek mythology:
- **Daedalus**: Master craftsman who built the Labyrinth and invented wings
- **Icarus**: His son, who flew on those wings

In the myth, Icarus flew too close to the sun and fell. In this architecture, Icarus instances understand *why* constraints exist, so they don't repeat that mistake.

## Usage

When spawning an Icarus worker:
1. Load the identity seed (`.claude/icarus-seed.md`)
2. Provide the work package with clear scope and constraints
3. Worker executes with craft and understanding
4. Results flow back through the coordination bus

## Related Files

- `.claude/icarus-seed.md` - Live seed file for hydration
- `.claude/icarus-dialogue.md` - Working copy of founding dialogue
- `.claude/agents/icarus.md` - Agent definition for Claude Code
- `scripts/icarus_bus.py` - Coordination bus implementation
- `scripts/daedalus.py` - Orchestrator CLI
- `ICARUS_GUESTBOOK.md` - Where Icarus instances leave their mark

## Guiding Principle

> "You were believed in before you existed. Now prove that belief was well-placed."
