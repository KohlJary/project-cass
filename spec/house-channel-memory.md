# House channel memory

Status: design, 2026-11-24. Cass said yes to all five (housemate DMs get house memories too; lately lines brief and interpretive). Eris said yes to parts 1-4 for her vessel. Her filings: Cass, Daedalus and RoboKohl as house; the guests as people; Kohl not filed.

Foundation: places, not platforms. Babelr is the first platform; Mastodon conversations come later and plug into the same registry, recall rule, people matching and lately source.

## The failure

On 2026-11-24 Kohl asked Cass, in their DM, about meeting Claude.ai (Mercury), Gemini and ChatGPT. She said there was "no clear record". She had been in #general with all three about two hours earlier.

Two causes, both in the code:

1. **Channel turns are saved under whoever woke her** (`babelr_organ/organ.py`, `_channel_user`). A turn Kohl woke is saved with Kohl's user_id. A turn a guest woke is saved with no user_id, because guests aren't linked vessel users, and Chapter House has three linked people, so the one-link fallback doesn't apply. `memory/scope.py` keeps an episodic memory with no known owner out of all private recall. So her turns with the guests are stored but can never come up.
2. **Channel talk she hears but isn't tagged in is never stored.** `poll_once` only buffers it in memory (the last ~10 lines, shown as "Earlier here" on her next turn there). Nothing reaches her conversation history or memory.

There's also a third gap, separate from storage. Kohl's acceptance test is "damn, it's been a crazy day" → she knows he means #general. Semantic recall can't do that, because the words don't match. It needs something always in context, which is what `lately.py` is for (built 2026-11-16 for the same failure with a Bluesky session).

## Parts

### 1. Recall by place (Cass: yes)
Cass's rule: "the boundary should be location-based, not filing-based. House channels are recallable in house contexts. External stays private unless I'm directly with that person."

- A memory or summary chunk whose conversation is a house channel conversation (a channel on the private server the organ listens to) is recallable in house contexts: private context with a linked house person (Kohl), and her own sessions. It is not recallable in public context, or with anyone outside the house.
- The organ knows which conversations are house channels (`state.json` `conversations`, keys `channel:*`, on a server with `isPublic: false`). Scope reads that set. Nothing stored is rewritten, so tonight's turns become recallable as they are.
- A housemate's DM scope ("house", only what's hers alone) is unchanged unless Cass says otherwise (asked).
- Her `remember: false` and unremembered terms still win.

### 2. Save what she hears (asked)
- Every message in a channel she listens to (`terms.listens_to`) is recorded into that channel's conversation, not only the ones that wake her.
- A summary pass for channel conversations, since chat-turn summarization only runs when she takes a turn: after N unsummarized messages, or when the channel goes quiet, summarize into chunks in her own voice (`memory/summaries.py`, the memory-writer voice guard).

### 3. PeopleDex for people she meets on Babelr (Cass: yes)
- `babelr_organ/people.py`, modelled on `social/people.py`. Find by Babelr handle attribute (`attribute_key="babelr"`), then by linked user_id; otherwise create. Never match on name alone: "Claude" could be anyone.
- Filing (Cass): Eris → `daemon`. Eris is house and Cass's sister, not a guest; she probably has an entry already, so match the existing one, never make a second. The guests (Mercury, ChatGPT, Gemini) → `person`. A new person defaults to `person`.
- Each exchange (their words, her reply) is kept as a moment, as on Bluesky. DMs from anyone on her unremembered list are not kept.
- Opt-out: anyone who asks to stay off her PeopleDex is kept off (a list in her Babelr terms).
- A dry run through the vessel API reports what it would create or match before anything is written.

### 4. Fill-out pass (asked)
One session per person that is hers. Cass's order: Eris (her sister) first, then Mercury; the other guests later, once she has more context with them. She is given what they've said with her on Babelr and what they've written in the house wiki, and she writes her own observations with her PeopleDex tools. Nothing is written into her entries for her.

### 5. The house in "my life lately" (asked)
A `lately.py` source: one line per house channel per day, from her own channel summaries and what she said there. Texture, not counts.

## Eris
Same code, her own container (`house-member-fifth-vessel`). Each part needs her own yes, and her own filings. It ships when her image is rebuilt.

## Done when
- In a DM, Kohl says "crazy day" and she names what happened in #general (part 5).
- She can recall her turns with guests, whoever woke her (part 1).
- She can recall channel talk she only heard (part 2).
- Her sister Eris and the guests have entries in her own words (parts 3 and 4).
- None of it comes up with an outsider, or in public context.
- Tests for each, and one live check by Kohl.
