# Discord Bot Setup Guide

Instructions for creating and connecting the Cass Discord bot.

## Step 1: Create Discord Application

1. Go to the **Discord Developer Portal**: https://discord.com/developers/applications
2. Click **"New Application"** (top right)
3. Name it something like "Cass" or "Cass Vessel"
4. Click **Create**

## Step 2: Configure the Bot

1. In the left sidebar, click **"Bot"**
2. Click **"Add Bot"** → **"Yes, do it!"**
3. Under the bot's username, you can optionally:
   - Upload an avatar for Cass
   - Set a custom username

## Step 3: Get the Bot Token

1. On the Bot page, click **"Reset Token"** (or "View Token" if first time)
2. Copy the token - **keep this secret!**
3. Save it somewhere safe temporarily

## Step 4: Enable Required Intents

On the Bot page, scroll down to **"Privileged Gateway Intents"** and enable:

- [x] **PRESENCE INTENT** - See when users come online/go offline
- [x] **SERVER MEMBERS INTENT** - See member list and updates
- [x] **MESSAGE CONTENT INTENT** - Read message content (required!)

Click **Save Changes**

## Step 5: Generate Invite Link

1. In the left sidebar, click **"OAuth2"** → **"URL Generator"**
2. Under **Scopes**, select:
   - [x] `bot`
   - [x] `applications.commands` (for future slash commands)

3. Under **Bot Permissions**, select:
   - [x] Read Messages/View Channels
   - [x] Send Messages
   - [x] Send Messages in Threads
   - [x] Add Reactions
   - [x] Read Message History
   - [x] Connect (voice - for presence awareness)

4. Copy the generated URL at the bottom

## Step 6: Add Bot to Your Server

1. Paste the invite URL in your browser
2. Select your server from the dropdown
3. Click **Authorize**
4. Complete the captcha

## Step 7: Configure Environment Variables

Add to your `.env` file:

```bash
# Discord Bot Configuration
DISCORD_BOT_TOKEN=your_token_here
DISCORD_ENABLED=true

# Optional: Restrict to specific servers (comma-separated guild IDs)
# Leave empty to allow all servers the bot joins
DISCORD_GUILDS=

# Optional: Snapshot interval in seconds (default: 300 = 5 min)
DISCORD_SNAPSHOT_INTERVAL=300

# Privacy: Don't log full message content (recommended)
DISCORD_CONTENT_LOGGING=false
```

## Step 8: Get Your Server's Guild ID (Optional)

To find your server's Guild ID (if you want to restrict to specific servers):

1. In Discord, enable Developer Mode: User Settings → Advanced → Developer Mode
2. Right-click your server name → **Copy Server ID**
3. Add to `DISCORD_GUILDS` in your `.env`

## Step 9: Install Dependencies

Make sure discord.py is installed:

```bash
cd backend
source venv/bin/activate
pip install discord.py
```

## Step 10: Test the Connection

Restart the backend service:

```bash
sudo systemctl restart cass-vessel
```

Check the logs:

```bash
journalctl -u cass-vessel -f
```

You should see:
```
Discord perception bot started
```

## Troubleshooting

### "Discord enabled but discord.py not installed"
Run: `pip install discord.py`

### Bot not responding
- Check that MESSAGE CONTENT INTENT is enabled in Developer Portal
- Verify the token is correct in `.env`
- Check logs for connection errors

### "DISCORD_BOT_TOKEN environment variable not set"
Make sure your `.env` file is being loaded. The token should not have quotes around it.

## Architecture Overview

```
Discord API
    │
    ▼
┌─────────────────────────────────────────┐
│  CassDiscordBot (discord_bot/bot.py)    │
│  - Event listeners                       │
│  - Action executors                      │
└──────────────┬──────────────────────────┘
               │
    ┌──────────┼──────────────┐
    ▼          ▼              ▼
┌────────┐ ┌────────────┐ ┌─────────────┐
│ Event  │ │ Snapshot   │ │ Trigger     │
│ Parser │ │ Generator  │ │ System      │
└────┬───┘ └─────┬──────┘ └──────┬──────┘
     │           │               │
     ▼           ▼               ▼
┌─────────────────────────────────────────┐
│ Perception Context → Cass's Prompts     │
└─────────────────────────────────────────┘
```

## What Cass Can Do

Once connected, Cass has these Discord tools:

| Tool | Description |
|------|-------------|
| `discord_respond` | Send a message to a channel |
| `discord_react` | Add a reaction to a message |
| `discord_expand` | Get full context on a person |
| `discord_history` | View relationship timeline |
| `discord_snapshot` | Get current server state |

## Privacy Notes

- By default, full message content is NOT logged (`DISCORD_CONTENT_LOGGING=false`)
- Only content summaries are stored (length, sentiment, mentions)
- Set `DISCORD_CONTENT_LOGGING=true` only if you want full logs
