---
name: Unified Query Interface for Global State Bus
summary: Federated query system where subsystems register as queryable sources with structured queries, precomputed rollups, and unified access for Cass
created: 2025-12-19
updated: 2025-12-19
resolved: 2025-12-19
status: COMPLETE
---

# Unified Query Interface for Global State Bus

## Overview

Extend the Global State Bus with a unified query interface where subsystems register as "queryable sources" and respond to structured queries. This enables:

1. **Precomputed state**: Subsystems maintain rolling aggregates, reducing recomputation
2. **Unified queries**: Common interface across all data sources
3. **LLM-friendly**: Cass can query any subsystem through a single tool
4. **Cross-subsystem correlation**: Compare GitHub engagement with token costs, etc.

**Reference implementations**: GitHub metrics + Token tracking

## Implementation Summary

### Files Created
- `backend/query_models.py` - StateQuery, TimeRange, Aggregation, QueryResult dataclasses
- `backend/queryable_source.py` - QueryableSource ABC, RefreshStrategy enum
- `backend/sources/__init__.py` - Package init
- `backend/sources/github_source.py` - GitHubQueryableSource (SCHEDULED refresh)
- `backend/sources/token_source.py` - TokenQueryableSource (LAZY refresh)
- `backend/handlers/state_query.py` - query_state tool handler

### Files Modified
- `backend/state_bus.py` - Added register_source, query, describe_sources methods
- `backend/database.py` - Added source_rollups table (schema v18)
- `backend/routes/admin/state.py` - Added /sources, /query, /rollups endpoints
- `backend/agent_client.py` - Added query_state tool with keyword detection
- `backend/main_sdk.py` - Source registration at startup, tool routing

### Key Features
- Three refresh strategies: SCHEDULED, LAZY, EVENT_DRIVEN
- Repo-level filtering for GitHub metrics
- Time presets: today, yesterday, last_7d, last_30d, this_week, this_month
- LLM-friendly formatted results
- Admin API for debugging/visibility

### Commits
- `4e1e84f` - Add unified query interface for Global State Bus
- `0eaf25e` - Fix repo filter for GitHub time series queries
