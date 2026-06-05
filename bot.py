import logging
import discord

from config import Config
from gemini_client import generate_response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = discord.Client(intents=intents)


@bot.event
async def on_ready():
    guilds = len(bot.guilds)
    log.info("Bot ready: %s | %d guild(s)", bot.user, guilds)


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    # Check if the message contains any of the trigger keywords
    uid = bot.user.id
    if f"<@{uid}>" not in message.content and f"<@!{uid}>" not in message.content:
        return

    try:
        async with message.channel.typing():
            context = []
            async for msg in message.channel.history(limit=Config.CONTEXT_MESSAGES, before=message):
                context.append(msg)
            context.reverse()

            chunks = await generate_response(message, context)

        first = True
        for chunk in chunks:
            if first:
                await message.reply(chunk)
                first = False
            else:
                await message.channel.send(chunk)
            log.info(
                "Bot said (message %d, channel %d):\n%s",
                message.id, message.channel.id, chunk,
            )

    except Exception:
        log.exception("Failed to generate or send reply for message %d", message.id)
        try:
            await message.add_reaction("❌")
        except discord.HTTPException:
            pass


bot.run(Config.DISCORD_TOKEN)
