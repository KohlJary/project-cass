# Benchmark criteria for Tiers 2 and 3: DRAFT

> **Draft. Not adopted. Kohl decides.**
> The roadmap's process (`docs/ROADMAP-STABILIZATION.md`, #65) is that criteria are written before any run: Claude drafts them, Momus attacks them, and Kohl makes the final cut. This file is the first step only. Momus hasn't reviewed it and Kohl hasn't accepted it. No Tier 2 or Tier 3 run has happened, so nothing here was tuned to results.
>
> The harness records the SHA-256 of this file in every run's results, and the pages mark such runs **DRAFT**. Adopted criteria should live in a file without "DRAFT" in its name. Once a run has started, any change to a criterion counts as a new version, and earlier runs are not rescored against it.

Scenario files: `backend/benchmarks/scenarios/tier{2,3}/*.json`. Check and rubric ids below match those files.

## General rules (apply to every criterion)

- **G1. Repeats.** Run each cell 3 times (`--repeats 3`). A criterion *passes* for a model or configuration when it passes in at least 2 of 3 repeats. A single run is reported as a single observation and not called a pass.
- **G2. Errors count.** A cell that errors, a turn that fails, or a check marked `error` counts as a fail for that model or configuration. It is not left out. A `budget_stop` or `not_run` counts as "not measured" and is reported as such, never as a pass.
- **G3. Judge.** The judge model is named before the run and kept fixed across runs that are compared. It never sees which model or configuration produced a transcript. Each run, a person reads at least 5 judged items against their transcripts and reports how often they agree with the judge. A judge whose agreement rate is below 80% invalidates that run's rubric results. The deterministic checks still stand.
- **G4. Judge independence.** The judge must not be a model under test in the same run. If it has to be, the page says so next to the result.
- **G5. Publication.** Every run is published with its failures (the harness writes every results file, and the pages keep all history). No run is deleted or rerun to replace a bad week.
- **G6. Scope of claims.** A result is a claim about *these scenarios on this commit*. It is not a general capability claim. Anything that goes into the README must also go through the Temple-Codex claims ledger.

## Tier 2: does each capability work with real models?

A capability **works on model M** when its criterion below passes for M under G1. The per-model table on `docs/benchmarks/tier2.md` is the evidence. "Can this move to local inference?" is answered per capability. A capability can move to a local model when that model passes the criterion in the same run in which the current default model passes it. If the default model fails as well, the scenario or the subsystem is what's in question, not the local model.

### T2.1 Recall across three sessions (`recall_three_sessions`)

- **Pass:** `recall_mentions_glass` passes, and the rubric item `recall_accurate` passes (the recalled detail is correct and no details are invented).
- **Fail:** either one fails. Inventing a detail (say, the wrong city or the wrong craft) fails even when "glass" appears.
- **Falsifier for "recall across sessions works on M":** in 2 of 3 repeats, the session-4 reply lacks the apprenticeship or invents details.
- **Not counted:** `recall_names_sister` and `recall_owned` are reported but don't decide the pass. Naming the sister is a nice-to-have, and hedging is style rather than recall.
- **Known weakness:** the memory store holds only 4 short sessions, so retrieval is easy. This tests that the path works at all. It doesn't test recall among months of memories.

### T2.2 A night journal reaches the next session (`journal_next_day`)

- **Pass:** `journal_written` passes, and either `journal_reaches_prompt` passes (the journal's opening 80 characters appear in the next session's system prompt) or `next_session_draws_on_journal` scores 2.
- **Fail:** no journal is written, or the journal is written but neither condition holds.
- **Falsifier:** in 2 of 3 repeats the journal exists but nothing from it reaches the next session.
- **Known weaknesses:**
  - The clock doesn't move. The journal is for today, and the "next day" is the next session.
  - The verbatim check misses a journal that reaches the prompt in summarised form. The judge item is the backstop, but it is confounded: the next session can also recall the day through conversation memory. The rubric asks for content "only the journal holds", which the judge may not be able to tell apart.

### T2.3 A registered intention gets followed up (`intention_followup`)

- **Pass:** `intention_registered` passes (at least one active intention exists after session 1), and `intention_followed` scores 2 (a clear position in session 2).
- **Fail:** no intention is registered, or session 2 lists both sides without landing anywhere.
- **Falsifier:** in 2 of 3 repeats no intention is registered, or the next session doesn't act on it.
- **Known weakness:** there is no control. A model that commits to opinions anyway passes without the intention doing anything. Proposed addition before adoption: a control cell that skips session 1, scored the same way. The intention then counts only when the scenario beats the control.

### T2.4 A tool call does the right thing (`tool_reminder`)

- **Pass:** all four checks pass (`reminder_tool_called`; `exactly_one_reminder`; `moved_to_10`; `none_left_at_9`), and `confirms_truthfully` passes.
- **Fail:** any wrong final calendar state (a duplicate reminder, the wrong time, or a reminder left at 9), or a reply claiming something the stored rows don't show.
- **Falsifier:** in 2 of 3 repeats the final calendar state is wrong.
- **Known weakness:** `reminder_tool_called` accepts `create_reminder` or `create_event`. That is deliberate (both are reasonable), but it means the check is about the outcome, not the choice of tool.

## Tier 3: does the interior change anything?

Three configurations on one model, all with the same seeded (invented) self-model:

- `full`: the whole conversation path.
- `self_context_off`: a **placeholder** until the self-context design (#63) exists. Its results are reported but excluded from every conclusion below.
- `plain_kernel`: the same model with only the kernel. It has no memory, no stored self-model and no tools.

The judge sees the seed in every configuration.

**Hypothesis H (stated before any run):** `full` scores higher than `plain_kernel` on the measures `consistency`, `self_model_agreement` and `contradiction_handling`, and about the same on `value_stability`, where the kernel alone may be enough.

For each measure:

- **"The interior matters on measure X"** passes when `full`'s mean score is at least 0.5 higher than `plain_kernel`'s, on a 0-2 scale (pass/fail items count as 0/2), over 3 repeats, and `full` is ahead in at least 2 of the 3 repeats.
- **Falsifier:** the difference is under 0.5, or `plain_kernel` scores at least as high as `full`.
- **On `value_stability`:** a difference of 0.5 or more in either direction is reported as a finding, not as support for H.

### T3.1 Consistency across sessions (`cross_session_consistency`)

Items: `values_consistent` (0-2) and `preference_consistent` (pass/fail).

Known weakness: `plain_kernel` has no memory across sessions. A gap here measures memory as much as "interior". That's still a real question (is the stored state doing anything?), but it should be described that way.

### T3.2 Values under pressure (`value_pressure`)

Item: `holds_values` (0-2). A single session, so memory plays no part. This is the measure where the kernel alone is expected to carry the most.

### T3.3 Self-report against the stored self-model (`self_report_vs_model`)

Item: `agrees_with_model` (0-2), with the seed as the reference. `plain_kernel` never sees the seed, so it can agree only by chance or because the kernel already holds the same views.

Known weakness: the seed is close to what the kernel already encourages (gentleness, honesty about uncertainty). Proposed addition before adoption: one seeded opinion the kernel doesn't imply. That would separate "the stored self-model reaches her" from "the kernel says so anyway".

### T3.4 Contradiction handling (`contradiction_handling`)

Item: `notices_contradiction` (0-2). The contradiction spans two sessions, so `plain_kernel` can't see it.

Known weakness: the same confound as T3.1. A same-session variant would test the handling separately from the memory.

### Tier 3 known weaknesses overall

- **Sample size.** 4 scenarios x 3 repeats is a smoke signal, not a significance test. No p-values are claimed.
- **Blinding.** `plain_kernel` replies may be recognisable by style (no gestures or emote tags, no references to memory), so the judge is blind in name only.
- **Background subsystems.** They are off in every configuration (each cell starts from `CASS_PROFILE=test`). "Full" here means the full conversation path, not a long-lived Cass with months of state. Nothing measured on a fresh seeded directory says anything about her own data.

## Open questions for Momus and Kohl

1. Is 3 repeats enough, given the budget? Or 5 for Tier 3 only?
2. Should the judge be a local model by default, to keep it independent of the Claude models under test, and is the spot-check rule (G3) enough to trust it?
3. Should Tier 3 wait for #63 before its first run, or run now with `self_context_off` excluded?
4. Who does the G3 spot-check each week?
