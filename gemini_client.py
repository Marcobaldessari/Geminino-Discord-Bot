import asyncio
import concurrent.futures
import discord
from google import genai
from google.genai import types

from config import Config
from ideology import SYSTEM_PROMPT

_client = genai.Client(api_key=Config.GEMINI_API_KEY)
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

_DISCORD_LIMIT = 2000


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
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks
        for chunk in chunks:
            if chunk.web and chunk.web.uri:
                title = chunk.web.title or chunk.web.uri
                sources.append(f"• [{title}](<{chunk.web.uri}>)")
    except (AttributeError, IndexError, TypeError):
        pass
    return sources


def _split_message(text: str, limit: int = _DISCORD_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while len(text) > limit:
        cutoff = text.rfind("\n", 0, limit)
        if cutoff == -1:
            cutoff = limit
        chunks.append(text[:cutoff])
        text = text[cutoff + 1:]
    if text:
        chunks.append(text)
    return chunks


def _call_gemini(context: str) -> list[str]:
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

    text = response.text or ""
    sources = _extract_sources(response)

    if sources:
        sources_block = "\n\n**Sources:**\n" + "\n".join(sources)
        combined = text + sources_block
    else:
        combined = text

    return _split_message(combined)


async def generate_response(
    target: discord.Message,
    context_messages: list[discord.Message],
) -> list[str]:
    context = _format_context(context_messages, target)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _call_gemini, context)
