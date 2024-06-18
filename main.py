import asyncio
from dataclasses import dataclass
import html
from http import HTTPStatus
import logging
import traceback
import uvicorn
from fastapi import Response
from flask import Flask, jsonify, make_response, request
from asgiref.wsgi import WsgiToAsgi
from telegram import Bot, Update
from telegram.constants import ParseMode
from chatbot import message_handler

from uuid import uuid4
from telegram.ext import (
    MessageHandler,
    filters,
    Application
)
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    ContextTypes,
    ExtBot,
    TypeHandler
)
from telegram.error import BadRequest, NetworkError

import admin_operations
import greeting
import config

from database import *

bot = Bot(config.BOT_TOKEN)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

@dataclass
class WebhookUpdate:
    """Simple dataclass to wrap a custom update type"""

    user_id: int
    payload: str

class CustomContext(CallbackContext[ExtBot, dict, dict, dict]):
    """
    Custom CallbackContext class that makes `user_data` available for updates of type
    `WebhookUpdate`.
    """

    @classmethod
    def from_update(
        cls,
        update: object,
        application: "Application",) -> "CustomContext":
        if isinstance(update, WebhookUpdate):
            return cls(application=application, user_id=update.user_id)
        return super().from_update(update, application)


async def webhook_update(update: WebhookUpdate, context: CustomContext) -> None:
    """Handle custom updates."""
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
    """Display a message with instructions on how to use this bot."""
    payload_url = html.escape(f"{config.URL}/submitpayload?user_id=<your user id>&payload=<payload>")
    text = (
        f"To check if the bot is still running, call <code>{config.URL}/healthcheck</code>.\n\n"
        f"To post a custom update, call <code>{payload_url}</code>."
    )
    await update.message.reply_html(text=text)


async def bot_setup_command(update, context):
    chat_id = update.message.chat_id
    if context.args:
        setup_validation = project_col.find_one({ 'registerId': context.args[0] })
        if setup_validation:
            project_col.update_one({ 'registerId':context.args[0] }, {"$set": { 'groupId': chat_id, 'registerId': str(uuid4())}})
            await update.message.reply_text(
            text="Bot setup completed"
            )
            config.settings[chat_id] = admin_operations.default
            config.settings[chat_id]['register'] = True
        else:
            await update.message.reply_text(
            text="Invalid register token"
            )
    else:
        await update.message.reply_text(
            text="Please add register token next to the command"
        )


async def bot_revoke_command(update, context):
    chat_id = update.message.chat_id
    if context.args:
        setup_validation = project_col.find_one({ 'registerId': context.args[0] })
        if setup_validation:
            project_col.update_one({ 'registerId':context.args[0] }, {"$set": { 'groupId': None, 'registerId': str(uuid4())}})
            await update.message.reply_text(
            text="Bot disconnected from the group"
            )
            config.settings[chat_id]['register'] = False
        else:
            await update.message.reply_text(
            text="Invalid register token"
            )
    else:
        await update.message.reply_text(
            text="Please add unregister token next to the command"
        )


async def error(update, context):
    error_message = str(context.error)
    
    # Example of handling BadRequest
    if isinstance(context.error, BadRequest):
        error_message = f"Telegram API returned BadRequest: {context.error.message}"
    elif isinstance(context.error, NetworkError):
        error_message = f"NetworkError occurred: {context.error.message}"
    else:
        error_message = f"Unknown error occurred: {context.error}"

    logger.error(f"Update {update} caused error: {error_message}\n\n")
    print("Error details:", traceback.format_exc())

    # Notify admin or log the error appropriately
    await context.bot.send_message(chat_id=config.ADMIN_CHAT_ID, text=error_message)

async def main() -> None:
    await bot.initialize()

    """Set up PTB application and a web application for handling the incoming requests."""
    context_types = ContextTypes(context=CustomContext)
    # Here we set updater to None because we want our custom webhook server to handle the updates
    # and hence we don't need an Updater instance
    dp = (
        Application.builder().token(config.BOT_TOKEN).updater(None).context_types(context_types).build()
    )

    await dp.initialize()

    # Register handlers
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

    # Pass webhook settings to telegram
    await dp.bot.set_webhook(url=f"{config.URL}/telegram", allowed_updates=Update.ALL_TYPES)

    # Set up webserver
    flask_app = Flask(__name__)

    @flask_app.post("/telegram")  # type: ignore[misc]
    async def telegram() -> Response:
        """Handle incoming Telegram updates by putting them into the `update_queue`"""
        await dp.update_queue.put(Update.de_json(data=request.json, bot=dp.bot))
        return jsonify({"status": "OK"})
    
    @flask_app.route("/submitpayload", methods=["GET", "POST"])
    async def custom_updates() -> Response:
        """
        Handle incoming webhook updates by putting them into the `update_queue` if
        the required parameters were passed correctly.
        """
        try:
            user_id = int(request.args["user_id"])
            payload = request.args["payload"]
        except KeyError:
            return jsonify({"error": "Please pass both `user_id` and `payload` as query parameters."}), HTTPStatus.BAD_REQUEST
        except ValueError:
            return jsonify({"error": "The `user_id` must be an integer."}), HTTPStatus.BAD_REQUEST

        await dp.update_queue.put(WebhookUpdate(user_id=user_id, payload=payload))
        return jsonify({"status": "OK"})
    
    @flask_app.get("/healthcheck")  # type: ignore[misc]
    async def health() -> Response:
        """For the health endpoint, reply with a simple plain text message."""
        return make_response("The bot is still running fine :)", HTTPStatus.OK)
    
    @flask_app.post("/settings")  # type: ignore[misc]
    async def change_settings() -> Response:
        data = request.json
        config.settings[data['groupId']] = data
        return jsonify({"message": f"Settings updated"}), HTTPStatus.OK


    webserver = uvicorn.Server(
        config=uvicorn.Config(
            app=WsgiToAsgi(flask_app),
            port=8443,
            use_colors=False,
            host="0.0.0.0",
        )
    )

    # Run application and webserver together
    async with dp:
        await dp.start()
        await webserver.serve()
        await dp.stop()

# Run FastAPI app
if __name__ == "__main__":
    asyncio.run(main())