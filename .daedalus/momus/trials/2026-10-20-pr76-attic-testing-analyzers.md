# Momus review: PR #76 (retire A/B, authenticity alerts/ML, temporal metrics)

Verdict: claims hold; one undocumented response-shape change.

1. "Scores unchanged" - SHOWN for the 6 inputs run. Old (14cda8c) vs new (HEAD) testing/ trees, score_response_enhanced on 6 texts, to_dict compared minus temporal_score/temporal_deviation: identical except base_score.id and timestamp. Scope: 6 texts, no timing_data (the only path where old code computed non-neutral temporal values; the only caller, routes/testing/authenticity.py, never passed it).
2. Merges cleanly onto origin/main (ec1d06d, #73-#75): no conflicts. On the merge result, full suite 2707 passed, 22 skipped, 23 xfailed (test_fixture_is_up_to_date included, so the fixture needs no regeneration after #73). Fixture auto-merged correctly.
3. Websocket chat path - SHOWN (consistent with tests that could fail): smoke/test_chat_turn_hazards.py drives real /ws chat turns with a fake LLM through the removed tail section; a leftover NameError would fail them. Remaining tool_iterations_count (websocket_handlers.py:840,911,1034) is still defined.
4. No live references: grep over backend, admin/tui/mobile/godot frontends, scripts, tests for the retired module/class/route names found only the new negative tests. 
5. Finding (minor, undocumented): POST /testing/authenticity/score-enhanced no longer returns "alerts" ({"score","alerts"} -> {"score"}) (routes/testing/authenticity.py ~line 140). PR body lists only temporal_score/temporal_deviation as response changes. No in-repo consumer reads it (grep), so impact is external callers only.
6. Not verified by me: admin-frontend `tsc` clean (no node_modules in worktree); palace.yaml 133-entry removal; the "4 retired paths 404" test does not cover the other ~29 removed routes (route-auth battery just drops them).
7. Weak-test note: test_retired_testing_routes_are_gone would also pass if a catch-all returned 404 for any reason, but it was meaningful before (routes returned 503/200), so it can fail.
