# Cliff Notes

Quick observations about things that need attention. Not urgent, but shouldn't be forgotten.

---

## 2025-12-20

### ✓ RESOLVED: SDK can_use_tool callback not being invoked
- **Where**: `daedalus/src/daedalus/worker/harness.py`
- **Root cause**: The SDK's `stream_input` method only waits for first result (before closing stdin) when hooks or MCP servers are present. With `can_use_tool` alone, stdin closed immediately after sending the prompt, breaking bidirectional control protocol.
- **Solution**: Switch from `can_use_tool` callback to `PreToolUse` hook
  - Hooks keep stdin open for bidirectional communication
  - Hook receives `tool_name` and `tool_input` → check ApprovalScope → return `permissionDecision`
  - Returns `"allow"`, `"deny"`, or escalates to bus for Daedalus approval
- **Test results** (test_hook.py):
  - `echo` command → auto-approved (Granted: 1)
  - `rm -rf` command → auto-denied (Denied: 1)
  - `wget` command → escalated to bus, timeout (Escalated: 2)
- **Key insight**: The CLI's `stream_input` checks `if self.sdk_mcp_servers or has_hooks` but not `if self.can_use_tool`. Using hooks is the intended extension point for permission routing

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
