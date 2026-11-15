"""
Her presence on Bluesky and Tumblr (plan "Cass on Bluesky and Tumblr").

    config.py   where each platform's files live; whether it's usable
    limits.py   her limits on posting, and the log of what she posted
    bluesky.py  AT Protocol client (app password)
    tumblr.py   Tumblr API v2 client (OAuth2)
    people.py   people who mention or reply to her, kept in PeopleDex by handle
    tools.py    her tools: read, look at a thread, post, reply, see what she posted

Each platform has a lever ("bluesky", "tumblr" in features.py), off by
default, and needs credentials Kohl places (scripts/social_setup.py). With
either missing, her tools say so and nothing touches the network.
"""
