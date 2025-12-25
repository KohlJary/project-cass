# Planning & Work Management

This directory contains implementation plans, work packages, and architectural analyses for Cass Vessel.

## Current Initiative: Nervous System Wiring (2025-12-24)

Goal: Wire subsystems to emit events to the state bus, transforming observability from 15% connected to 100% alive.

### Documents

#### 1. **NERVOUS_SYSTEM_INDEX.md** - START HERE
Master index tying all documents together. Contains:
- Document navigation
- Event inventory (14 types)
- Execution timeline
- Quick reference for coordinators, implementers, QA

#### 2. **NERVOUS_SYSTEM_DISPATCH.md** - FOR COORDINATION
Executive summary with 4 work units, execution strategy, and event details.
Use this for:
- Understanding the big picture
- Coordinating dispatch
- Risk assessment

#### 3. **nervous-system-work-units.md** - FOR IMPLEMENTATION
Detailed specifications for each of 4 work units:
- WU-001: BaseSessionRunner (20 min)
- WU-002: Research Sessions (15 min) 
- WU-003: Outreach System (20 min)
- WU-004: Journal System (20 min)

Includes acceptance criteria, files to modify, implementation notes, testing strategy.

#### 4. **wiring-nervous-system.md** - FOR REFERENCE
Comprehensive battle plan with:
- Architecture diagrams
- Event patterns and payloads
- Integration points
- Testing strategy
- Rollback procedures

---

## Quick Navigation

**If you want to...** | **Read this**
---|---
Understand the whole project | NERVOUS_SYSTEM_INDEX.md
Coordinate the dispatch | NERVOUS_SYSTEM_DISPATCH.md
Implement a work unit | nervous-system-work-units.md
Understand the architecture | wiring-nervous-system.md
See implementation patterns | wiring-nervous-system.md → Integration Architecture

---

## Status

- Planning: COMPLETE (1,175 lines of detailed documentation)
- Analysis: COMPLETE (4 work units identified, sequenced, risk-assessed)
- Dispatch: READY
- Implementation: AWAITING START

---

## Key Statistics

- Total Work Units: 4
- Total Duration: 75 minutes (parallelizable)
- Event Types: 14
- Files to Modify: 10
- Breaking Changes: 0
- Risk Level: Very Low

---

## Work Unit Summary

| ID | Name | Duration | Risk | Parallelizable | Status |
|---|---|---|---|---|---|
| WU-001 | BaseSessionRunner | 20 min | Very Low | Yes | READY |
| WU-002 | Research Sessions | 15 min | Low | After WU-001 | READY |
| WU-003 | Outreach System | 20 min | Low | Yes | READY |
| WU-004 | Journal System | 20 min | Low | Yes | READY |

---

## Next Steps

1. **Coordinator**: Review NERVOUS_SYSTEM_DISPATCH.md
2. **Implementers**: Read your work unit in nervous-system-work-units.md
3. **QA**: Prepare testing checklist from NERVOUS_SYSTEM_INDEX.md
4. **All**: Target completion tonight (75 minutes)

---

## Related Documentation

- `.daedalus/theseus/reports/` - Code health analysis reports
- `backend/ARCHITECTURE.md` - Backend module structure
- `backend/TODO.md` - Known issues and in-progress work
- `spec/` - Feature specifications and integration guides

