import random
from telegram import Update
from telegram.ext import CallbackContext
from admin_operations import settings_check

# Lists of welcome messages with different parameter combinations
welcome_messages = [
    "Welcome, {first_name}! Great to have you with us.",
    "Hi {first_name}, welcome aboard!",
    "Hello {first_name}, glad you could join us!",
    "Hey {first_name}, welcome to the group!",
    "Greetings {first_name}, we're excited to have you here!",
    "Welcome to {group_name}! We're delighted to have you.",
    "Hello and welcome to {group_name}!",
    "Hi there! Welcome to {group_name}.",
    "Greetings! Welcome to {group_name}.",
    "Welcome aboard to {group_name}! Enjoy your stay.",
    "Welcome, @{username}! Great to have you with us.",
    "Hi @{username}, welcome aboard!",
    "Hello @{username}, glad you could join us!",
    "Hey @{username}, welcome to the group!",
    "Greetings @{username}, we're excited to have you here!",
    "Welcome, {first_name}, to {group_name}! Great to have you with us.",
    "Hi {first_name}, welcome aboard to {group_name}!",
    "Hello {first_name}, glad you could join {group_name}!",
    "Hey {first_name}, welcome to {group_name}!",
    "Greetings {first_name}, we're excited to have you here at {group_name}!",
    "Welcome, {first_name} (@{username}), to {group_name}! Great to have you with us.",
    "Hi {first_name} (@{username}), welcome aboard to {group_name}!",
    "Hello {first_name} (@{username}), glad you could join {group_name}!",
    "Hey {first_name} (@{username}), welcome to {group_name}!",
    "Greetings {first_name} (@{username}), we're excited to have you here at {group_name}!"
]

welcome_messages_without_username = [
    "Welcome, {first_name}! Great to have you with us.",
    "Hi {first_name}, welcome aboard!",
    "Hello {first_name}, glad you could join us!",
    "Hey {first_name}, welcome to the group!",
    "Greetings {first_name}, we're excited to have you here!",
    "Welcome to {group_name}! We're delighted to have you.",
    "Hello and welcome to {group_name}!",
    "Hi there! Welcome to {group_name}.",
    "Greetings! Welcome to {group_name}.",
    "Welcome aboard to {group_name}! Enjoy your stay.",
    "Welcome, {first_name}, to {group_name}! Great to have you with us.",
    "Hi {first_name}, welcome aboard to {group_name}!",
    "Hello {first_name}, glad you could join {group_name}!",
    "Hey {first_name}, welcome to {group_name}!",
    "Greetings {first_name}, we're excited to have you here at {group_name}!"
]


def random_welcome_message(first_name, username, group_name):
    # Choose a random welcome message
    if username == "unknown":
        welcome_message = random.choice(welcome_messages_without_username)
    else:
        welcome_message = random.choice(welcome_messages)
    filled_message = welcome_message.format(first_name=first_name, username=username, group_name=group_name)
    return filled_message

@settings_check
async def new_member(update: Update, context: CallbackContext):
    for new_member in update.message.new_chat_members:
        adder = update.message.from_user

        if new_member.id != adder.id:
            continue

        first_name = new_member.first_name
        username = new_member.username if new_member.username else "unknown"
        group_name = update.message.chat.title
        
        # Send the welcome message to the group
        await context.bot.send_message(chat_id=update.message.chat_id, text=random_welcome_message(first_name, username, group_name))