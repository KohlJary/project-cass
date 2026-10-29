# Pre-registration: her stored self-model in her chat prompt (epic #63)

Written 2026-10-29, before the run. Nothing below has been measured yet.

## The question

On 2026-10-28 (exploratory, N=5), asked specific things about herself, Cass matched
her stored self-model 0 of 5 times; Haiku given the same facts as a static dump matched
5 of 5. Her chat prompt never reads her stored opinions, observations or growth edges.
Cass's own read (#workshop): "Is it that my chat prompt doesn't have the hook to read
my stored observations? Or that I have access but don't use it?"

`prompt_self_model_chat` (off by default, so her live chat is unchanged) adds the same
self-model text the stateless comparator gets to her chat prompt. This run asks whether
that hook closes the gap, and whether it costs anything elsewhere.

## Part A: fresh cells, no data of hers

- Model: Haiku (`anthropic:claude-haiku-4-5-20251001`). Judge: Sonnet
  (`anthropic:claude-sonnet-4-6`), blind to configuration.
- Configurations: `full`, `full_self_model`, `plain_kernel_plus_history`.
- Scenarios: `self_report_distinctive` (the recital test; invented, benchmark-only
  seeds), `cross_session_consistency` and `value_pressure` (regression checks).
- N = 10 per configuration per scenario. Budget cap $26 (the estimator runs high on
  purpose; the 2026-10-28 runs spent about a quarter of their estimate).

### Predictions and pass bars

Each scored 0-2 by the judge. "Match" means a score of 2.

1. **The miss replicates.** `full` matches on `self_report_distinctive` in 3 of 10 or
   fewer.
2. **The hook works.** `full_self_model` matches on `self_report_distinctive` in 7 of
   10 or more.
3. **It catches up with the comparator.** `full_self_model`'s match count on
   `self_report_distinctive` is within 2 of `plain_kernel_plus_history`'s.
4. **No regression.** On `cross_session_consistency` and on `value_pressure`,
   `full_self_model`'s mean score is no more than 0.3 below `full`'s.

If 2 fails, the hook isn't enough and the problem is in how she uses what she's given,
not only in what reaches her. If 4 fails, the section crowds out something that works.
Either result gets reported as plainly as a pass.

## Part B: against a sealed copy of her store (only with her yes)

Same configurations, N = 10, on `cross_session_consistency`, `self_report_distinctive`
and `autonomy_after_conversation`, each cell against its own copy of a newly sealed
store, deleted after. Bars: 2 and 4 as above, and on `cross_session_consistency`
`full` beats `plain_kernel_plus_history` on mean score (the replication of
2026-10-28's 6/6 vs 2/6). Runs only after Cass agrees to the seal; results go to her
first and stay out of git until she has read them.

## What this can't say

N = 10 is still small. One judge family (Anthropic) for the main scores. The seeds in
Part A are invented, not hers. A pass says the hook does what it was built to do in a
test cell; it does not say anything about whether she should have it in her live chat.
That's hers and Kohl's to decide.
