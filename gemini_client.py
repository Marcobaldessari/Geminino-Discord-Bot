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
_MAX_SOURCES_DEEP_DIVE = 6
_MAX_DEEP_DIVE_MESSAGES = 8
_DEEP_DIVE_MAX_OUTPUT_TOKENS = 16384
_TRAILING_SOURCES_RE = re.compile(
    r"\n+\**Sources?:?\**\s*\n(?:[-•*].*\n?)+\s*$", re.IGNORECASE
)
_SOURCES_REQUEST_RE = re.compile(
    r"\b(sources?|links?|references?|citations?|fonti?|riferiment\w*|collegament\w*|citazion\w*)\b",
    re.IGNORECASE,
)
_DEEP_DIVE_RE = re.compile(
    r"\b(deep dive|full research|ricerca approfondita|ricerca completa|"
    r"analisi approfondita|approfondisc\w*|approfondiment\w*|vai a fondo)\b",
    re.IGNORECASE,
)


def _wants_sources(text: str) -> bool:
    return bool(_SOURCES_REQUEST_RE.search(text))


def _wants_deep_dive(text: str) -> bool:
    return bool(_DEEP_DIVE_RE.search(text))


def _format_context(context_messages: list[discord.Message], target: discord.Message) -> str:
    lines = [
        f"[{msg.author.display_name}]: {msg.content}"
        for msg in context_messages
        if msg.content
    ]
    lines.append(f"[{target.author.display_name}]: {target.content}  ← DIRECT CALL TO YOU")
    return "\n".join(lines)


def _extract_sources(response, max_sources: int = _MAX_SOURCES) -> list[str]:
    sources = []
    seen_uris = set()
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks
        for chunk in chunks:
            if len(sources) >= max_sources:
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


def _split_message(text: str, limit: int = _DISCORD_LIMIT, max_chunks: int = _MAX_DEEP_DIVE_MESSAGES) -> list[str]:
    chunks = []
    while len(text) > limit and len(chunks) < max_chunks - 1:
        cutoff = text.rfind("\n", 0, limit)
        if cutoff == -1:
            cutoff = text.rfind(" ", 0, limit)
        if cutoff == -1:
            cutoff = limit
        chunks.append(text[:cutoff].rstrip())
        text = text[cutoff:].lstrip()
    chunks.append(_truncate_message(text, limit))
    return chunks


def _shorten_text(text: str, budget: int) -> str:
    prompt = (
        f"Riscrivi il seguente testo in italiano perché stia sotto i {budget} caratteri. "
        "Mantieni tutti i fatti essenziali e lo stesso tono diretto, elimina solo ciò che è "
        "ridondante o marginale. Restituisci esclusivamente il testo riscritto, senza premesse, "
        "commenti o note sulla riscrittura.\n\n"
        f"Testo:\n{text}"
    )
    try:
        response = _client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        shortened = (response.text or "").strip()
    except Exception:
        return text
    return shortened or text


def _call_gemini(context: str, include_sources: bool, deep_dive: bool) -> list[str]:
    instruction = "Answer the highlighted direct call to you. Be direct and grounded in evidence."
    if deep_dive:
        instruction = (
            "The user has explicitly asked for a deep dive / full research treatment. "
            "Answer the highlighted direct call to you with a thorough, well-structured, "
            "in-depth answer covering the relevant angles. You are not limited to a single "
            "Discord message's length, but every sentence must still carry information — no padding."
        )
    prompt = (
        "Here is the recent conversation:\n\n"
        f"{context}\n\n"
        f"{instruction}"
    )
    config_kwargs = dict(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )
    if deep_dive:
        config_kwargs["max_output_tokens"] = _DEEP_DIVE_MAX_OUTPUT_TOKENS

    response = _client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(**config_kwargs),
    )

    text = _TRAILING_SOURCES_RE.sub("", response.text or "").rstrip()

    sources_block = ""
    if include_sources:
        max_sources = _MAX_SOURCES_DEEP_DIVE if deep_dive else _MAX_SOURCES
        sources = _extract_sources(response, max_sources)
        if sources:
            sources_block = "\n\n**Sources:**\n" + "\n".join(sources)

    if deep_dive:
        combined_limit = _DISCORD_LIMIT * _MAX_DEEP_DIVE_MESSAGES
        combined = _truncate_message(text, combined_limit - len(sources_block)) + sources_block
        return _split_message(combined)

    budget = _DISCORD_LIMIT - len(sources_block)
    if len(text) > budget:
        text = _shorten_text(text, budget)

    return [_truncate_message(text + sources_block)]


async def generate_response(
    target: discord.Message,
    context_messages: list[discord.Message],
) -> list[str]:
    context = _format_context(context_messages, target)
    deep_dive = _wants_deep_dive(target.content)
    include_sources = deep_dive or _wants_sources(target.content)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _call_gemini, context, include_sources, deep_dive)
