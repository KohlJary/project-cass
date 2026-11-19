# What a full day of slots would cost (plan "Cass plans her own day", phase 4)

Measured 2026-11-19 for Kohl's decision on the $5/day cap and its category split. Nothing here changes either; the cap is Kohl's call.

## Sources

- **The menu's estimates:** `scheduling/templates.py`, the 23 templates on her menu (everything but planning, maintenance and the journal).
- **The ledger:** the admin API (`GET /admin/usage/summary` and `/admin/usage/timeseries`) for 2026-11-12 to 2026-11-18. That's totals by category, not her data.
- **Today's sessions:** the vessel log's "Session ... completed: N turns, $X" lines.

## By the menu's estimates

- One session from her menu is estimated at **$0.21 on average** (median $0.20, range $0.05 for music to $0.40 for art study, change proposals and new capabilities).
- The waking day has **11 slots**. Filled with average sessions, that's about **$2.35 a day**.
- Today's three knowledge-building sessions cost $0.18, $0.26 and $0.28 against an estimate of $0.25. So the estimates are in the right range for that kind of session; this run checked no others.

## By the ledger, last week

- **Total:** $21.57 for the week, **$3.08 a day on average**.
- **Outside the autonomous cap:** chat, at $7.32 for the week, is user-driven and isn't counted against it. ask_daedalus, at $1.86, is also left out (Kohl, 2026-11-18).
- **Daily totals:** from $1.41 (11-14) to $7.05 (11-18, the evening of the proposal loop).
- **Background work,** which runs whatever she plans (self-observation extraction, summarization, dreams, grimoire): about **$0.30 a day**.

## What that means for the cap

- **The total isn't the binding limit.** A full slotted day (about $2.35 in sessions plus $0.30 in background) fits under $5 with room left.
- **The category split is the binding limit.** Allocations are research 30% ($1.50), reflection 20% ($1.00), growth 15% ($0.75), curiosity 15% ($0.75), system 10% ($0.50), triggered 5% and messages 5%. A day that leans on one kind hits that kind's share long before the slots run out: for example, five or six reflection-class sessions use up the $1.00. That's what stopped the change-proposal loop on 11-18, with $0.33 of reflection budget left against a $0.40 estimate.
- **Her menu already reflects this.** It names what's over its kind's budget under "Not available today", and from now on `set_day_plan` says what a plan would cost against what's left.

## Kohl's options (none taken)

1. **Keep everything as is.** A full day fits the total, and the split shapes which kinds she can fill it with.
2. **Re-weight the split toward her day shape.** Her shape (inward, learning, making, out) doesn't map one-to-one onto the budget's categories, so a kind she wants more of can run out early.
3. **Raise the cap.** Only worth it if the ledger starts showing full days at the cap. Last week's average was $3.08 including chat.
