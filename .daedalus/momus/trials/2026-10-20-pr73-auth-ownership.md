# Momus review: PR #73 (fix/auth-ownership, 6033df9), claims: closes #19 and #20

Verdict: consistent, mostly shown. Core claims hold; no blocker. Four findings, none High.

Commands run (read-only, in a scratchpad copy for mutations):
- pytest tests/smoke/test_auth_ownership.py tests/test_route_auth.py tests/test_auth.py -> 851 passed, 22 skipped
- mutation copy (backend minus data/venv) of the PR; each reverted individually, then test_auth_ownership.py:
  - drop set_user_status("pending") in register: 2 failed (caught)
  - admin carve-out removed (admin never allowed): 2 failed (caught)
  - ownership check made always-pass: failed (caught)
  - drop _require_approved in refresh(): 7 passed (NOT caught)
  - drop the rejected branch of _require_approved: 7 passed (NOT caught)

F1 (Medium) Same-class leak left open: GET /cass/disagreements?user_id=X
  routes/cass.py:219-227 + route_guard.py USER_ROUTES ("GET","/cass/*"). Handler has no auth dependency, so it is USER level: any logged-in user passes user_id of another user and gets get_disagreements_with_user(X): topic, their_position, my_position, rationale, with_user_name (self_model.py:485-497). Scenario: Alice calls /cass/disagreements?user_id=<Bob> and reads what Bob argued with Cass. The PR answers "journals were the only per-user routes" implicitly; they are not. Not in #19/#20 text, so not a claim failure, but the issue title is "ownership checks on per-user" data.
  Other per-user routes checked: users.py GET /{id} already owner-only; /conversations user_id param already 403s; /memory/test/user/{id} is default-ADMIN; admin/stats user routes are admin. Read by grep only, not by exhaustively booting the route table.

F2 (Low-Medium) Refresh and rejected-account checks are untested
  auth.py (refresh: self._require_approved(token_data.user_id)); test_auth_ownership.py never calls /auth/refresh nor sets status "rejected". Reverting either leaves 7/7 green (mutation above). The claim "login and token refresh refuse pending/rejected" is shown only for login+pending. Scenario: a user rejected after login keeps minting access tokens via refresh forever, and nothing fails. Cheapest test: set_user_status(uid,"rejected"), POST /auth/refresh with a refresh token from before -> 403; same for login.
  Related, not introduced here: get_current_user/route_guard never check status, so an already-issued access token keeps working until expiry after rejection (auth.py user_id_from_any_token). Registration cannot produce such tokens any more.

F3 (Low) Status write is a separate, unchecked second step
  auth.py register(): create_user() inserts with column default status='approved' (schema.py:47), then set_user_status(...) is called and its bool return is ignored (users.py:1929-1942 returns False if load_profile fails). A failure there leaves an approved account; the auth record is saved afterwards, so login would then succeed with no admin approval. Window is small and needs an unusual failure, so Low. Fix is to check the return or insert pending directly.

F4 (Low) Mobile: pending path works, but UX is rough
  - register throws Error(message) (useAuth.ts ~77-80) so no crash; shown via setAuthError in App.tsx, i.e. as an error. Onboarding profile (fullProfile, App.tsx:52-58) is discarded because setPendingOnboarding(true) is never reached; it is not re-collected after approval.
  - A later login on a still-pending account shows raw 'API error: 403 Forbidden - {"detail":"Account pending ..."}' (client.ts fetch error format), not the clean message. Not a crash.
  - Not run: no mobile tests or build executed. The mobile claim is untested by me and by the PR (no TS test).

Checked and holds:
- Token issuance paths: only AuthService.login/refresh (auth.py create_tokens calls) and /admin/auth/login (status checked, routes/admin/auth.py ~ admin_login) and scripts/daedalus_auth.py (CLI, needs local secret). No OAuth route found. WebSocket auth (websocket_handlers.py ~543-588) and route_guard only decode tokens; neither checks status, but pending users can no longer obtain tokens.
- /admin/auth/register (public) already created pending users with a separate password_hash; its users can't log in via /auth/login (no auth record).
- Lockout of existing users: schema default 'approved' (schema.py:47), migrate_user_status adds column DEFAULT 'approved' (migrations.py:747), load_profile maps NULL to approved (users.py:751), _require_approved uses `or "approved"`. Users with NULL or approved status are not locked out. Not run against a real DB (forbidden); reasoned from code.
- Admin carve-out: user_is_admin (route_guard.py:231) reads users.is_admin from SQLite, the same check route_guard uses for ADMIN level (route_guard.py:286); fails closed on exception.
- route_guard: removing the three USER_ROUTES entries is correct because get_current_user is in _SELF_AUTH_DEPENDENCIES (route_guard.py), so the routes become SELF level and authenticate themselves. They still return 401 with no token (get_current_user). Side effect: in DEMO_MODE, anonymous demo visitors no longer get GET on these journals (SELF level skips the demo-anonymous branch, and get_current_user requires a token). Possibly intended; not mentioned in the PR.
- Journal tests: three paths asserted 403 for non-owner; owner and admin 200 for list route only (date/search not asserted for owner/admin).

Residual (pre-existing, not from this PR): email squatting (an anonymous caller can pre-register a victim's email as pending, blocking their real registration; limited by 5/min rate limit), and unbounded pending rows.

Who should see this next: Kohl for F1 (decide whether /cass/disagreements?user_id should be owner-only); test-runner for F2 tests.
