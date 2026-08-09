"""
ETFC Betting bot — Telegram-facing entrypoint for Phase 2.

Deliberately thin. The bot's only real jobs are: greet the user, show a
quick balance check, and launch the Mini App (where all the actual
browsing/betting happens). It talks to the database directly (same models/
services the API uses) rather than calling the HTTP API — there's no
Telegram-auth handshake to do here since these commands already come from
an authenticated Telegram chat.

Run with:  python bot.py
Requires:  ETFC_TELEGRAM_BOT_TOKEN, ETFC_MINI_APP_URL (must be https:// for
           Telegram to accept it as a WebApp url — see app/config.py)
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.services import wallet_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("etfc_bot")


def _mini_app_keyboard(settings) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🥊 Open ETFC Betting", web_app=WebAppInfo(url=settings.mini_app_url))]]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    tg_user = update.effective_user

    db = SessionLocal()
    try:
        user = wallet_service.get_or_create_user_by_telegram_id(db, str(tg_user.id), tg_user.username)
        mode_line = (
            "🟢 Live — real-money wagering is on."
            if settings.wagering_enabled
            else "🟡 Demo mode — play money only, real wagering opens once ETFC/Lottery Service approval is in hand."
        )
        await update.message.reply_text(
            f"Welcome to ETFC Betting, {tg_user.first_name or 'there'}! 🥊\n\n"
            f"{mode_line}\n"
            f"Your balance: {user.wallet.balance} {user.wallet.currency}\n\n"
            "Tap below to see upcoming fights and place bets.",
            reply_markup=_mini_app_keyboard(settings),
        )
    finally:
        db.close()


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    db = SessionLocal()
    try:
        user = wallet_service.get_or_create_user_by_telegram_id(db, str(tg_user.id), tg_user.username)
        await update.message.reply_text(f"Balance: {user.wallet.balance} {user.wallet.currency}")
    finally:
        db.close()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "/start — open ETFC Betting\n"
        "/balance — check your balance\n"
        "/help — this message"
    )


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "ETFC_TELEGRAM_BOT_TOKEN is not set — get one from @BotFather and put it in .env"
        )
    # Ensure tables exist if the bot is started before the API has run once.
    Base.metadata.create_all(bind=engine)

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("help", help_command))
    return application


if __name__ == "__main__":
    app = build_application()
    logger.info("ETFC bot starting (polling mode)...")
    app.run_polling()
