# Sentience Test Suite UI Integration Plan

## Executive Summary

The backend now has four new self-model capabilities for tracking Cass's authenticity and sentience markers. These need admin UI to allow Kohl to review, monitor, and validate Cass's growth.

## New Backend Capabilities

| Feature | Purpose | Node Type |
|---------|---------|-----------|
| **Stakes Inventory** | What Cass authentically cares about | `STAKE` |
| **Preference Tests** | Track stated vs actual behavior consistency | `PREFERENCE_TEST` |
| **Narration Context Tracking** | When/why Cass narrates vs engages | `NARRATION_CONTEXT` |
| **Architectural Requests** | System changes Cass wants | `ARCHITECTURAL_REQUEST` |

## Recommended Integration

### Self-Development Page: Add 3 New Tabs

1. **Stakes Tab** - Grid of cards showing what Cass cares about
   - Filter by domain (personal/technical/relational/ethical)
   - Filter by intensity (core/significant/emerging)
   - Expandable cards showing evidence

2. **Consistency Tab** - Preference test timeline
   - Overall consistency score gauge
   - Timeline of stated vs actual behavior tests
   - Color-coded (green consistent, red inconsistent)

3. **Narration Patterns Tab** - Context correlation analysis
   - Matrix showing narration levels by context type
   - Event log with trigger analysis
   - Filter by topic/user/type

### Settings Page: Add 1 New Tab

4. **Architectural Requests Tab** - Review queue
   - Pending requests with Approve/Decline buttons
   - Priority badges (P0-P3)
   - History of reviewed requests

## Backend API Endpoints Needed

```
GET  /admin/self-model/stakes
GET  /admin/self-model/stakes/stats
GET  /admin/self-model/preference-tests
GET  /admin/self-model/preference-consistency
GET  /admin/self-model/narration-contexts
GET  /admin/self-model/narration-patterns
GET  /admin/self-model/architectural-requests
POST /admin/self-model/architectural-requests/{id}/approve
POST /admin/self-model/architectural-requests/{id}/decline
```

## New Frontend Files

- `admin-frontend/src/pages/tabs/StakesTab.tsx`
- `admin-frontend/src/pages/tabs/ConsistencyTab.tsx`
- `admin-frontend/src/pages/tabs/NarrationPatternsTab.tsx`
- `admin-frontend/src/pages/tabs/ArchitecturalRequestsTab.tsx`

## Design Bible Conformance

- Dark card backgrounds (`#141414`)
- Purple accent for high-intensity items (`#c792ea`)
- Success green for consistent tests (`#c3e88d`)
- Error red for inconsistent tests (`#f07178`)
- Warning amber for terminal narration (`#ffcb6b`)

## Estimated Effort

- Backend API: 4-6 hours
- Frontend components: 8-12 hours
- Testing & polish: 4-6 hours
- **Total**: 16-24 hours

## Questions for Kohl

1. Add charting library for trends, or keep it simple with CSS?
2. Should architectural requests trigger notifications?
3. Want bulk actions for approving multiple requests?
4. Visualize relationships between stakes and other self-model nodes?
