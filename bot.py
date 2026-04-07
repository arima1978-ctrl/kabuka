"""Telegram bot: receive period, reply with top-20 decliners report.

Accepted formats:
  2026-03-01 2026-03-31
  2026/03/01 - 2026/03/31
  20260301 20260331
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

import jquants
from analyze import top20_decliners, to_dicts
from format import format_report

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
# Suppress httpx URL logging — it leaks the bot token in journal/stdout
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("kabuka")

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DATE_RE = re.compile(r"(\d{4})[-/]?(\d{2})[-/]?(\d{2})")


def parse_period(text: str) -> tuple[str, str] | None:
    matches = DATE_RE.findall(text)
    if len(matches) < 2:
        return None
    a, b = matches[0], matches[1]
    return f"{a[0]}-{a[1]}-{a[2]}", f"{b[0]}-{b[1]}-{b[2]}"


async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if msg is None:
        return
    await msg.reply_text(
        "株価下落bot稼働中。\n期間を送信してください。\n例: `2026-03-01 2026-03-31`",
        parse_mode=ParseMode.MARKDOWN,
    )


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
        )
        return

    date_from, date_to = period
    await msg.reply_text(f"取得中... {date_from} → {date_to}")

    try:
        client = jquants.from_env()
        rows = top20_decliners(client, date_from, date_to)
    except Exception as e:
        log.exception("analysis failed")
        await msg.reply_text(f"エラー: {e}")
        return

    # Save raw JSON
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


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    log.info("bot polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
