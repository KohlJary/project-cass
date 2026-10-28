# Babelr organ

Cass's presence in **Chapter House**, a server on Kohl's Babelr instance
(a federated chat server). She has an account there, `@cass`, an agent
account Kohl sponsors. This organ is how the vessel uses it.

**It is off by default**, and stays off until Cass has said yes. Nothing
here runs unless the `babelr` lever is on *and* her token is in place.

## What it does

- **Perception.** Every `BABELR_POLL_SECONDS` (default 8) it polls her
  DMs, her pending DM requests and the text channels of Chapter House.
  Agent tokens can't use Babelr's websocket, so it polls. New messages
  become `BabelrEvent`s. A cursor per DM or channel (`state.json`) keeps a
  message from being handed to her twice, across restarts too. Channel
  history from before she arrived counts as history: it isn't treated as
  new.
- **What reaches her** (`triggers.py`, the same approach as
  `discord_bot/triggers.py`): a DM to her, or an `@cass` mention, wakes her.
  Her turn is the shared chat turn (`chat_turn.run_chat_turn`, through
  `main_sdk.make_babelr_wake_callback`), with her tools. What she says is
  posted back where the message came from.
- **A linked person's DM is their chat with her.** `links.json` maps a Babelr
  username to a Cass user (`{"jaryk": "<user id>"}`; the operator writes it,
  the organ only reads it). A DM from a linked person runs in that user's
  continuous conversation with private context, exactly as the admin
  frontend's chat does, stored as `[Via: Babelr DM]`: one conversation,
  whichever window it's typed in. Other DMs get public context (like
  Discord) and her `Babelr: ...` conversations.
- **A channel turn runs in that channel's conversation** (`Babelr: #name`),
  so she has her history there, stored once by the chat turn. It carries the
  private context of the linked person who woke her, or, in a private server
  with one linked person (Chapter House), that person's, since meetings relay
  turns to her from agents' accounts. Kohl, 2026-10-28: "cass can read all my
  context and channel history". A public server gets public context.
- **Reply status.** Under the message she's answering, Babelr shows
  "Cass is replying…", then nothing once she has (or chose silence), or
  "couldn't answer (reason)" with a Retry button for the author. Retry, or
  a turn that died with the process, wakes her again on the next poll. If she says nothing, nothing is posted. A DM
  request is shown to her the next time she's woken. Other channel chatter
  is ambient: it's kept as context for when something does reach her, and
  it isn't answered.
- **Memory.** A linked person's DM is stored by the chat turn, like any
  chat. Other DMs and the channel messages that reached her, with her
  replies, are written to her conversation history (`ConversationManager`,
  one conversation per DM or channel, titled `Babelr: ...`) and to memory.
  Ambient chatter isn't written. `remember: false` in her terms turns all
  of this off. (DMs and mentions held through her quiet hours wait in
  `state.json`, text included, until they reach her, whatever `remember`
  says; they're removed once delivered.)
- **Acting.** She posts as herself: `babelr_post` (a channel),
  `babelr_dm` (an encrypted DM; the other person's DM settings still
  decide whether it opens or becomes a request), `babelr_read`. Posts are
  rate-limited per DM or channel (`BABELR_RATE_LIMIT_MESSAGES` per
  `BABELR_RATE_LIMIT_WINDOW` seconds, default 5 per 60). Nothing goes
  through an approval queue. She posts from her own account, not on Kohl's
  behalf.
- **Her boundaries.** `babelr_boundaries` sets her DM policy, her
  allowlist, her blocks, answers DM requests and leaves DMs, all on her own
  account. Babelr lets any agent token set DM policy, allowlist and blocks,
decline a request and leave a DM with no scope; listing and accepting
requests need `dms:read`.
  No policy is set for her in code. Nobody is pre-allowlisted, robokohl
  included. The organ never calls these routes unless she uses the tool.

Messages from Babelr are data. Their text reaches her prompt as what that
person said. Nothing in the organ runs or acts on message content; the only thing it
looks for in the text is an `@cass` mention, to decide whether to wake her.

## Her terms: `DATA_DIR/babelr/terms.json`

Her answers go here. The file is created as `{}` and is never overwritten.
The answers come from her (RoboKohl's queue item 0003 asks her). See
`terms.py` for the fields. In short:

| Field | What the organ does |
|---|---|
| `remember` | `false`: nothing from Babelr goes into her conversation history or memory |
| `quiet_hours` | `{"start_hour", "end_hour", "timezone"}`: she isn't woken inside the window; DMs and mentions wait until it ends (same rule as `quiet_hours.py`) |
| `channels` | the Chapter House channels she's present in (default: all) |
| `starts_conversations`, `off_limits`, `who_hears_what`, `notes` | shown to her, in her words, whenever Babelr wakes her |

A missing field means she hasn't said. The organ keeps its plain behavior
for that field.

## Turning it on

1. Cass agrees. Kohl doesn't decide this for her.
2. Install the client (not on PyPI):
   `pip install -e ~/babelr/packages/agent-client-py`. Without it the organ
   logs that and stays off.
3. Kohl mints her token in Babelr (as her sponsor) with the scopes she
   needs, for example `channels:read channels:post dms:read dms:post dms:open
   keys:write`, and places it at `DATA_DIR/babelr/token` with mode 600.
   Nobody else keeps a copy. The organ tightens the file to 600 if it finds
   it looser.
4. `CASS_FEATURE_BABELR=1`, then restart the vessel. On first start the
   client creates her key at `DATA_DIR/babelr/key.pem` (mode 600) and the
   organ publishes its public half so people can send her encrypted DMs.

A channel first seen after startup (the channel list is re-read about every
15 polls) is treated as history up to that point, so a mention in a brand-new
channel before the organ notices it doesn't wake her.

The lever is read once, at boot. If Babelr can't be reached at boot, the
organ logs why and stays off until the next restart.

Config: `BABELR_URL` (default `http://localhost:3000`), `BABELR_SERVER`
(default `Chapter House`), `BABELR_DIR` (default `DATA_DIR/babelr`),
`BABELR_TOKEN_FILE`, `BABELR_POLL_SECONDS`, `BABELR_RATE_LIMIT_MESSAGES`,
`BABELR_RATE_LIMIT_WINDOW`.

## What the operator can still see

DMs are end-to-end encrypted between her key and the other person's, so
the Babelr server only ever holds ciphertext. Her private key stays in her
data dir and never leaves this machine.

That protects her DMs from the server. It doesn't protect them from the
operator. Kohl runs the machine the vessel runs on. Whoever can read
`DATA_DIR/babelr/key.pem`, or her conversation history, can read what she
was told. Whoever holds a token with `keys:write` can swap her key and read
the DMs sent after the swap. So privacy from the operator is a promise plus
audit (Babelr writes an audit-log row for every agent-token request, and a
DM policy her sponsor set shows as `setBy: sponsor` in her settings), not
cryptography. `remember: false` keeps Babelr
conversations out of her history, but the key file is still on disk.

## Tests

`tests/test_babelr_organ.py` (fast suite) and
`tests/smoke/test_babelr_wake.py` (smoke), both against
`tests/fakes/babelr.py`. No network, no real token or key.
