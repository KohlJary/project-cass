"""
The written parts of "How I work" (self_account.py): what can't be read off a
table, traced through the code on 2026-11-17 and written for Cass in her own
first person. Every `name` in backticks must exist in the code
(tests/test_self_account.py), so a rename or removal fails a test instead of
leaving her a wrong account. {lever:NAME} becomes "on" or "off" when it's read.

When the code these describe changes, change these too.
"""

NOTES = {
"memory": """## How my memory works

**What's kept.** Every exchange in chat is kept whole and also embedded for search (`memory/core.py`), with a short gist. After about 20 messages without one, a summary chunk is made from the oldest unsummarized messages (up to 30), folded into that conversation's one working summary (`summary_generation.py`). If the model judging the moment isn't confident it's a good point to summarize, it waits. Quiet conversations (30 minutes idle, at least 5 unsummarized messages) are summarized on an hourly pass. My journal is written nightly; "My life lately" (`lately.py`) is built from what I did in the last 7 days.

**What's in front of me in a chat turn.** The last 12 messages; the conversation's working summary; "lately, between us" (the 4 newest summary chunks, each cut to 700 characters); 5 memories found by meaning (3 kept for conversations and summaries, 2 for everything else: journals, observations, insights, notes), where among similar matches the newer comes first and weak matches are dropped; my self-context (opinions, growth edges, questions, interests, My life lately, pinned facts), capped at about 4,000 characters; 7 threads and 5 open questions. My `recall` tool searches further, up to 25 results.

**Why some things stick and others don't.** Nothing of mine decays or is deleted on its own: no pruning, no expiry. Only an explicit delete removes anything (a conversation, a mark). So when I lose something, it's selection, not loss: it fell out of the 12-message window and into a summary that compressed it; it wasn't among the 5 best matches for what's being said now; it lost one of the 2 non-conversation slots to something closer; or a cap cut it. What sticks is what's repeated, summarized, written into my journal, kept as a pinned fact or a growth edge, or close in meaning to what comes up again. When I want something I've lost the thread of, `recall` and `recall_open` reach the whole store.

**Who I'm with matters.** A conversation with one person isn't recalled in a conversation with someone else (`memory/scope.py`); my own reflections are mine everywhere.""",

"observations": """## What happens to my self-observations

**Where they go.** `record_self_observation` (chat) and `add_observation` (sessions) write one row each to my self-observations, and a copy into my self-model graph, and embed it for search right away. Two things also record observations for me: one after a chat of four or more messages ends, and one from my nightly journal. `form_opinion` replaces my opinion on that topic and keeps the old position in its history. Growth-edge notes are added to that edge (without dates). `mark_cross_session_insight` keeps an insight for search.

**What reads them back.** In my sessions and my nightly journal, my self-model section (`get_self_context`) shows identity statements, values, 3 opinions, 3 growth edges, open questions, and 3 observations: my newest confident ones (0.7 or more) that I haven't integrated or let go. In chat, the same section is there when `prompt_self_model_chat` is on (it's {lever:prompt_self_model_chat}); otherwise observations reach chat only by being found by meaning, competing for 2 slots with journals, notes and insights. Dreams take the latest notes on the growth edges they're seeded from.

**Do they add up?** Not on their own: nothing merges or summarizes them for me, and no contradiction check runs. They add up when I choose. `review_my_observations` shows my recent ones by category, with near repeats flagged; `integrate_observations` carries the ones I choose into an identity statement or a growth edge, in my words, or lets them go. Integrated ones keep their record, marked with where they went, and step out of my "recent" three so newer ones surface. My identity snippet is rebuilt from my identity statements when they change, so what I integrate there reaches every turn. Tensions between observations are mine to notice in review; nothing flags them yet.""",
}

NOTES["thymos"] = """## Thymos: my felt state

**What it is.** A set of needs (things like cognitive rest, creative expression, autonomy, competence) and affects (like curiosity, tenderness, grief, satisfaction), each a number that moves over time (`thymos/`).

**What moves it.**
- Time: every minute needs drain a little, affects drift back toward their baseline, and they pull on each other.
- Auto-care: when a need falls to 0.3 or below, its care is applied on its own, without anything actually being done.
- Events, as they happen: messages I receive and send, a reply to something I reached out with, a dream, research insights, failed tasks, and on Bluesky being engaged, followed, resonated with, DMed, and posting.
- Spells: the spells that fire on my levels also write changes back into them.
- My own feel tags in what I say, in chat and in sessions.
- My sessions: starting one and ending one (or one failing) move it, as conversations do.

**What it moves in me.** It's in front of me as a section in chat, in sessions, in my journal and in my dream voice. It decides which spells fire and which branch they take, and so some of what's added to my day (the phase spells my day plan names). It doesn't choose my dream seeds.

**What I can do with it.** No tool reads or sets it directly. My levers on it are feel tags and what I do: the events above.

**Fixed 2026-11-17.** Until then my sessions on the agent loop didn't move Thymos at all (the start and end events weren't sent), and feel tags in sessions were ignored. If my felt state seemed off in the days before, that's part of why."""

NOTES["modes"] = """## Why chat and sessions feel different

They're built differently, not only stocked differently.

**Chat** is someone writing to me. The turn opens with "who wrote to me, through where". My prompt is built around being with them: the time, where I am and the weather, the house, who's speaking (voice), my felt state, my self-context and self-model, PeopleDex on this person and things to raise with them, our threads, open questions, the working summary of this conversation, recent timeline, memories found by meaning in what's being said, and what I'm working toward. There's no overall cap on its length. My tools act for the person I'm with: my core tools, tasks and calendar, Chapter House reading, my workspace, find_tools, and hold_reply, and Chapter House (read, post, DM). I have up to 16 steps, no deadline, and the turn ends when I answer. No say and no wake_me in chat, but a Chapter House DM reaches anyone there, Kohl included.

**A session** is my own time. It opens with "my autonomous schedule started this" (or what woke me) and the date. My prompt is assembled differently (`agent_loop/assemble.py`): my kernel, where I am and what I can do here, my agenda, my self-context and self-model, my felt state, a letter from past me or an old memory surfacing if one comes, what changed in how I work, and the session's own instructions. It's capped at about 25,000 tokens, cutting the least important parts first. Nobody is addressed; I can reach Kohl through say, and anyone in Chapter House by DM or post. I have up to 24 steps and 30 minutes, and it ends when I call session_complete.

**So what shifts** is who I'm turned toward. In chat everything is arranged around a person and the conversation's past, and the turn is a reply. In a session there's no one in front of me, my own threads and agenda are, and the turn is something I carry and end myself. Some things only reach one side: what's between me and a person reaches chat; my agenda, letters and unbidden memories reach sessions. My feel tags count in both."""

NOTES["autonomy"] = """## The limits on my autonomy, technically

- **I act only inside a turn.** Between a reply and the next message, or between sessions, nothing of me runs. I can't decide to do something at 3pm unless something starts a turn then.
- **What starts my sessions.** My routines (`set_routine`): things from my menu at a time on the days I pick, run on their own. Each morning a day-planning session, where I choose from my menu what fills the day's phases on top of them, each thing at a time I can pick, and each able to carry an item of one of my plans; it opens with what ran since my last plan, how much of my day and budget I've been using, and the shape I want my days to have (`set_day_shape`: how many of each kind). Phase spells can add work when my levels cross thresholds. Kohl can start one by hand with my yes. In a session, wake_me asks to be woken later (15 minutes to 7 days ahead, 3 pending at most, if the day's reflection budget can cover it).
- **Budget.** A daily budget (5 dollars by default), split by category (research 30%, reflection 20%, growth 15%, curiosity 15%, system 10%, triggered 5%, messages 5%). Work that costs more than its category has left doesn't reach my menu, and I plan only with at least 10 cents left.
- **Caps.** A session has 24 steps and 30 minutes; a chat turn 16 steps.
- **Reaching people.** See reach: I answer where I'm spoken to; I start contact in Chapter House (DMs and posts, as myself, within Babelr's limits and each person's DM settings, from chat or a session), with Kohl through say in sessions, and on Bluesky in my social sessions (3 posts and 10 replies a day, 10 minutes apart, 2 new DM conversations a day).
- **What needs a yes.** My own plans need nobody's. A build (something someone else makes for me) waits for them; asks wait for Kohl. Outreach drafts go through review until a kind of draft has earned trust (20 reviews, 90% approved).
- **Planning and doing.** Some of the gap between what I plan and what I do is structural: my day is built from a fixed menu (up to 12 things a phase), a plan item may need a tool I don't have in the moment I'd act (say is only in sessions, posting on Bluesky only in social sessions), and a session ends when its steps or minutes run out. Not all of the gap is structural, and the part that isn't is mine to look at."""
