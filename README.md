# Geminino Discord Bot

A Discord bot powered by Google Gemini 2.5 Flash. It lives quietly in a forum server and only speaks when called by name — reading the recent thread context before replying.

![Geminino](Assets/geminino.jpg)

## How it works

- Triggers when the bot is mentioned in a server channel
- Fetches the last 100 messages from the channel as conversation context
- Sends the request and the context to Gemini 2.5 Flash with Google Search grounding enabled
- Replies directly to the triggering message, appending cited sources when available
- Answers in the channel mode: `compact` (one short message) or `deep` (full report)

## Modes

| Mode | Behaviour |
|---|---|
| `compact` | Short sourced answer, kept inside a single Discord message |
| `deep` | Full sourced report; attached as `report.md` when it exceeds Discord's limit |

Commands (mention the bot first):

- `@bot <question>` — answer in the channel mode
- `@bot help` — list the commands
- `@bot mode` — show the current mode
- `@bot mode deep`, `@bot deep mode`, or `@bot deep` — set the channel mode. Aliases such as `breve`, `analisi`, `report`, `modalità` are accepted
- `@bot mode deep <question>` — set the mode and answer now
- `@bot deep <question>` — one-shot deep answer, the channel mode stays unchanged
- Attach a text file (`.txt`, `.md`, `.csv`, `.json`, …) to send a long prompt. Discord uploads any message over 2000 characters as `message.txt`, and the bot reads it as the prompt

A bare mode switch reuses your last question in the channel (within 30 minutes), and mentioning the bot in a reply uses the replied-to message as the prompt.

The mode is stored per channel in `data/modes.json`. Channels that never set one use `DEFAULT_MODE` from `.env` (`compact` if unset).

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
| `BOT_TRIGGERS` | Comma-separated names/nicknames stripped from the request text |
| `GEMINI_MODEL` | Gemini model to call (default: `gemini-2.5-flash`) |
| `DEFAULT_MODE` | Mode for channels that never set one: `compact` or `deep` (default: `compact`) |

**4. Run**
```bash
python bot.py
```

**5. Tests**
```bash
python -m unittest discover -s tests
```

## Discord bot permissions

When creating the bot in the Developer Portal, enable the following under **Privileged Gateway Intents**:
- Message Content Intent

Invite the bot with at minimum these permissions: `Send Messages`, `Read Message History`, `Add Reactions`, `Attach Files` (deep reports are uploaded as `report.md`).

## Project structure

```
├── bot.py                 # Discord client, event handling, delivery
├── policy.py              # Command parsing, transcript and reply formatting
├── modes.py               # Per-channel mode persistence (data/modes.json)
├── gemini_client.py       # Gemini API calls with Google Search grounding
├── ideology.py            # System prompts (compact, deep)
├── config.py              # Environment variable loading
├── tests/test_policy.py
├── requirements.txt
└── .env.example
```
