from __future__ import annotations

from typing import Any

ScreenData = dict[str, Any]

_contexts: dict[int, ScreenData] = {}


def set_screen(user_id: int, screen: str, **data: Any) -> None:
    _contexts[user_id] = {"screen": screen, **data}


def get_screen(user_id: int) -> ScreenData:
    return _contexts.get(user_id, {"screen": "menu"})
