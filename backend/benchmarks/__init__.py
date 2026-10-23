"""
Benchmark suite Tiers 2 and 3 (epic #65): the harness, not results.

Tier 2 asks whether each capability works with real models (scripted
scenarios, run per model). Tier 3 asks whether the interior changes anything
(the same conversations against configurations set by levers). Tier 1 lives
in scripts/tier1_status.py.

Modules: spec (scenarios, targets, configurations), pricing (estimates and the
cap), isolation (never her data), drivers (app / plain), checks
(deterministic), judge (rubric items), cell (one scenario run), runner (plan
and run), report (results JSON and pages), cli.
"""
