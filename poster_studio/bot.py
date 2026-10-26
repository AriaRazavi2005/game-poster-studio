"""
poster_studio.bot
~~~~~~~~~~~~~~~~~
Standalone aiogram 3.x Telegram Bot for @BazyePc.
Supports single-photo poster framing, album auto-collaging, caption parsing
('Title | Subtitle | Badge'), inline preset/ratio switching, and ADMIN_IDS security.
Run with: python -m poster_studio.bot
"""

from __future__ import annotations

import asyncio
import io
import os
from typing import Dict, List, Optional, Tuple

from poster_studio.core.presets import list_presets
from poster_studio.core.collage import list_collage_templates
from poster_studio.telegram_bridge import create_game_poster, create_game_collage, poster_to_bytes

# Per-user session preferences (preset, ratio, template)
_USER_STATE: Dict[int, Dict[str, str]] = {}
_ALBUM_BUFFER: Dict[str, List[bytes]] = {}


def parse_caption_parts(caption: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Splits 'Title | Subtitle | Badge' from Telegram photo caption."""
    if not caption:
        return None, None, None
    parts = [p.strip() for p in caption.split("|")]
    title = parts[0] if len(parts) >= 1 and parts[0] else None
    subtitle = parts[1] if len(parts) >= 2 and parts[1] else None
    badge = parts[2] if len(parts) >= 3 and parts[2] else None
    return title, subtitle, badge


async def run_bot() -> None:
    try:
        from aiogram import Bot, Dispatcher, F, Router
        from aiogram.types import (
            BufferedInputFile,
            CallbackQuery,
            InlineKeyboardButton,
            InlineKeyboardMarkup,
            Message,
        )
        from aiogram.filters import Command
    except ImportError as exc:
        raise RuntimeError("aiogram 3.x is required for bot mode. Install via: pip install .[bot]") from exc

    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is required.")

    admin_raw = os.environ.get("ADMIN_IDS", "")
    admin_ids = {int(x.strip()) for x in admin_raw.split(",") if x.strip().isdigit()}

    bot = Bot(token=token)
    dp = Dispatcher()
    router = Router()

    def _is_allowed(user_id: int) -> bool:
        return not admin_ids or (user_id in admin_ids)

    def _build_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⚽ Sports", callback_data="preset:sports"),
                InlineKeyboardButton(text="🩸 Horror", callback_data="preset:horror"),
                InlineKeyboardButton(text="🐉 RPG", callback_data="preset:fantasy_rpg"),
                InlineKeyboardButton(text="🤖 Cyber", callback_data="preset:cyberpunk"),
            ],
            [
                InlineKeyboardButton(text="📐 4:5", callback_data="ratio:4:5"),
                InlineKeyboardButton(text="📐 1:1", callback_data="ratio:1:1"),
                InlineKeyboardButton(text="📐 9:16", callback_data="ratio:9:16"),
                InlineKeyboardButton(text="🇮🇷 فارسی", callback_data="preset:persian_bold"),
            ],
        ])

    @router.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        if not message.from_user or not _is_allowed(message.from_user.id):
            return
        await message.reply(
            "🎮 **Game Poster Studio v2 (@BazyePc)**\n"
            "• یک عکس بفرست تا پوستر قاب‌بندی شود.\n"
            "• چند عکس (آلبوم) بفرست تا کلاژ ساخته شود.\n"
            "• کپشن عکس را به فرمت `عنوان | زیرعنوان | برچسب` بنویس.",
            reply_markup=_build_keyboard(),
        )

    @router.message(Command("presets"))
    async def cmd_presets(message: Message) -> None:
        lines = [f"• `{k}`: {v.get('description', '')}" for k, v in list_presets().items()]
        await message.reply("🎨 **Preset List:**\n" + "\n".join(lines))

    @router.message(Command("templates"))
    async def cmd_templates(message: Message) -> None:
        lines = [f"• `{k}` ({v['slots']}x): {v['name']}" for k, v in list_collage_templates().items()]
        await message.reply("🧩 **Collage Templates (22):**\n" + "\n".join(lines))

    @router.callback_query()
    async def handle_callback(query: CallbackQuery) -> None:
        if not query.from_user or not query.data:
            return
        uid = query.from_user.id
        state = _USER_STATE.setdefault(uid, {"preset": "bazyepc_default", "ratio": "4:5", "template": "auto"})
        kind, val = query.data.split(":", 1)
        state[kind] = val
        await query.answer(f"Set {kind} = {val}")

    @router.message(F.photo)
    async def handle_photo(message: Message) -> None:
        if not message.from_user or not _is_allowed(message.from_user.id) or not message.photo:
            return
        uid = message.from_user.id
        state = _USER_STATE.setdefault(uid, {"preset": "bazyepc_default", "ratio": "4:5", "template": "auto"})

        bio = io.BytesIO()
        await bot.download(message.photo[-1], destination=bio)
        raw_bytes = bio.getvalue()
        title, subtitle, badge = parse_caption_parts(message.caption)

        # Album / Media Group -> Auto Collage
        if message.media_group_id:
            mgid = message.media_group_id
            buf = _ALBUM_BUFFER.setdefault(mgid, [])
            buf.append(raw_bytes)
            if len(buf) > 1:
                return
            await asyncio.sleep(1.2)
            images_bytes = _ALBUM_BUFFER.pop(mgid, [])
            collage_img = create_game_collage(
                input_images=images_bytes,
                ratio=state["ratio"],
                template=state["template"],
                title=title,
                subtitle=subtitle,
                badge=badge,
            )
            out_bytes = poster_to_bytes(collage_img)
            await message.reply_photo(
                BufferedInputFile(out_bytes, filename="collage.jpg"),
                caption="🎮 @BazyePc Collage",
                reply_markup=_build_keyboard(),
            )
            return

        poster_img = create_game_poster(
            input_image=raw_bytes,
            ratio=state["ratio"],
            preset=state["preset"],
            title=title,
            subtitle=subtitle,
            badge=badge,
        )
        out_bytes = poster_to_bytes(poster_img)
        await message.reply_photo(
            BufferedInputFile(out_bytes, filename="poster.jpg"),
            caption="🎮 @BazyePc",
            reply_markup=_build_keyboard(),
        )

    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run_bot())
