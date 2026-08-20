import io
import logging

import discord

from config import Config
from gemini_client import generate_response
from modes import default_mode, get_channel_mode, set_channel_mode
from policy import (
    MAX_ATTACHMENT_CHARS,
    ContextMessage,
    DiscordReply,
    TextAttachment,
    compose_question,
    find_pending_question,
    is_text_attachment,
    parse_bot_request,
    split_into_messages,
    strip_bot_mention,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = discord.Client(intents=intents)

_ALLOWED_MENTIONS = discord.AllowedMentions(everyone=False, roles=False, replied_user=False)

HELP = "\n".join([
    "Modes:",
    "- compact — short sourced answer, one Discord message",
    "- deep — full sourced report; attached as report.md if it exceeds Discord's limit",
    "",
    "@bot help — show this message",
    "@bot mode — show the current mode",
    "@bot mode deep / @bot deep mode / @bot deep — set the channel mode",
    "@bot mode deep <question> — set deep and answer now",
    "@bot deep <question> — one-shot deep, does not change the channel default",
    "",
    f"The mode is saved per channel. New channels start in {default_mode()}.",
])


def _bot_names(message: discord.Message) -> list[str]:
    names = [bot.user.name if bot.user else ""]
    if message.guild and message.guild.me:
        names.append(message.guild.me.display_name)
    names.extend(Config.BOT_TRIGGERS)
    return [name for name in names if name]


async def _read_text_attachments(message: discord.Message) -> list[TextAttachment]:
    files: list[TextAttachment] = []
    for attachment in message.attachments:
        if not is_text_attachment(attachment.filename, attachment.content_type):
            continue
        try:
            raw = await attachment.read()
            text = raw.decode("utf-8", errors="replace")[:MAX_ATTACHMENT_CHARS]
            files.append(TextAttachment(name=attachment.filename, text=text))
        except (discord.HTTPException, UnicodeDecodeError):
            log.exception("Could not read attachment %s", attachment.filename)
    return files


def _discord_files(files: list[tuple[str, bytes]]) -> list[discord.File]:
    return [discord.File(io.BytesIO(data), filename=name) for name, data in files]


# Delivery degrades instead of raising: a deep answer takes minutes, so the
# prompt may be deleted meanwhile, and the upload may be refused outright when
# the bot lacks Attach Files, in which case the report still goes out as plain
# messages.
async def _deliver(message: discord.Message, content: str, files: list[tuple[str, bytes]] | None = None) -> None:
    files = files or []
    try:
        await message.reply(
            content,
            files=_discord_files(files),
            allowed_mentions=_ALLOWED_MENTIONS,
            suppress_embeds=True,
        )
        return
    except discord.HTTPException:
        log.exception("Reply failed, sending to the channel instead")

    try:
        await message.channel.send(
            content,
            files=_discord_files(files),
            allowed_mentions=_ALLOWED_MENTIONS,
            suppress_embeds=True,
        )
        return
    except discord.HTTPException:
        log.exception("Channel send failed")

    if not files:
        return
    try:
        for chunk in split_into_messages(files[0][1].decode("utf-8", errors="replace")):
            await message.channel.send(
                chunk,
                allowed_mentions=_ALLOWED_MENTIONS,
                suppress_embeds=True,
            )
    except discord.HTTPException:
        log.exception("Could not deliver the report as plain messages")


async def _resolve_reference(message: discord.Message) -> discord.Message | None:
    resolved = message.reference.resolved if message.reference else None
    if isinstance(resolved, discord.Message):
        return resolved
    if not message.reference or message.reference.message_id is None:
        return None
    try:
        return await message.channel.fetch_message(message.reference.message_id)
    except discord.HTTPException:
        return None


async def _fetch_context(message: discord.Message) -> list[ContextMessage]:
    history = [
        msg async for msg in message.channel.history(limit=Config.CONTEXT_MESSAGES, before=message)
    ]
    history.reverse()
    return [
        ContextMessage(
            author=msg.author.display_name,
            content=msg.clean_content,
            created_at=msg.created_at,
            author_id=str(msg.author.id),
            bot=msg.author.bot,
        )
        for msg in history
    ]


@bot.event
async def on_ready():
    log.info("Bot ready: %s | %d guild(s) | default mode: %s", bot.user, len(bot.guilds), default_mode())


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None or bot.user is None:
        return
    if not message.mentions or bot.user not in message.mentions:
        return

    try:
        names = _bot_names(message)
        request = parse_bot_request(strip_bot_mention(message.clean_content, names))

        if request.type == "help":
            await _deliver(message, HELP)
            return

        mode = await get_channel_mode(message.channel.id)
        if request.type == "set" and request.mode:
            mode = await set_channel_mode(message.channel.id, request.mode)
        elif request.type == "ask" and request.mode:
            mode = (
                await set_channel_mode(message.channel.id, request.mode)
                if request.persist
                else request.mode
            )

        context = await _fetch_context(message)
        attachments = await _read_text_attachments(message)
        question = compose_question(request.text if request.type == "ask" else None, attachments)

        if not question and message.reference:
            replied_to = await _resolve_reference(message)
            if replied_to and not replied_to.author.bot:
                question = strip_bot_mention(replied_to.clean_content, names)

        if not question and request.type == "set":
            question = find_pending_question(context, str(message.author.id), names) or ""

        if not question:
            if message.attachments:
                await _deliver(
                    message,
                    f"Mode: {mode}. I could not read the attached file. "
                    "Attach a text file (.txt, .md, .csv, .json) or paste the prompt.",
                )
            elif request.type == "set":
                await _deliver(message, f"Mode set to {mode} for this channel. Send your question.")
            else:
                await _deliver(message, f"Current mode: {mode}.")
            return

        async with message.channel.typing():
            reply: DiscordReply = await generate_response(question, context, mode)

        await _deliver(message, reply.content, reply.files)
        log.info("Answered message %d in channel %d (mode: %s)", message.id, message.channel.id, mode)

    except Exception:
        log.exception("Failed to generate or send reply for message %d", message.id)
        try:
            await message.add_reaction("❌")
        except discord.HTTPException:
            pass


bot.run(Config.DISCORD_TOKEN)
