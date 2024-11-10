import os
os.environ['USER_AGENT'] = 'pugal'
import os
import asyncio
from dataclasses import dataclass
import html
from http import HTTPStatus
import logging
import traceback
from fastapi import FastAPI, Response
from flask import Flask, jsonify, make_response, request
from asgiref.wsgi import WsgiToAsgi
from telegram import Bot, Update
from telegram.constants import ParseMode
from message_handler import message_handler
from admin_operations import settings_check, admin_only
from uuid import uuid4
from telegram.ext import (
    MessageHandler,
    filters,
    Application,
    CommandHandler,
    CallbackContext,
    ContextTypes,
    ExtBot,
    TypeHandler
)
from telegram.error import BadRequest, NetworkError
from database import project_col
import admin_operations
import greeting
import config
from message_handler import chat_memory

bot = Bot(config.BOT_TOKEN)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.INFO)

logger = logging.getLogger(__name__)

@dataclass
class WebhookUpdate:
    """Simple dataclass to wrap a custom update type"""
    user_id: int
    payload: str

class CustomContext(CallbackContext[ExtBot, dict, dict, dict]):
    @classmethod
    def from_update(
        cls,
        update: object,
        application: "Application",) -> "CustomContext":
        if isinstance(update, WebhookUpdate):
            return cls(application=application, user_id=update.user_id)
        return super().from_update(update, application)

async def webhook_update(update: WebhookUpdate, context: CustomContext) -> None:
    chat_member = await context.bot.get_chat_member(chat_id=update.user_id, user_id=update.user_id)
    payloads = context.user_data.setdefault("payloads", [])
    payloads.append(update.payload)
    combined_payloads = "</code>\n• <code>".join(payloads)
    text = (
        f"The user {chat_member.user.mention_html()} has sent a new payload. "
        f"So far they have sent the following payloads: \n\n• <code>{combined_payloads}</code>"
    )
    await update.message.reply_text(text=text, parse_mode=ParseMode.HTML)

async def start_web(update: Update, context: CustomContext) -> None:
    payload_url = html.escape(f"{config.URL}/submitpayload?user_id=<your user id>&payload=<payload>")
    text = (
        f"To check if the bot is still running, call <code>{config.URL}/healthcheck</code>.\n\n"
        f"To post a custom update, call <code>{payload_url}</code>."
    )
    await update.message.reply_html(text=text)

@admin_only
@settings_check
async def bot_setup_command(update, context):
    chat_id = update.message.chat_id
    if context.args:
        setup_validation = project_col.find_one({ 'registerId': context.args[0] })
        if not setup_validation:
            await update.message.reply_text(
                text="Invalid register token"
            )
            return

        if setup_validation and setup_validation['groupId']:
            await update.message.reply_text(
                text="Since the bot is already a member of another group, try using the unregister command on the current group to unlink it before attempting to register here."
            )
            return

        project_col.update_one({ 'registerId':context.args[0] }, {"$set": { 'groupId': chat_id, 'registerId': str(uuid4())}})
        await update.message.reply_text(
        text="Bot setup completed"
        )
        config.settings[chat_id] = admin_operations.default
        config.settings[chat_id]['register'] = True
        config.settings[chat_id]['manager'] = str(setup_validation['manager'])
    else:
        await update.message.reply_text(
            text="Please add register token next to the command"
        )

@settings_check
@admin_only
async def bot_revoke_command(update, context):
    chat_id = update.message.chat_id
    if context.args:
        setup_validation = project_col.find_one({ 'registerId': context.args[0] })
        if not setup_validation:
            await update.message.reply_text(
                text="Invalid register token"
            )
        
        if setup_validation and not setup_validation['groupId']:
            await update.message.reply_text(
                text="You're attempting to unregister, but the bot hasn't registered yet."
            )

        if setup_validation:
            project_col.update_one({ 'registerId':context.args[0] }, {"$set": { 'groupId': None, 'registerId': str(uuid4())}})
            await update.message.reply_text(
            text="Bot disconnected from the group"
            )
            config.settings[chat_id]['register'] = False
            chat_memory = {}
    else:
        await update.message.reply_text(
            text="Please add unregister token next to the command"
        )

async def error(update, context):
    error_message = str(context.error)
    if isinstance(context.error, BadRequest):
        error_message = f"Telegram API returned BadRequest: {context.error.message}"
    elif isinstance(context.error, NetworkError):
        error_message = f"NetworkError occurred: {context.error.message}"
    else:
        error_message = f"Unknown error occurred: {context.error}"

    logger.error(f"Update {update} caused error: {error_message}\n\n")
    print("Error details:", traceback.format_exc())

    await context.bot.send_message(chat_id=config.ADMIN_CHAT_ID, text=error_message)

async def create_app() -> FastAPI:
    await bot.initialize()

    context_types = ContextTypes(context=CustomContext)
    dp = (
        Application.builder().token(config.BOT_TOKEN).updater(None).context_types(context_types).build()
    )

    await dp.initialize()

    dp.add_handler(CommandHandler("kick", admin_operations.kick))
    dp.add_handler(CommandHandler("mute", admin_operations.mute))
    dp.add_handler(CommandHandler("unmute", admin_operations.unmute))
    dp.add_handler(CommandHandler("warn", admin_operations.warn))
    dp.add_handler(CommandHandler("delete", admin_operations.delete))
    dp.add_handler(CommandHandler("pin", admin_operations.pin))
    dp.add_handler(CommandHandler("unpin", admin_operations.unpin))
    dp.add_handler(CommandHandler("register", bot_setup_command))
    dp.add_handler(CommandHandler("unregister", bot_revoke_command))
    dp.add_handler(MessageHandler(filters.TEXT, message_handler))
    dp.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greeting.new_member))
    dp.add_handler(MessageHandler(filters.COMMAND, admin_operations.handle_command_from_non_admin))
    dp.add_handler(TypeHandler(type=WebhookUpdate, callback=webhook_update))
    dp.add_error_handler(error)

    await dp.bot.set_webhook(url=f"{config.URL}/telegram", allowed_updates=Update.ALL_TYPES)

    flask_app = Flask(__name__)

    @flask_app.post("/telegram")
    async def telegram() -> Response:
        try:
            update = Update.de_json(request.get_json(force=True), bot)
            await dp.process_update(update)
        except Exception as e:
            logger.error(f"Error processing update: {e}")
            logger.error(traceback.format_exc())
        return make_response(jsonify({"status": "ok"}), HTTPStatus.OK)

    app = FastAPI()

    asgi_app = WsgiToAsgi(flask_app)
    app.mount("/", asgi_app)

    @app.on_event("startup")
    async def startup():
        await dp.start()
        logger.info("Application startup complete.")

    @app.on_event("shutdown")
    async def shutdown():
        await dp.stop()

    return app
