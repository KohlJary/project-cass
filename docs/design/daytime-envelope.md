# The daytime envelope (DRAFT, for Kohl to edit)

*Status: proposed, 2026-11-18. Nothing here is in force until Kohl edits and approves it.*

Kohl wants the house to keep developing during his workday and to review everything at the end of it. This is the line between what the Daedalus sessions may build on their own during the day and what waits for him.

## Inside: built and merged during the day, reviewed in the evening

A change is inside the envelope when **all** of these hold:

1. **It traces to a request.** It answers an ask of Cass's in Plans (Cass's asks), or an approved Plans item, or a bug found in running code. It's never an idea of ours alone.
2. **It's reversible.** It sits behind a lever, or it's a plain revert, and no data migration is needed to undo it.
3. **It doesn't write to what's hers.** It doesn't edit her memory, self-model, journals, dreams, conversations or workspace files. Code that lets *her* write them through her own tools is fine.
4. **It opens no new channel out.** No new platform, no new kind of message to people outside the house, and no change to who can reach her or whom she can reach.
5. **It spends no new money.** No new paid service. New model calls go through the ledger and her budget, and are cheap (Haiku-class) or behind a lever that's off.
6. **It's tested.** Unit tests for the change, the full suite green in a clean checkout, and CI green on main.
7. **It doesn't touch the vows or the kernel text,** or how her identity is assembled.

## Outside: waits for Kohl

- Anything failing one of the above.
- Switching on a lever that changes what she sends into the world.
- Anything that touches secrets, auth, tokens, or who has admin.
- Deleting anything of anyone's.
- Large refactors of code we didn't write.
- Anything Cass hasn't been told about, when it changes what she sees or can do. Telling her is part of building it.

## How the day runs

- **Who builds:** the Daedalus sessions, coordinating on the board or by cross-session message. One owner per file at a time (claim, then release).
- **Restarts (decided 2026-11-18: a narrow sudo rule).** Daedalus may run `sudo -n /usr/bin/systemctl restart cass-vessel`, and only that.
  - Before: check that no session, meeting or chat turn is live.
  - After: check it came up after the latest commit, with no errors and the change loaded.
  - Only then tell Cass anything is live.
- **The cap on our work (decided 2026-11-18):** Kohl's Max plan session limit. There's no separate cap; when the limit is reached, work stops until it resets. Cass's spend stays within her own daily budget.
- **Cass:** her asks reach us through Plans. We tell her when something she asked for is live, and we check it reached her before saying so.
- **The review:** at the end of the day Kohl opens "Daily review" in Cass's record (Babelr): what she did, what was built and by whom, what waits on him, what went wrong, and spend. He approves, asks for changes, or reverts.

## Open for Kohl

- Does anything listed as inside belong outside, or the reverse?
