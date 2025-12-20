# Cliff Notes

Quick observations about things that need attention. Not urgent, but shouldn't be forgotten.

---

## 2025-12-20

### SDK can_use_tool callback not being invoked
- **Where**: `daedalus/src/daedalus/worker/harness.py`
- **Issue**: Claude Agent SDK's `can_use_tool` callback never fires - CLI subprocess auto-approves based on user's ~/.claude settings before reaching our callback
- **Architecture**: Two-layer permission system:
  1. CLI internal rules (from user settings, CLAUDE.md) - runs first
  2. Our callback - only fires if CLI says "ask user"
- **Symptoms**:
  - "Stream closed" error when Write tool used (CLI tries to prompt but stream handling fails)
  - Safe commands (echo, ls) auto-approved at CLI level, callback never invoked
- **Working components**: IcarusBus async wait, permissions.py ApprovalScope, worker harness streaming
- **Next step**: Test with minimal config that forces all permissions through callback

---

## 2025-12-19

### Metrics use local time instead of UTC
- **Where**: `github_source.py`, `token_source.py`, rollup date calculations
- **Issue**: GitHub API and Anthropic API both use UTC timestamps, but our metrics aggregation uses local time (`datetime.now()`)
- **Impact**: Date boundaries will be off, especially for users not in UTC timezone
- **Fix**: Use `datetime.utcnow()` or `datetime.now(timezone.utc)` for all date comparisons and rollup keys

### Token spend tracking may be under-counting
- **Where**: `token_tracker.py`
- **Issue**: Reported spend ($23.36/month, $13.64/today) seems lower than expected
- **Possible causes**:
  - Cache tokens not being counted correctly
  - Some API calls not going through the tracker
  - Pricing calculation may be off
- **To investigate**: Compare raw Anthropic billing with our tracked totals
