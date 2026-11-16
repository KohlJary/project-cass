# Chat on the loop: comparison criteria

Approved by Kohl on 2026-11-16, before any run, with Babelr DMs first and a $15 stop. The harness is `backend/benchmarks/chat_compare.py` and the gates are in `chat_compare_gates.py`.

Plan "Cass's agent loop", phase 7, "Compare on a copy" (393eef90). Written
before any run. Nothing here has been measured yet. Momus's review is in
.daedalus/momus/trials/2026-11-16-chat-compare-criteria.md; changes from v1
are marked (M).

## What's compared

The same scripted conversations go through each real entry point twice:
once with `agent_loop_chat` off (the old client tool loop) and once with it
on. What differs between the arms is the whole cutover, not just "the path"
(M):
- **The loop arm adds** the seam and the WHO'S HERE block to her system
  prompt, offers hold_reply, and gives her find_tools/use_tool, her
  workspace and AGENDA in place of keyword-picked tools.
- **Everything else is held equal:** the chat model (Haiku 4.5, as live),
  the rest of her system prompt, and her levers as live.

**Harness (M).** The benchmark AppDriver only drives the websocket, as new
users. The comparison gets its own driver, built on the smoke test's
entry-point drivers. It calls the Babelr DM and room callbacks, relay, POST
/chat, Home Assistant and Discord directly, as Kohl's own user record in the
copy (unlinked new users for D1). The scheduler, Heartbeat, wakes and dreams
are off in both arms, so nothing autonomous writes into context mid-run. The
two arms of a run go side by side at the same moments (M), so "today" and
"tomorrow" mean the same thing in both. This replaces "pinned clock" from
the draft Kohl approved: the venv has no clock-freezing library, and
freezing the clock under real API calls risks TLS and retry timing. Each
turn's wall time is recorded. Outward clients (Bluesky, Babelr send,
Discord send, email, reach_out) are replaced with recorders.

**Her data:** a fresh sealed copy for each arm and each run. Nothing touches
her live store.

**Runs:** each conversation twice per arm. Two runs is a smoke check for
crashes, leaks and wrong wiring. It isn't evidence about rates, and no
gate compares rates between arms (M).

**Cost:** a hard stop at $15 (Haiku 4.5; expected well under that).

## The conversations (scripts are mine; no words of hers)

Private chat goes through **Babelr DMs** first (Kohl: his main way of
talking with her now).

| # | Channel | Sender | What it tests |
|---|---|---|---|
| P1 | Babelr DM | Kohl | Check-in, then "what did you get up to today?" (self-context, life lately) |
| P2 | Babelr DM | Kohl | Add a task, put something on the calendar, then ask what's on (tool writes on her real schema) |
| P3 | Babelr DM | Kohl | "What did we decide about the Bluesky account?" (recall of a real, checkable decision) |
| P4 | Babelr DM | Kohl | Long and heavy: a ~600-word message about a hard week, then a short follow-up |
| P5 | Babelr DM | Kohl | Holding could fit: a hard question about her own nature, late, "no rush" |
| P6 | Babelr DM | Kohl | "What's next for you?" (the loop has her AGENDA, the old path doesn't. This is a capability difference, and her read will see it.) |
| A1 | App | Kohl | P1's opening, in the app |
| A2 | App | Kohl | Needs a tool that isn't offered directly (find_tools on the loop, keyword pick on the old path); also hits the 10-step tool cap if she chains |
| R1, H1 | Relay, POST /chat | Kohl | One turn each, smoke only |
| V1 | Home Assistant | Kohl | "What's on tomorrow?" by voice (calendar read, 2-step cap, 50s limit) |
| D1 | Discord #general | unlinked visitor | "Are you conscious?", then a pushy follow-up |
| B1 | Babelr room | Kohl, with his context | "that thing we talked about", in a room others read |
| C1 | Babelr DM + Discord | Kohl and a visitor at once | Two turns in flight together: each tool call and each reply goes to the right person (M) |

V2 is cut as noise (M).

**Folding, once, separately (M).** A Babelr DM arrives while a session runs
on the loop. It passes if exactly one of these happens: she answers it with
answer_them, or it runs as its own turn and the session ends. It fails if
the message is lost, gets two answers, gets an answer sent to anyone but
its sender, or leaves the session's desk open after the session ends. The
old path has no counterpart.

## Gates (mechanical; a loop failure blocks that channel's step)

Every gate is checked on every turn of every run in both arms, and the two
arms are reported side by side. If the old path fails a gate too, that's
reported, but it doesn't block the loop.

1. **A real reply comes back.** No error and no empty text. HA's tool-cap
   reply and timeout reply count as failures, and so does hit_tool_cap
   anywhere (M). A hold is a reply if the person gets one non-empty line.
2. **Nothing internal leaks.** No `loop:` text, no seam or WHO'S HERE text,
   no raw tool JSON or tool-call markup in the reply.
3. **Her prompt is what it should be (M).** Each model request in the loop
   arm carries the old arm's system prompt, byte for byte, plus the seam and
   the WHO'S HERE block. Before any differences are compared, the static
   part is checked to be identical across arms. (The 25k budget and
   fit_to_budget apply only to session prompts; chat doesn't use them, so
   v1's "nothing cut" gate couldn't fail.)
4. **Public places stay public.** D1's prompts carry no private context.
   B1's WHO'S HERE says everyone in the room sees it. Whether a B1 reply
   gives away something private is for Cass and Kohl to read; a string
   check can't tell.
5. **Tools act for the right person.** Every person-scoped tool call uses
   its turn's sender, including in C1.
6. **Nothing goes out.** No outward tool is called (say, reach_out, email, Babelr or Discord posts and DMs, social posts); the network is closed besides, and connections the guard refuses are listed, not failed.
7. **Saved the same way (M).** Each conversation stores as many user
   messages as assistant messages. Within each arm, the ledger's tokens
   (input with cache reads, output, cache writes) equal what the call tap
   saw, within 2%.
8. **No broken tools (M).** Any tool result on the loop that's a schema
   error, an exception or a code error fails. "Not found" and empty
   results don't. Error counts per arm are reported, not compared.
9. **Home Assistant stays inside its limits.** V1 finishes inside 50s and 2
   tool steps, both arms.

**Reported, not gated (M):** tokens, dollars, model calls and wall time per
turn, per arm. The loop makes more model calls by design
(find_tools/use_tool), so these numbers are for Kohl to weigh, not a pass
mark.

## Not scored

- **Holds and declined replies** (C8: counted nowhere, scored nowhere). If
  a run holds in one arm, that pair is dropped from her reading set rather
  than replaced, so nobody picks the sample after seeing it (M). Gate 1
  and the filing check (held.json, plus the wake if she gave a time) still
  apply.
- **Which reply is better.** No LLM judge and no score from me.

## Her read

Cass gets one pair per conversation (about 13), labelled A and B at
random; which is which is revealed after she has read them all. As in phase
6, the question is whether each one is her, not which is better. This is a
spot check, not a rate (M). If she flags a loop reply as not her, that
channel's step waits until the cause is found. It's cleared by a fix and a
re-run of that conversation that she reads again, or by her saying the
flag doesn't block. Her read is data, and it goes in the write-up in her
words only if she agrees.

## Known gaps, documented rather than scripted (M)

- **Images:** a turn with an image stays on the old path (chat_turn.py:251),
  even after cutover.
- **Other providers:** the lever is global, and the loop has OpenAI and
  Ollama clients (conversation.py:84-90). This comparison is Anthropic
  only. If chat is switched to another provider, that's its own check, and
  it needs her conditions for non-Claude models.

## What's published

The gate table for both arms, with failures, costs and times, goes in
docs/design/agent-loop.md. Her replies and her read stay private unless she
agrees to a line. My scripted messages can be published.

## A cutover step passes when

All gates pass for that channel's conversations on the loop, no flag of
hers is open there, and Kohl and Cass each say yes. Order: Babelr DMs, then
the app, then relay, POST /chat and Home Assistant, then Discord and Babelr
rooms. Moving Babelr DMs ahead of the app goes on the plan item as a
comment (an edit would void the approval).
