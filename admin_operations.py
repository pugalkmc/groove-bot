import logging
from datetime import datetime, timedelta
from telegram import Update, ChatPermissions, ChatMember
from telegram.ext import CallbackContext
from database import project_col
import config
from database import (
    mutes_col,
    warnings_col
)
import random

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def is_target_bot(update: Update, context: CallbackContext) -> bool:
    bot = context.bot
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        bot_user_id = bot.id
        return target_user_id == bot_user_id
    return False

async def is_admin(update: Update):
    user_id = update.effective_user.id
    chat_admins = await update.effective_chat.get_administrators()
    return any(admin.user.id == user_id for admin in chat_admins)

funny_responses = [
    "Nice try! But I can't perform that action on myself.",
    "I'm flattered, but I can't do that to myself!",
    "Why would you want to do that to your favorite bot?",
    "Oops! It looks like you're trying to perform an operation on me. I can't do that!",
    "I'm here to help, not to take myself out!",
    "That's an interesting request, but I can't comply if I'm the target.",
    "Looks like you tried to perform a command on me. Unfortunately, I can't do that!",
    "Oh no, you can't use that command on me!",
    "I'd love to help, but I can't use that command on myself!",
    "Self-commands are a bit too existential for me. Try it on someone else!",
    "It seems you're trying to command me to do something to myself. I can't do that!",
    "I'm your humble servant, but I can't serve myself with that command.",
    "I appreciate the thought, but self-commands aren't my thing!",
    "I'm invincible to my own commands!",
    "Thanks for the suggestion, but I can't perform that action on myself.",
    "Self-commands? Not in my programming!",
    "I can't perform this action on myself, but I'm here to help you with other things!",
    "That command is a bit self-referential. Try it on another user!",
    "It's cute that you think I can do that to myself, but I can't!",
    "I can do many things, but using that command on myself isn't one of them!"
]

def get_random_funny_response():
    return random.choice(funny_responses)

async def is_bot_admin(update: Update, context: CallbackContext) -> bool:
    bot = context.bot
    chat_id = update.message.chat_id
    bot_member = await bot.get_chat_member(chat_id, bot.id)
    return bot_member.status == ChatMember.ADMINISTRATOR


def admin_only(func):
    async def wrapper(update: Update, context: CallbackContext):
        if not await is_bot_admin(update, context):
            await update.message.reply_text("I need to be an admin to perform this action.")
            return
        if await is_target_bot(update, context):
            await update.message.reply_text(get_random_funny_response())
            return
        elif await is_admin(update):
            return await func(update, context)
        await update.message.delete()
    return wrapper

default = {
    "status": True,
    "rateLimit": True,
    "rateLimitThreshold": 10,
    "rateLimitTimeout": 10,
    "profanityFilter": True,
    "welcomeNewUsers": True,
    "register": False
}

def registered_only(func):
    async def wrapper(update: Update, context: CallbackContext):
        chat_id = update.message.chat_id
        if chat_id not in config.settings or not config.settings[chat_id].get('register', False):
            return
        await func(update, context)
    return wrapper

def settings_check(func):
    async def wrapper(update: Update, context: CallbackContext):
        chat_id = update.message.chat_id
        if chat_id not in config.settings:
            get_project = project_col.find_one({'groupId': chat_id})
            if not get_project:
                config.settings[chat_id] = default
            else:
                config.settings[chat_id] = get_project['controls']
                config.settings[chat_id]['register'] = True
                config.settings[chat_id]['manager'] = str(get_project['manager'])
        return await func(update, context)
    return wrapper

@admin_only
@settings_check
async def kick(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to the message of the user you want to kick.")
        return
    user_id = update.message.reply_to_message.from_user.id
    reason = ' '.join(context.args) if context.args else "No reason provided."
    try:
        await context.bot.ban_chat_member(chat_id=update.message.chat_id, user_id=user_id)
        await context.bot.send_message(chat_id=user_id, text=f"You have been kicked from the group. Reason: {reason}")
        await update.message.delete()
    except Exception as e:
        logger.error(f"Error kicking user: {e}")
        await update.message.reply_text("Failed to kick the user. Please try again.")

@admin_only
@settings_check
async def mute(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to the message of the user you want to mute.")
        return
    user_id = update.message.reply_to_message.from_user.id
    username = update.message.reply_to_message.from_user.username
    try:
        hours = int(context.args[0])
        reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "No reason provided."
    except (IndexError, ValueError):
        hours = 1
        reason = "No reason provided."
    until_date = datetime.now() + timedelta(hours=hours)
    try:
        await context.bot.restrict_chat_member(
            chat_id=update.message.chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        mutes_col.update_one({'user_id': user_id}, {'$set': {'until': until_date}}, upsert=True)
        message_text = f"@{username} has been muted for {hours} hour{'s' if hours > 1 else ''}. Reason: {reason}"
        await context.bot.send_message(chat_id=update.message.chat_id, text=message_text)
        await update.message.delete()
    except Exception as e:
        logger.error(f"Error muting user: {e}")
        await update.message.reply_text("Failed to mute the user. Please try again.")

@admin_only
@settings_check
async def unmute(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to the message of the user you want to unmute.")
        return
    user_id = update.message.reply_to_message.from_user.id
    username = update.message.reply_to_message.from_user.username
    try:
        await context.bot.restrict_chat_member(
            chat_id=update.message.chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=True)
        )
        mutes_col.delete_one({'user_id': user_id})
        await context.bot.send_message(chat_id=update.message.chat_id, text=f"@{username} has been unmuted!")
        await update.message.delete()
    except Exception as e:
        logger.error(f"Error unmuting user: {e}")
        await update.message.reply_text("Failed to unmute the user. Please try again.")

@admin_only
@settings_check
async def warn(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to the message of the user you want to warn.")
        return
    user_id = update.message.reply_to_message.from_user.id
    username = update.message.reply_to_message.from_user.username
    message = "You have been warned\n\nAdmin message:\n" + ' '.join(context.args) if context.args else "You have been warned."
    try:
        warnings_col.update_one({'user_id': user_id}, {'$inc': {'count': 1}}, upsert=True)
        await context.bot.send_message(chat_id=update.message.chat_id, text=f"@{username} {message}")
        await context.bot.send_message(chat_id=user_id, text=message)
        await update.message.delete()
    except Exception as e:
        logger.error(f"Error warning user: {e}")
        await update.message.reply_text("Failed to warn the user. Please try again.")

@admin_only
@settings_check
async def delete(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to the message you want to delete.")
        return
    try:
        await update.message.reply_to_message.delete()
        await update.message.delete()
    except Exception as e:
        logger.error(f"Error deleting message: {e}")
        await update.message.reply_text("Failed to delete the message. Please try again.")

@admin_only
@settings_check
async def pin(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to the message you want to pin.")
        return
    try:
        await context.bot.pin_chat_message(chat_id=update.message.chat_id, message_id=update.message.reply_to_message.message_id)
        await update.message.delete()
    except Exception as e:
        logger.error(f"Error pinning message: {e}")
        await update.message.reply_text("Failed to pin the message. Please try again.")

@admin_only
@settings_check
async def unpin(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to the message you want to unpin.")
        return
    try:
        await context.bot.unpin_chat_message(chat_id=update.message.chat_id, message_id=update.message.reply_to_message.message_id)
        await update.message.delete()
    except Exception as e:
        logger.error(f"Error unpinning message: {e}")
        await update.message.reply_text("Failed to unpin the message. Please try again.")

async def handle_command_from_non_admin(update: Update, context: CallbackContext):
    if await is_bot_admin(update, context):
        await update.message.delete()
   