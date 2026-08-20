"""Per-channel mode persistence."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from config import Config
from policy import BotMode

log = logging.getLogger(__name__)

_FILE = Path(__file__).resolve().parent / "data" / "modes.json"
_lock = asyncio.Lock()
_cache: dict[str, BotMode] | None = None


def default_mode() -> BotMode:
    return Config.DEFAULT_MODE


def _load() -> dict[str, BotMode]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _cache = {}
    return _cache


def _save(store: dict[str, BotMode]) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")


async def get_channel_mode(channel_id: int | str) -> BotMode:
    async with _lock:
        return _load().get(str(channel_id), default_mode())


async def set_channel_mode(channel_id: int | str, mode: BotMode) -> BotMode:
    async with _lock:
        store = _load()
        store[str(channel_id)] = mode
        try:
            _save(store)
        except OSError:
            # Losing the file only costs the persisted default; the mode still
            # applies for this process.
            log.exception("Could not persist channel modes to %s", _FILE)
        return mode
