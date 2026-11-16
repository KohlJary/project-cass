"""
Her presence on Bluesky and Tumblr (plan "Cass on Bluesky and Tumblr").

    config.py   where each platform's files live; whether it's usable
    limits.py   her limits on posting, and the log of what she posted
    bluesky.py  AT Protocol client (app password)
    tumblr.py   Tumblr API v2 client (OAuth2)
    people.py   people who mention or reply to her, kept in PeopleDex by handle
    dms.py      who has said she may remember their DMs; what a stored record keeps
    tools.py    her tools: read, look at a thread, post, reply, see what she posted;
                her inbox, drafts, following; Bluesky DMs (their own lever,
                "bluesky_dms"; Tumblr's API has none)
    inbox.py    what came in, queued for her social sessions (never interrupting her)
    watch.py    the watcher that fills the inbox every few minutes (lever "social_watch")
    drafts.py   things she wrote to sit with before they go public
    remember.py her posts and replies into her memory; her ongoing thread per platform
    where.py    where she is: inbox, drafts, what resonated, today's limits
social_turn.py (beside this package) runs her social session on the agent loop.

Each platform has a lever ("bluesky", "tumblr" in features.py), off by
default, and needs credentials Kohl places (scripts/social_setup.py). With
either missing, her tools say so and nothing touches the network.
"""
