"""Telegram bot: receive period (text or calendar), reply with top-20 decliners report.

Accepted text formats:
  2026-03-01 2026-03-31
  2026/03/01 - 2026/03/31
  20260301 20260331

Or use the 📅 button / /calendar command to pick dates from a calendar.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram_bot_calendar import LSTEP, DetailedTelegramCalendar

import jquants
from analyze import top20_decliners, to_dicts
from format import format_report

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("kabuka")

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DATE_RE = re.compile(r"(\d{4})[-/]?(\d{2})[-/]?(\d{2})")
CAL_ID_FROM = 1
CAL_ID_TO = 2

STEP_LABEL_JA = {"y": "年", "m": "月", "d": "日"}


def parse_period(text: str) -> tuple[str, str] | None:
    matches = DATE_RE.findall(text)
    if len(matches) < 2:
        return None
    a, b = matches[0], matches[1]
    return f"{a[0]}-{a[1]}-{a[2]}", f"{b[0]}-{b[1]}-{b[2]}"


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("📅 期間を選ぶ", callback_data="open_calendar")]]
    )


async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if msg is None:
        return
    await msg.reply_text(
        "株価下落bot稼働中。\n"
        "下のボタンでカレンダーから期間を選ぶか、\n"
        "テキストで期間を送信してください。\n"
        "例: `2026-03-01 2026-03-31`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_keyboard(),
    )


async def cmd_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _start_calendar(update, context, picking="from")


async def _start_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE, picking: str) -> None:
    msg = update.effective_message
    if msg is None:
        return
    context.chat_data["picking"] = picking
    cal_id = CAL_ID_FROM if picking == "from" else CAL_ID_TO
    calendar, step = DetailedTelegramCalendar(calendar_id=cal_id).build()
    label = "開始日" if picking == "from" else "終了日"
    await msg.reply_text(
        f"{label}を選択してください ({STEP_LABEL_JA.get(step, step)})",
        reply_markup=calendar,
    )


async def on_open_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    context.chat_data.pop("from_date", None)
    await _start_calendar(update, context, picking="from")


async def on_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    picking = context.chat_data.get("picking", "from")
    cal_id = CAL_ID_FROM if picking == "from" else CAL_ID_TO

    result, key, step = DetailedTelegramCalendar(calendar_id=cal_id).process(query.data)

    if not result and key:
        label = "開始日" if picking == "from" else "終了日"
        await query.edit_message_text(
            f"{label}を選択してください ({STEP_LABEL_JA.get(step, step)})",
            reply_markup=key,
        )
        return

    if not result:
        return

    selected = result.strftime("%Y-%m-%d")

    if picking == "from":
        context.chat_data["from_date"] = selected
        await query.edit_message_text(f"開始日: {selected}")
        await _start_calendar(update, context, picking="to")
        return

    # picking == "to"
    from_date = context.chat_data.get("from_date")
    if not from_date:
        await query.edit_message_text("開始日が未選択です。/calendar からやり直してください。")
        return

    to_date = selected
    if to_date < from_date:
        from_date, to_date = to_date, from_date
    await query.edit_message_text(f"期間: {from_date} → {to_date}")
    await _run_analysis(update, from_date, to_date)


async def _run_analysis(update: Update, date_from: str, date_to: str) -> None:
    msg = update.effective_message
    if msg is None:
        return
    await msg.reply_text(f"取得中... {date_from} → {date_to}")
    try:
        client = jquants.from_env()
        rows = top20_decliners(client, date_from, date_to)
    except Exception as e:
        log.exception("analysis failed")
        await msg.reply_text(f"エラー: {e}")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = DATA_DIR / f"{date_from}_{date_to}_{stamp}.json"
    out.write_text(
        json.dumps(
            {"from": date_from, "to": date_to, "rows": to_dicts(rows)},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    log.info("saved %s", out)

    report = format_report(rows, date_from, date_to)
    await msg.reply_text(report, parse_mode=ParseMode.MARKDOWN)


async def handle_message(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if msg is None:
        return
    text = msg.text or ""
    period = parse_period(text)
    if not period:
        await msg.reply_text(
            "期間を認識できませんでした。例: `2026-03-01 2026-03-31`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_keyboard(),
        )
        return
    date_from, date_to = period
    await _run_analysis(update, date_from, date_to)


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("calendar", cmd_calendar))
    # Channel posts: CommandHandler doesn't catch them, use MessageHandler with regex
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST & filters.Regex(r"^/start(@\w+)?\b"), cmd_start))
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST & filters.Regex(r"^/calendar(@\w+)?\b"), cmd_calendar))
    app.add_handler(CallbackQueryHandler(on_open_calendar, pattern="^open_calendar$"))
    app.add_handler(CallbackQueryHandler(on_calendar, pattern="^cbcal_"))
    app.add_handler(MessageHandler((filters.TEXT & ~filters.COMMAND) | (filters.UpdateType.CHANNEL_POST & filters.TEXT & ~filters.COMMAND), handle_message))
    log.info("bot polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
