import asyncio
import concurrent.futures
import re

import discord
from google import genai
from google.genai import types

from config import Config
from ideology import SYSTEM_PROMPT

_client = genai.Client(api_key=Config.GEMINI_API_KEY)
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

_DISCORD_LIMIT = 2000
_TRUNCATION_MARKER = "…"
_MAX_SOURCES = 3
_TRAILING_SOURCES_RE = re.compile(
    r"\n+\**Sources?:?\**\s*\n(?:[-•*].*\n?)+\s*$", re.IGNORECASE
)
_SOURCES_REQUEST_RE = re.compile(
    r"\b(sources?|links?|references?|citations?|fonti?|riferiment\w*|collegament\w*|citazion\w*)\b",
    re.IGNORECASE,
)


def _wants_sources(text: str) -> bool:
    return bool(_SOURCES_REQUEST_RE.search(text))


def _format_context(context_messages: list[discord.Message], target: discord.Message) -> str:
    lines = [
        f"[{msg.author.display_name}]: {msg.content}"
        for msg in context_messages
        if msg.content
    ]
    lines.append(f"[{target.author.display_name}]: {target.content}  ← DIRECT CALL TO YOU")
    return "\n".join(lines)


def _extract_sources(response) -> list[str]:
    sources = []
    seen_uris = set()
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks
        for chunk in chunks:
            if len(sources) >= _MAX_SOURCES:
                break
            if chunk.web and chunk.web.uri and chunk.web.uri not in seen_uris:
                seen_uris.add(chunk.web.uri)
                title = chunk.web.title or chunk.web.uri
                sources.append(f"• [{title}](<{chunk.web.uri}>)")
    except (AttributeError, IndexError, TypeError):
        pass
    return sources


def _truncate_message(text: str, limit: int = _DISCORD_LIMIT) -> str:
    if len(text) <= limit:
        return text
    cutoff = limit - len(_TRUNCATION_MARKER)
    space = text.rfind(" ", 0, cutoff)
    if space != -1:
        cutoff = space
    return text[:cutoff].rstrip() + _TRUNCATION_MARKER


def _call_gemini(context: str, include_sources: bool) -> str:
    prompt = (
        "Here is the recent conversation:\n\n"
        f"{context}\n\n"
        "Answer the highlighted direct call to you. Be direct and grounded in evidence."
    )
    response = _client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )

    text = _TRAILING_SOURCES_RE.sub("", response.text or "").rstrip()

    if include_sources:
        sources = _extract_sources(response)
        if sources:
            text += "\n\n**Sources:**\n" + "\n".join(sources)

    return _truncate_message(text)


async def generate_response(
    target: discord.Message,
    context_messages: list[discord.Message],
) -> str:
    context = _format_context(context_messages, target)
    include_sources = _wants_sources(target.content)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _call_gemini, context, include_sources)
