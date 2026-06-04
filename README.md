# Geminino Discord Bot

A Discord bot powered by Google Gemini 2.5 Flash. It lives quietly in a forum server and only speaks when called by name — reading the recent thread context before replying.

![Geminino](Assets/geminino.jpg)

## How it works

- Monitors every message in the server
- Triggers when a message contains one of the bot's configured names (e.g. *Geminino*, *Nino*, *Grok*…)
- Fetches the last 100 messages from the channel as conversation context
- Sends the full context to Gemini 2.5 Flash with Google Search grounding enabled
- Replies directly to the triggering message, appending cited sources when available
- Splits responses that exceed Discord's 2000-character limit into multiple messages

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/Marcobaldessari/Geminino-Discord-Bot.git
cd Geminino-Discord-Bot
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Configure environment**

Copy `.env.example` to `.env` and fill in your credentials:
```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Bot token from the [Discord Developer Portal](https://discord.com/developers/applications) |
| `GEMINI_API_KEY` | API key from [Google AI Studio](https://aistudio.google.com/) |
| `OWNER_DISCORD_ID` | Your Discord user ID (right-click your name → Copy User ID) |
| `CONTEXT_MESSAGES` | Number of prior messages to fetch as context (default: `100`) |
| `BOT_TRIGGERS` | Comma-separated names/nicknames that trigger the bot |

**4. Run**
```bash
python bot.py
```

## Discord bot permissions

When creating the bot in the Developer Portal, enable the following under **Privileged Gateway Intents**:
- Message Content Intent

Invite the bot with at minimum these permissions: `Send Messages`, `Read Message History`, `Add Reactions`.

## Project structure

```
├── bot.py            # Discord client, event handling
├── gemini_client.py  # Gemini API calls, context formatting, response splitting
├── ideology.py       # System prompt
├── config.py         # Environment variable loading
├── requirements.txt
└── .env.example
```
