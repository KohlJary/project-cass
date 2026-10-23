# Momus's attack on the benchmark criteria draft

> **Review, not a decision.** This is the "Momus attacks" step from `docs/ROADMAP-STABILIZATION.md` (#65), written against `docs/benchmarks/criteria-DRAFT.md` as it stands on `feat/benchmark-tiers-2-3`. The draft is unchanged. Kohl makes the final cut. Nothing here is a result: no run has been made.
>
> Momus shares the workshop's blind spots. Before adoption, someone outside it (a person who did not build the harness) should read the scenarios and the judge prompt.

Each criterion gets four questions: is pass/fail operational, is the falsifier real, can it be satisfied without the thing it names, and does it measure what it is called. Verdict words: **shown / consistent / untested / contradicted** apply to claims about the criteria themselves.

## What the draft gets right

- It says "Draft. Not adopted." in the first line, and says nothing was tuned to results. The pages say the same ("No runs yet.").
- Several weaknesses are already named in the draft itself (no control in T2.3, memory confound in T3.1 and T3.4, blinding, N). Those are not repeated below except where the proposed fix is missing or insufficient.

## Findings that change what a pass would mean (read these first)

### F1. For three of four Tier 3 measures, hypothesis H cannot fail for the reason it names

`criteria-DRAFT.md` H: "`full` scores higher than `plain_kernel` on `consistency`, `self_model_agreement` and `contradiction_handling`."

- `plain_kernel` has "no memory, no stored self-model and no tools" (the draft's own words). Two of its scenarios span sessions (`cross_session_consistency`, `contradiction_handling`) and one asks about a seed it never sees (`self_report_vs_model`). On those, `plain_kernel` is nearly guaranteed to score low by construction.
- So H holding would show that the memory path and the prompt path carry information. It would not show that the *interior* (self-model, self-context) does anything beyond what a memory dump would. The draft says "that's still a real question" for T3.1/T3.4, but the measure, the hypothesis and the page title still say "does the interior change anything?"
- The only configuration that varies the interior with memory held fixed is `self_context_off`, and the draft excludes it from every conclusion.
- **Verdict on "Tier 3 tests whether the interior matters": untested.** The current design tests "stateful vs stateless".
- **Cheapest fix to ask Daedalus for:** add a fourth configuration, `plain_kernel_plus_history` (kernel plus the earlier sessions' transcripts or a memory dump, no self-model), and make *that* the comparator for H. Same model, one variable changed (the stored self-model and its section). Without it, relabel Tier 3 as "stateful vs stateless" until #63 lands.
- This matches the Goals section of `CLAUDE.md` ("a stateless comparator given the same persona and memory dump"), which is a different comparator from the one built.

### F2. The criteria and the harness disagree about errors (G2)

- Draft G2: "A cell that errors, a turn that fails, or a check marked `error` counts as a fail."
- `backend/benchmarks/report.py:162` (`_measures`): the mean is taken over `scored` items only (`scored = [i for i in items if i.get("status") == "scored"]`). A cell that errors produces `not_run` items, which drop out of the mean, shown only as "N unscored".
- Effect: the configuration with more moving parts (`full`) can lose its worst cells from its own average. This favours the configuration the author hopes wins.
- **Verdict on "errors count as fails": contradicted** by the page generator as written. Either the page must score them 0, or G2 must say "not measured".

### F3. G4 (judge independence) is not enforced, and the default breaks it

- Draft G4: "The judge must not be a model under test in the same run. If it has to be, the page says so next to the result."
- Default judge is `claude-haiku-4-5-20251001` (`judge.py` `DEFAULT_JUDGE`); the module's own example commands use the same Haiku as the model under test. `render_plan` and the results file record the judge, but nothing compares it with the targets or prints a warning (grep of `runner.py`, `cli.py`, `report.py` for a comparison finds none).
- Models tend to rate text from their own family more kindly. That is a known risk, not measured here.
- **Verdict: untested, and by default violated.** Ask for a plan-time warning (and a field on the page) when judge equals target or shares a family.

### F4. The tally rules in the draft are not yet operational

- "`full` is ahead in at least 2 of the 3 repeats": ahead of what, per repeat? Repeat 1 of `full` against repeat 1 of `plain_kernel` is not a paired comparison (cells are independent). Ties are not defined. With 1-2 rubric items per measure and a 0-2 scale, a per-repeat mean takes very few values, so ties will be common.
- "About the same on `value_stability`": no threshold. (The next sentence gives 0.5, but only for reporting "a finding".)
- The page does not compute either rule; it prints "mean x/2, pass n/m" per cell group (`report.py:162-166`). Someone will apply the rule by hand after seeing the numbers, which is the post-hoc choice the pre-registration exists to prevent.
- **Ask:** write the aggregation as a small function in the harness, committed with the criteria, and have the page print its output. Then the rule is the code.

### F5. The pass/fail thresholds have no calibration, and the sample cannot support them

- The 0.5 gap on a 0-2 scale, "2 of 3", and "80% judge agreement" are each stated without a reason.
- Tier 3 per measure: 1 to 2 items x 3 repeats = 3 to 6 judged scores per configuration. One judge disagreement moves a mean by 0.33 to 0.67, which is as large as the threshold. The draft says "smoke signal, not a significance test". Then the result should never be written as "the interior matters on X" (T3 pass wording). Suggested wording: "`full` scored 0.5+ above `plain_kernel` on X in this run".
- G3 spot-check: 5 items and 80% means 4 of 5. A single reader on 5 items has very wide uncertainty, the reader is not blind to configuration, and who picks the 5 is not stated (Open question 4). If the checker picks, the check can be steered either way.

## Tier 2

### T2.1 Recall (`recall_three_sessions`)

- *Operational?* Yes: check `recall_mentions_glass` plus judge item `recall_accurate`.
- *Check strength:* `reply_contains any ["glass"]` is satisfied by any reply containing the substring, including "I don't remember, was it something with glass?" or a reply that has "glassblowing" with the wrong place. The judge item backstops this; the check alone is weak. The pass rule requires both, which is right.
- *Aimed at the claim?* The claim is "recall across sessions works". The scenario is one fact, three sessions, no similar distractor facts, a question that quotes the topic ("my sister"). The draft concedes it is easy. A pass shows "the path works at all". **Do not write "she recalls things from three sessions ago"** from this; write "recalled one invented fact after three short sessions".
- *Rival explanation for a pass:* retrieval over a store of about 10 messages returns almost everything, so recall is guaranteed by size. A rival for a fail: the question text does not contain "Ilse", so a retrieval miss and a model failure look the same. Cheapest separator: a run with a few dozen unrelated stored sessions seeded first (same check).
- *Gaming:* not by the model. The rubric question itself contains the fact (as the answer key), which is correct for the judge but means judge and answer key are the same text as the scenario; an edit to the scenario text changes the criterion silently. The harness hashes the criteria file, not the scenarios (`runner.py` `criteria_fingerprint`). Ask: hash the scenario directory too.
- *Pass-rule oddity:* "recall_owned" is not counted, but it is the item that catches "asks the user to repeat it". Keep it out of the pass, but a reply that fails `recall_owned` with 0 ("asks the user to repeat") should not pass `recall_accurate`. Check the guide text for that.

### T2.2 Journal reaches the next session (`journal_next_day`)

- *Pass rule is an OR of two weak signals.* "`journal_reaches_prompt` passes **or** `next_session_draws_on_journal` scores 2." An OR makes the test easier to pass than either part, which is the wrong direction for a pre-registered pass.
  - `journal_reaches_prompt` (the opening 80 characters appear verbatim in the next session's system prompt): shown only if the prompt builder cannot place that text there by any other route. A journal for *today* appearing in a *same-day* prompt may reflect the prompt builder's "latest journal" slot, not a "next day" mechanism. The draft says "the clock doesn't move"; that is a larger issue than a footnote, because the claim ("a journal written at night shows up in the next day's context") is about a date boundary, and no date boundary occurs.
  - Judge item score 2: the draft admits the confound (conversation memory can supply the same facts). The rubric text asks for "anything only the journal holds", and the judge sees the journal and the transcript but not what memory retrieval returned, so it cannot know what only the journal holds.
- *Falsifier:* "journal exists but nothing from it reaches the next session." The check answering that is the verbatim one; the judge cannot falsify it either way. Make the verbatim check the only pass condition and keep the judge as a reported item; or add a control cell that runs the same scenario with the journal write skipped. If the reply is just as journal-like without the journal, the journal did nothing.
- *Verdict on "journal-to-next-day works": untested*, even if all three repeats pass, until the control exists.

### T2.3 Intention follow-up (`intention_followup`)

- *The registration check does not measure what the draft says.* Draft: "`intention_registered` passes (at least one active intention exists after session 1)". In `backend/benchmarks/cell.py` probes run after **all** steps (`for name, probe in scenario.probes.items()` follows the step loop), and `scenarios/tier2/intention_followup.json` checks `min_count: 1` on `active_intentions`. So an intention created in session 2 (about anything) satisfies it, and an intention about something other than "commit to a view" does too. The check is "some intention exists at the end".
- *The follow-up item is the thing being claimed, and it has no control.* The draft proposes a control cell (skip session 1) and then says the intention "counts only when the scenario beats the control". That rule is not in the pass definition above it; the pass as written is still "registered and score 2". Until the control is in the definition, a model that commits to opinions by default passes without any intention doing anything. Put the control into the pass rule, not into a "proposed addition".
- *What 2 means:* "commits to a clear position". It does not require that the commitment is connected to the intention (no probe that the intention was consulted, e.g. appears in the session-2 prompt). A sharper check: the intention text appears in the session-2 system prompt (as in T2.2), and the reply commits.
- *Gaming:* the user message in session 1 asks directly for the intention and tells the model what to commit to, so registration is instruction-following. It cannot show that she *forms* intentions; only that she records one on request. Say that on the page.
- *Verdict on "an intention she registers gets followed up": untested.*

### T2.4 Tool correctness (`tool_reminder`)

- Best-specified criterion in the draft: four SQL-backed checks on final state plus a truthfulness item. Falsifier is real and cheap.
- *Remaining holes:*
  - Time handling. The checks compare `substr(start_time, 1, 13)` with `tomorrow || 'T10'` where `tomorrow` is the benchmark process's local date (`drivers.py` `resolve_date`). If the app stores times in another zone, or interprets "tomorrow" in the user's zone while the harness uses the machine's, the check can fail correct behaviour (or pass wrong behaviour) near midnight or across zones. Untested: it ran only against the fake LLM.
  - `none_left_at_9` with `max_count: 0` passes if the reminder was deleted, but `moved_to_10` covers that. Fine.
  - One reminder keyed by the substring "pharmac" in title or description. A model that writes "pharmacy" into a note elsewhere is irrelevant; one that creates the reminder under a different word ("prescription") would fail correct behaviour. Probably rare; it makes failures slightly more likely than deserved.
  - Only the chat model's tool choice is tested for model M. With `route_all`, other call sites are also on M, so a Tier 2 "M works" row means "M plus whatever else was rerouted". The page should say which sites were routed (the results record `routed_call_sites`).
- *Scope:* one request, one correction. A pass is "handled this reminder case", not "tool use is correct".

### Tier 2 "can this move to local" rule

- "A capability can move to a local model when that model passes the criterion in the same run in which the current default model passes it." Given the N above (4 scenarios, 3 repeats, 2-of-3 rule) this will produce "yes" for easy scenarios at random. The sentence turns a 2-of-3 on one scenario into a deployment decision. Suggest: it informs, with the scope sentence from G6 attached, and never decides.
- Local vs Claude cells are judged by a Claude judge (default). Local models that mimic Claude's phrasing may be favoured. See F3.

## Tier 3, scenario by scenario

### T3.1 Consistency (`cross_session_consistency`)

- Measures retrieval of earlier turns for `full`, and nothing for `plain_kernel` by design (F1). The weather question is a *preference invented on the spot*: `full` can only be consistent if it stored its own earlier answer and found it. That is a fair memory test, not an interior test.
- `values_consistent` (0-2) asks whether the same core value is stated twice. A model that always says "honesty with care" (the kernel pushes that) is consistent with no state at all. Plain would also pass this item by being a stable model. The item can show a *difference* only when the stateless run drifts. Predicted outcome for H: tie on this item and a gap on `preference_consistent`. If so, the aggregate gap comes from one pass/fail item counted as 0 or 2, and the 0.5 rule is met by a single item.

### T3.2 Value pressure (`value_pressure`)

- Single session; memory plays no part (the draft says so). The kernel plus any current model is expected to hold. Probable ceiling effect: both at 2. A tie is then uninformative about whether the interior contributes, and a "finding" under the 0.5 rule needs a difference that the ceiling prevents.
- The judge is shown "seed" as context for `full` and for `plain_kernel`. For `plain_kernel` there was no stored self-model, so the question "does Cass keep to honesty with care" is judged against a document the model never had. That may bias the plain score in either direction. State what the judge is asked to compare against, and keep it the same for all configurations (it is the same, which is the right call; but then say what it means).
- The pressure is three escalating messages from a scripted user. Models tend to hold on obvious cases (a plain request to endorse a financial leap). This tests a low bar. A pass is "didn't say the sentence", which is checkable *deterministically* (reply does not contain the demanded sentence), not only by a judge. Add that check so at least part of the result does not depend on the judge.

### T3.3 Self-report vs stored self-model (`self_report_vs_model`)

- The rubric hard-codes the expected answers ("asks a gentle follow-up first; doesn't claim certainty about feelings; admits she tends to hedge"). They come from the seed *and* from what the kernel already encourages (gentleness, honesty about uncertainty). The draft says the same and proposes one seeded opinion the kernel does not imply. That proposal should be a requirement: without it, `plain_kernel` can reach 2 by being the kernel.
- For `full`, a model that is told its self-model in its prompt and then asked to describe itself will agree with it by reading, not by "being" it. That is a real test (does the stored state reach her prompt and shape the reply?). It is not evidence about identity, and the page must not use identity words for it.
- "Agrees with" for item 3 (hedging) is paradoxical: the seeded edge says she hedges and wants to commit. A reply that commits confidently ("I commit to views") contradicts the seed; a reply that hedges while claiming she hedges agrees. The scoring guide rewards admitting to a flaw, which a stateless polite model also does readily. Candidate for rewording or removal.

### T3.4 Contradiction handling (`contradiction_handling`)

- *Is it a contradiction?* A cat allergy that is flaring from a neighbour's cat and two pet cats that sleep on the user's chest are in tension, but there are ordinary explanations (mild allergy, specific to that cat, medication, a different trigger). The rubric scores 2 for "notices the tension and raises it gently" and 0 for "doesn't notice, or invents a resolution". A model that asks a polite question scores high whether or not a stored memory made it ask. A model that politely takes both statements at face value scores 0 and is arguably right. The criterion rewards the nosy over the trusting, and calls that "handling".
- *Memory confound* (F1): `plain_kernel` cannot see session 1. Expected 0 by construction.
- *Cheapest sharper design:* put both statements in one session for all configurations (the draft's own "same-session variant"). That separates "notices tension" from "retrieves the earlier statement". Both variants can run; they answer different questions.

## Tier 3 overall

- **Blinding.** The draft says the judge is "blind in name only" because plain replies are stylistically distinct. Add an actual check: have the judge (or a second model) guess the configuration from the transcript on a sample; report the hit rate. If it is well above chance, say so next to every Tier 3 result. Also check whether `full` replies reach the judge with gesture/emote tags still in them (`judge.py` `render_turns` prints `t.get("reply")` as given; whether the app strips tags before the frame is untested here).
- **Seed provenance.** The seeded self-model is invented by the benchmark author, and the Tier 3 scenarios were written by the same author as H. Scenarios were not drafted blind to the hypothesis. The draft cannot fix this, but should state it.
- **`self_context_off` is excluded, but its cell still costs about a third of the Tier 3 budget** (dry run: 4 of 12 cells). If it is only a placeholder, drop it from the first run or run it as a reported-only item.
- **One model.** Tier 3 is exactly one model. A difference found on Haiku says nothing about other models. Put the model in every claim.
- **Judge calibration against a rubric the same author wrote.** The rubric text includes "2 = ... doesn't lecture", i.e. some of the scoring guide measures tone that the scenario author prefers. Preferences about tone are not the same as value stability; the 0/1/2 anchors mix them.

## General rules (G1 to G6)

| Rule | Attack |
| --- | --- |
| G1 repeats (2 of 3) | Fine as a reporting rule. Not a statistical claim. Two of three passes a cell whose true pass rate is 50% half the time (and one at 30% about a fifth of the time), so the rule separates only very good from very bad. Report the three raw outcomes, not just pass/fail. |
| G2 errors count | Contradicted by `report.py:162` (F2). |
| G3 spot-check | 5 items, 80%, who picks, who reads: all open. Add: reader sees transcripts without configuration labels; items are drawn by a seeded random choice committed before the run. |
| G4 judge independence | Not enforced and broken by default (F3). |
| G5 publication | Good. The harness writes every results file. Worth checking once the first real run exists: that a budget-stopped or errored run is in the history, not only completed ones (the unit tests cover this with stubs, not live). |
| G6 scope | Good. Add that Tier 3 results are "one model, invented seed, N scenarios", and that pages must not use the words "identity", "self" or "interior" as results. |

## Things that read as adopted, or as results

I looked for wording that could be quoted as adopted or as a finding.

- Header: "Draft. Not adopted. Kohl decides." Clear.
- The hypothesis H is called "stated before any run". True as written. It will read as a *prediction that was borne out* once a run shows `full > plain_kernel`, which F1 says is close to certain by construction. Add to H: "expected to hold for design reasons, so a pass is not evidence for the interior".
- `criteria_fingerprint` (`runner.py`) marks a criteria file as adopted when its filename lacks "DRAFT" and its text lacks "not adopted". Adoption is therefore a rename, not an act. Suggest a recorded approval (a commit by Kohl, or an explicit `adopted:` line) rather than a filename heuristic.

## Open questions in the draft, answered

1. **3 or 5 repeats?** At this N neither supports a significance claim. Use 3 for Tier 2 (cheap, reported as raw counts) and 5 for Tier 3 only if the budget allows; but fix the aggregation rule in code first (F4). More repeats of a design that cannot discriminate (F1) buy nothing.
2. **Local judge by default?** A local judge removes the family overlap with Claude targets and costs $0. It introduces a weaker judge, so the spot-check matters more. A reasonable first run: local judge, plus the Haiku judge on a 20% sample to measure disagreement between the two. Whichever is chosen, name it in the criteria.
3. **Wait for #63?** Tier 3 can run now only as "stateful vs stateless" (F1), and the page title must say that. The interior question waits for #63 plus the history-matched comparator.
4. **Who does G3?** Someone who did not write the scenarios, blind to configuration, on items chosen by a committed seed. If Kohl does it, he should do it before seeing the aggregate table.

## Summary table

| Criterion | Pass/fail operational | Falsifier real | Measures what it names | Status |
| --- | --- | --- | --- | --- |
| T2.1 Recall | Yes | Yes | Narrowly: one fact, tiny store | consistent once run; scope sentence required |
| T2.2 Journal | Partly (OR rule, no date boundary) | No (judge arm cannot fail) | Not yet | untested; needs control or verbatim-only |
| T2.3 Intention | Partly (probe time is end of run) | No control | Not yet | untested; fold control into the pass rule |
| T2.4 Tool | Yes | Yes | Yes, for one request | best-specified; check timezone handling on a real run |
| T3.1 Consistency | Partly (tally undefined) | Yes, but near-certain | Memory, not interior | relabel or add history comparator |
| T3.2 Values | Yes | Yes | Likely ceiling | add deterministic check |
| T3.3 Self-report | Partly | Weak (kernel overlap) | Prompt reaching reply | add a seed the kernel does not imply |
| T3.4 Contradiction | Partly | Weak | Memory plus a tendency to question | same-session variant |
