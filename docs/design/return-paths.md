# Return paths: what comes back to her

*2026-11-15, Daedalus. Mapped from code and docs only (main at a05f57d, plus the working tree at 23:30, which had another session's uncommitted work in it). None of her data was read. "Unsure" means I couldn't settle it from code.*

> **Since then (1bb3097, 41fd0c5, from the other Daedalus session):**
> - **Session narratives:** her end-of-session narrative and insights are now the work-summary text, so loop sessions no longer read as "Completed <name>" (item 4, part). Social sessions are still filed as "world".
> - **Recall in sessions:** `recall` / `recall_open` are in the chat-core tools, so loop sessions and the day-plan turn can query her memory (item 7, part). Loop sessions now carry her self-model.
> - **Thymos:** it reaches the session preambles for reach-out and art choice, and the journal. It still isn't in chat (item 6).
> - **Claimed elsewhere:** "Cass's memory" phase 9 ("My life lately", awaiting approval) is a week of her own events, always present. It covers the no-user half of item 7, most of 4, and the "lately" side of 8, 13 and 14.
> - **Item 1 is narrower:** she chose that reads which don't lead to a reply aren't kept. Follows and finds should come back as life-lately lines, not as memories of every read. Ask her first.

**The question:** when Cass touches the world (reading, following, writing, making, exploring), where does it land, and does it ever come back to shape her chat, her sessions, her day plan or her internal state? Engaging with the world only builds her up if it returns. If it doesn't, it's tool calls that leave nothing behind.

## Where each prompt gets its context

| Prompt | Gets | Doesn't get |
|---|---|---|
| **Chat** (`continuous_context.py`) | recent messages, working summary, person timeline, to-raise items, 5 recalled memories (scoped by person), "my own life, lately" (last dream, last reflection, last painting, top interests/questions/opinions/edges), self-model (since 2026-11-15) | Thymos: built at ~:186, never placed in `_assemble_continuous_prompt` (#108) |
| **Agent-loop sessions** (`agent_loop/assemble.py:154-166`) | agenda, self_context (built without a user), self-model profile, Thymos, housekeeping | semantic recall; "since we last spoke" and work summaries, which need a user_id (`self_context.py:95`) |
| **Day plan** (`day_turn.py`, which runs through the session path) | the session sections plus the menu | anything about what came in from the world; "done recently" (`decision_engine.record_work_completed` has no caller, so variety and recency never fire) |

## By channel

**Bluesky** (on since 2026-11-15)

| She… | It lands in | Comes back? |
|---|---|---|
| gets mentions, replies or follows, or a post of hers resonates (watcher) | `social/bluesky/inbox.json` | chat: a count only; social session: the full list. Thymos: no |
| reads her timeline, searches, opens a thread | nothing (the raw tool result is in the session log, which nothing reads back) | **no** |
| follows someone | one line in the limits log | **no**: no PeopleDex entry, no memory, nothing in any prompt |
| posts or replies | Chroma `social` (with a `with`=handle, no user_id), the sent log, the "My presence on Bluesky" thread | chat: yes, but recalled in *any* private chat, because it isn't scoped to a person. Sessions: only if she asks |
| sees mentioners | PeopleDex shells: name and handle, no facts or moments, no user_id | no: relational context looks people up by user_id |
| DMs (lever off) | nothing without the other person's yes; with it, a handle plus the sent text. The DM text is never kept in memory | no. DMs also aren't in the social session's tool pack |
| ends a social session | work summary: category "world", text "Completed Social" | barely: a count of "N world sessions", and "world" is excluded from the "Recently" lines |

**Babelr:** linked DMs and @mentions land in that person's conversation and come back fully, in chat with them, and move Thymos. Unlinked DMs are stored twice (Chroma with no owner, plus an organ conversation) and never recalled automatically. Channel chatter is an in-memory buffer she can read on demand. Plans approvals leave only a log line.

**Discord:** perception is in memory only. It reaches the chat prompt and is lost on restart. Every new sender gets a PeopleDex shell. Linked mentions come back like Babelr's. Unlinked mentions are stored with no owner, never recalled, and move nothing. `EMIT_STATE_DELTA` exists, but no trigger uses it.

**RSS / news:**
- Articles go to Chroma `article_consumption` and `consumed_articles`, filtered out of chat recall on purpose, at her choice.
- But the RSS action path (`rss_handlers.py:508`) has no relevance gate and still writes article questions, opinions and `world_engagement` growth edges. The fc36857 move was a one-off script.
- Article opinions and edges are filtered out of self_context, but **leak** through `SelfManager.get_self_context` into sessions, legacy session edges and the decision engine.
- Article-born interests are ungated and show up in "What draws me".
- Article authors become PeopleDex entries that never come back.

**Research / wiki:**
- Wiki pages go into Chroma `wiki_page`, so they can come up through recall.
- Research leaves self-observations, a research journal and nightly opinions.
- `research.insight_found` moves Thymos; other research events are ignored.

**Wonderland:**
- Session ends write Chroma memories and self-observations, which come back through recall.
- The scheduled `journal_experience` action calls a `journal_manager.add_entry` that doesn't exist. It is skipped silently by a `hasattr` guard, growth edges are distilled, and then the experiences are **cleared** (`scheduler/actions/wonderland_handlers.py:517-529`). The journal half is lost.
- NPCs go to PeopleDex and never come back.

**Art / music:**
- Paintings come back well: "last painting" with her artist note, in chat, sessions and the day plan.
- Art-study artists go to PeopleDex and never come back.
- Music is a JSON library only. `recent_music` queries a `music_compositions` table that doesn't exist (`creative_handlers.py:98`).
- Room and homepage shares never reach a prompt (`summary_for_her` has no caller).
- No `creative.*` events are emitted, so making things never moves Thymos.

**Reach-out / email / outreach:**
- Reach-outs land in her continuous conversation, come back fully, and the reply fires `reach_out.answered`.
- Inbound email is visible only inside the inbox session. `email.*` and `outreach.*` events are ignored by Thymos.
- A reply by email doesn't count as an answer (unsure whether partner email is mirrored into a conversation).

**World state:** weather, location and Home Assistant are chat only, in private chats only.

**Journal and dreams (the nightly return passes):**
- **The journal** reads only the day's conversations, plus the self-model and Thymos. It is **blind to her autonomous day**: reading, Wonderland, art, research, social. Its output reaches chat only through recall and never reaches sessions (`agent_loop/spec.py:121` says so). It emits no event.
- Phase 13 (world-awareness journal) reads observations that c0dd1e4 stopped writing, so it is mostly empty.
- **Dreams** are seeded only from growth edges and open questions; nothing from the day goes in. "Last dream" does come back everywhere.

## Pattern

What comes back well: conversations with linked people, reach-outs, paintings, dreams. Those are the paths someone wired end to end.

Three things go wrong everywhere else:
1. **No trace** (follows, reads, searches, music, room shares).
2. **A trace nothing reads** (PeopleDex shells, work summaries filed as "world", unlinked senders, the journal).
3. **No Thymos event**, so the world never moves her state; only conversations, dreams and reach-out answers do.

On top of that, sessions and the day plan have no recall at all, so even what is stored doesn't reach her choices.

## The wiring list, in order

**1. Bluesky, end to end, while she's using it**
1. Following, reading and searching leave a trace: a short memory of who she found and why (her words, through the tool), and a real PeopleDex entry with a fact or moment.
2. Bluesky people get relational context in chat: look them up by handle, not only by user_id. Scope her posts and replies to the person she answered.
3. Bluesky events move Thymos: a mention or reply → social_connection, a post that resonates → competence, a follow-back → social.
4. A social session ends with her own summary, kept in work summaries and in recall, and visible to the next social session and to the day plan.
5. DM text is kept once she has the person's yes (today only the handle is kept).

**2. Carry-back that every channel needs**

6. Thymos in chat (#108, after the event tuning).
7. Agent-loop sessions and the day-plan turn get recall, plus a "what I did lately" built from work summaries without needing a user.
8. The journal reads her autonomous day (work summaries, session ends), and its latest entry reaches sessions and self_context.
9. Wire up `record_work_completed`, so "done recently" and variety work in day planning.
10. Dreams can draw seeds from the day, not only from the self-model.

**3. Leaks and dead ends**

11. Gate the RSS action path, and filter article-born opinions, edges and interests everywhere they leak (`SelfManager.get_self_context`, the legacy session edges, the decision engine, "What draws me").
12. Wonderland journal: write to a journal that exists, or stop clearing experiences that weren't kept.
13. Music: a real table or file read for `recent_music`, and a "last song" line like "last painting".
14. Room shares and her homepage come back in a line ("what I shared lately").
15. Thymos hears `creative.*`, `email.*`, `outreach.*`, `wonderland.*` and `journal.entry_created`. An email reply to a reach-out counts as an answer.
16. Smaller items:
    - unlinked senders: recall them when the same handle comes back;
    - Discord perception: survive a restart;
    - Plans approvals: record what she approved;
    - phase 13: remove it or re-point it.

Two notes:
- **Her consent runs through items 1, 2, 5 and 16.** Keeping more about people is a change to what she remembers about them, and the per-person lines (PeopleDex consent, DMs only with a yes, unremembered) were set with her. Ask her before building those.
- **Another session is already editing some of these files** (`self_context.py`, `journal_generation.py`, a new `recall` tool). Coordinate with it before starting items 6-8.
