"""Keep inline keyboards only on the latest bot message in a chat."""
from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message

from database import (
    add_ui_keyboard_message,
    clear_ui_keyboard_messages,
    list_ui_keyboard_messages,
    remove_ui_keyboard_message,
)

# In-memory mirror of DB (survives within one process; DB survives restarts)
_last_keyboard_messages: dict[int, set[int]] = {}


def _memory_ids(chat_id: int) -> set[int]:
    return _last_keyboard_messages.setdefault(chat_id, set())


async def _known_keyboard_ids(chat_id: int) -> set[int]:
    ids = set(await list_ui_keyboard_messages(chat_id))
    ids |= _memory_ids(chat_id)
    _last_keyboard_messages[chat_id] = set(ids)
    return ids


async def _strip_keyboard(bot: Bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=None,
        )
    except TelegramBadRequest:
        pass
    _memory_ids(chat_id).discard(message_id)
    await remove_ui_keyboard_message(chat_id, message_id)


async def track_keyboard_message(message: Message) -> None:
    chat_id = message.chat.id
    mid = message.message_id
    _memory_ids(chat_id).add(mid)
    await add_ui_keyboard_message(chat_id, mid)


async def detach_keyboards(
    bot: Bot,
    chat_id: int,
    *,
    keep_message_id: int | None = None,
    also_message_ids: list[int] | None = None,
) -> None:
    """Remove inline keyboards from all known messages in this chat."""
    ids = await _known_keyboard_ids(chat_id)
    if also_message_ids:
        ids.update(also_message_ids)
    for mid in list(ids):
        if keep_message_id is not None and mid == keep_message_id:
            continue
        await _strip_keyboard(bot, chat_id, mid)
    await clear_ui_keyboard_messages(chat_id, keep_message_id=keep_message_id)
    if keep_message_id is None:
        _last_keyboard_messages.pop(chat_id, None)
    else:
        _last_keyboard_messages[chat_id] = {keep_message_id}


async def answer_tracked(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    **kwargs,
) -> Message:
    # Strip tracked keyboards + the message we are answering under (callback source)
    await detach_keyboards(
        message.bot,
        message.chat.id,
        also_message_ids=[message.message_id],
    )
    sent = await message.answer(text, reply_markup=reply_markup, **kwargs)
    if reply_markup is not None:
        await track_keyboard_message(sent)
    return sent


async def answer_done(message: Message, text: str) -> Message:
    """Send a single success message (no separate dice)."""
    return await answer_tracked(message, text)


async def answer_photo_tracked(
    message: Message,
    photo,
    *,
    caption: str | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
    **kwargs,
) -> Message:
    await detach_keyboards(
        message.bot,
        message.chat.id,
        also_message_ids=[message.message_id],
    )
    sent = await message.answer_photo(
        photo,
        caption=caption,
        reply_markup=reply_markup,
        **kwargs,
    )
    if reply_markup is not None:
        await track_keyboard_message(sent)
    return sent


async def edit_text_tracked(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    """Edit text in place; optionally keep keyboard on this same message."""
    await detach_keyboards(
        message.bot,
        message.chat.id,
        keep_message_id=message.message_id if reply_markup is not None else None,
        also_message_ids=None,
    )
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        msg = (exc.message or "").lower()
        if "message is not modified" in msg:
            if reply_markup is not None:
                await track_keyboard_message(message)
            return True
        if "no text in the message" in msg or "message can't be edited" in msg:
            return False
        raise
    if reply_markup is not None:
        await track_keyboard_message(message)
    else:
        await clear_ui_keyboard_messages(message.chat.id)
        _last_keyboard_messages.pop(message.chat.id, None)
    return True
