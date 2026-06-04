import os
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


class Config:
    DISCORD_TOKEN: str = _require("DISCORD_TOKEN")
    GEMINI_API_KEY: str = _require("GEMINI_API_KEY")
    OWNER_ID: int = int(_require("OWNER_DISCORD_ID"))
    CONTEXT_MESSAGES: int = int(os.getenv("CONTEXT_MESSAGES", "100"))
    BOT_TRIGGERS: list[str] = [
        t.strip()
        for t in os.getenv(
            "BOT_TRIGGERS",
            "Geminino,Nino,Gemmi,Gimmi,Jimmy,bottino,mio saggio amico"
        ).split(",")
        if t.strip()
    ]
