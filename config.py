import os
from dotenv import load_dotenv

from policy import BotMode, resolve_mode

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _default_mode() -> BotMode:
    raw = os.getenv("DEFAULT_MODE", "").strip()
    mode = resolve_mode(raw)
    if raw and not mode:
        raise ValueError(f'Invalid DEFAULT_MODE "{raw}": expected compact or deep.')
    return mode or "compact"


class Config:
    DISCORD_TOKEN: str = _require("DISCORD_TOKEN")
    GEMINI_API_KEY: str = _require("GEMINI_API_KEY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    OWNER_ID: int = int(_require("OWNER_DISCORD_ID"))
    CONTEXT_MESSAGES: int = int(os.getenv("CONTEXT_MESSAGES", "100"))
    DEFAULT_MODE: BotMode = _default_mode()
    BOT_TRIGGERS: list[str] = [
        t.strip()
        for t in os.getenv(
            "BOT_TRIGGERS",
            "Geminino,Nino,Gemmi,Gimmi,Jimmy,bottino,mio saggio amico"
        ).split(",")
        if t.strip()
    ]
