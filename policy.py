"""Discord-facing behaviour: command parsing, transcript formatting, reply shaping.

Kept free of Discord and Gemini imports so it can be unit tested on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, Sequence

BotMode = Literal["compact", "deep"]

MAX_CONTEXT_MESSAGES = 30
DISCORD_MESSAGE_LIMIT = 2000
MAX_ATTACHMENT_CHARS = 100_000

TEXT_ATTACHMENT_EXTENSIONS = (
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".log", ".yml", ".yaml", ".xml",
)

MODE_ALIASES: dict[str, BotMode] = {
    "compact": "compact",
    "brief": "compact",
    "short": "compact",
    "breve": "compact",
    "deep": "deep",
    "full": "deep",
    "report": "deep",
    "analysis": "deep",
    "analisi": "deep",
    "approfondito": "deep",
}

MODE_KEYWORDS = {"mode", "modo", "modalita", "modalità"}

# Aliases unambiguous enough to prefix a question ("deep <question>"). The others
# only switch mode next to an explicit keyword, otherwise a question like
# "Analisi del debito pubblico" would lose its first word.
PREFIX_ALIASES = {"compact", "deep"}

HELP_ALIASES = {"help", "aiuto"}

_URL_RE = re.compile(r"https?://[^\s<>]+")
_TRAILING_PUNCTUATION_RE = re.compile(r"[),.;:!?]+$")
_RAW_MENTION_RE = re.compile(r"<@[!&]?\d+>")


@dataclass(frozen=True)
class BotRequest:
    type: Literal["status", "help", "set", "ask"]
    text: str = ""
    mode: Optional[BotMode] = None
    persist: bool = False


@dataclass(frozen=True)
class ContextMessage:
    author: str
    content: str
    created_at: datetime
    author_id: str = ""
    bot: bool = False


@dataclass(frozen=True)
class TextAttachment:
    name: str
    text: str


@dataclass(frozen=True)
class DiscordReply:
    content: str
    files: list[tuple[str, bytes]] = field(default_factory=list)


def strip_bot_mention(content: str, bot_names: Sequence[str]) -> str:
    text = _RAW_MENTION_RE.sub("", content)
    names = [re.escape(name) for name in bot_names if name]
    if names:
        text = re.sub(rf"@(?:{'|'.join(names)})(?:#\d+)?(?!\w)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[^\S\r\n]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_token(token: str = "") -> str:
    return re.sub(r"^[^\w]+|[^\w]+$", "", token.lower())


def _rest_after_tokens(text: str, count: int) -> str:
    index = 0
    for _ in range(count):
        while index < len(text) and text[index].isspace():
            index += 1
        while index < len(text) and not text[index].isspace():
            index += 1
    return text[index:].strip()


def parse_bot_request(text: str) -> BotRequest:
    trimmed = text.strip()
    if not trimmed:
        return BotRequest(type="status")

    tokens = trimmed.split()
    first = _normalize_token(tokens[0])
    second = _normalize_token(tokens[1]) if len(tokens) > 1 else ""

    if len(tokens) == 1 and first in HELP_ALIASES:
        return BotRequest(type="help")

    mode: Optional[BotMode] = None
    consumed = 0
    explicit = False

    if first in MODE_KEYWORDS:
        if not second:
            return BotRequest(type="status")
        mode = MODE_ALIASES.get(second)
        if not mode:
            return BotRequest(type="help")
        consumed = 2
        explicit = True
    elif first in MODE_ALIASES:
        if second in MODE_KEYWORDS:
            mode = MODE_ALIASES[first]
            consumed = 2
            explicit = True
        elif not second:
            mode = MODE_ALIASES[first]
            consumed = 1
            explicit = True
        elif first in PREFIX_ALIASES:
            mode = MODE_ALIASES[first]
            consumed = 1

    if not mode:
        return BotRequest(type="ask", text=trimmed)

    rest = _rest_after_tokens(trimmed, consumed)
    if not rest:
        return BotRequest(type="set", mode=mode)
    return BotRequest(type="ask", text=rest, mode=mode, persist=explicit)


def resolve_mode(value: Optional[str]) -> Optional[BotMode]:
    return MODE_ALIASES.get(_normalize_token(value)) if value else None


def is_text_attachment(name: str, content_type: Optional[str] = None) -> bool:
    if content_type and re.match(r"^(?:text/|application/(?:json|xml|x-yaml|yaml))", content_type, re.IGNORECASE):
        return True
    lower = name.lower()
    return any(lower.endswith(extension) for extension in TEXT_ATTACHMENT_EXTENSIONS)


# Discord turns any message longer than 2000 characters into a message.txt
# upload, so the prompt often arrives as a file with an empty message body.
def compose_question(inline: Optional[str], attachments: Sequence[TextAttachment]) -> str:
    parts = [inline.strip()] if inline and inline.strip() else []
    for attachment in attachments:
        text = attachment.text.strip()[:MAX_ATTACHMENT_CHARS]
        if text:
            parts.append(f'Attached file "{attachment.name}":\n{text}')
    return "\n\n".join(parts)


def find_pending_question(
    messages: Sequence[ContextMessage],
    author_id: str,
    bot_names: Sequence[str],
    now: Optional[datetime] = None,
    max_age: timedelta = timedelta(minutes=30),
) -> Optional[str]:
    reference = now or datetime.now(timezone.utc)
    for item in reversed(list(messages)):
        if item.bot or item.author_id != author_id:
            continue
        if reference - item.created_at > max_age:
            continue
        parsed = parse_bot_request(strip_bot_mention(item.content, bot_names))
        if parsed.type == "ask" and parsed.text.strip():
            return parsed.text
    return None


def format_transcript(messages: Sequence[ContextMessage], limit: int = MAX_CONTEXT_MESSAGES) -> str:
    recent = list(messages)[-limit:] if limit else list(messages)
    return "\n".join(
        f"[{message.created_at.isoformat()}] {message.author}: {message.content.strip() or '[attachment or empty message]'}"
        for message in recent
    )


def suppress_link_previews(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        if match.start() > 0 and text[match.start() - 1] == "<":
            return raw
        trailing_match = _TRAILING_PUNCTUATION_RE.search(raw)
        trailing = trailing_match.group(0) if trailing_match else ""
        url = raw[: -len(trailing)] if trailing else raw
        return f"<{url}>{trailing}" if url else raw

    return _URL_RE.sub(replace, text)


def fit_to_discord_message(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> str:
    content = suppress_link_previews(text)
    if len(content) <= limit:
        return content
    split_at = content.rfind("\n", 0, limit)
    if split_at < int(limit * 0.6):
        split_at = content.rfind(" ", 0, limit)
    if split_at < 1:
        split_at = limit
    return content[:split_at].rstrip()


def split_into_messages(text: str, limit: int = DISCORD_MESSAGE_LIMIT, max_chunks: int = 8) -> list[str]:
    rest = suppress_link_previews(text).strip()
    if not rest:
        return []
    chunks: list[str] = []
    while len(rest) > limit and len(chunks) < max_chunks - 1:
        floor = int(limit * 0.5)
        split_at = rest.rfind("\n\n", 0, limit)
        if split_at < floor:
            split_at = rest.rfind("\n", 0, limit)
        if split_at < floor:
            split_at = rest.rfind(" ", 0, limit)
        if split_at < 1:
            split_at = limit
        chunks.append(rest[:split_at].rstrip())
        rest = rest[split_at:].lstrip()
    chunks.append(f"{rest[: limit - 1].rstrip()}…" if len(rest) > limit else rest)
    return [chunk for chunk in chunks if chunk]


def ensure_sources(text: str, urls: Sequence[str]) -> str:
    missing = [url for url in urls if url not in text][:5]
    if not missing:
        return text
    listed = "\n".join(f"- <{url}>" for url in missing)
    return f"{text.strip()}\n\nSources:\n{listed}"


def prepare_discord_reply(text: str, urls: Sequence[str], mode: BotMode) -> DiscordReply:
    with_sources = ensure_sources(text, urls) or "I could not produce a sourced answer."
    discord_text = suppress_link_previews(with_sources)
    if mode == "compact" or len(discord_text) <= DISCORD_MESSAGE_LIMIT:
        return DiscordReply(content=fit_to_discord_message(discord_text))
    preview = fit_to_discord_message(discord_text, 1650)
    return DiscordReply(
        content=f"{preview}\n\n— full report attached —",
        files=[("report.md", with_sources.encode("utf-8"))],
    )
