import asyncio
import concurrent.futures
from typing import Sequence

from google import genai
from google.genai import types

from config import Config
from ideology import PROMPTS
from policy import (
    BotMode,
    ContextMessage,
    DiscordReply,
    format_transcript,
    prepare_discord_reply,
)

_client = genai.Client(api_key=Config.GEMINI_API_KEY)
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def _extract_sources(response) -> list[str]:
    urls: list[str] = []
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks
        for chunk in chunks:
            if chunk.web and chunk.web.uri and chunk.web.uri not in urls:
                urls.append(chunk.web.uri)
    except (AttributeError, IndexError, TypeError):
        pass
    return urls


def _call_gemini(prompt: str, mode: BotMode) -> DiscordReply:
    response = _client.models.generate_content(
        model=Config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=PROMPTS[mode],
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )
    return prepare_discord_reply(response.text or "", _extract_sources(response), mode)


async def generate_response(
    question: str,
    context_messages: Sequence[ContextMessage],
    mode: BotMode,
) -> DiscordReply:
    transcript = format_transcript(context_messages, Config.CONTEXT_MESSAGES)
    prompt = (
        f"Active mode: {mode}. Latest user request:\n{question}\n\n"
        f"Latest channel transcript ({len(context_messages)} messages):\n\n{transcript}"
    )
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _call_gemini, prompt, mode)
