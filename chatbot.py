import asyncio
import time
from collections import deque
from datetime import datetime, timedelta
import traceback

import auto_mod
import config
import gemini_config
from better_profanity import profanity
from database import profanity_collection
from telegram import ChatPermissions
from pinecone_config import index
from admin_operations import registered_only, settings_check
profanity.load_censor_words()
chat_memory = {}


async def chat_with_memory(update, limit=3):
    user_id = update.message.from_user.id
    text = update.message.text
    first_name = update.message.from_user.first_name
    username = update.message.from_user.username
    chat_id = update.message.chat_id
    if user_id not in chat_memory:
        chat_memory[user_id] = deque(maxlen=limit)

    previous_chat = ""

    for user, system in chat_memory[user_id]:
        previous_chat += f"User: {user}\nAI: {system}\n"

    refined_message = text
    if len(chat_memory[user_id]) >= 1:
        refined_message = gemini_config.client.chat.completions.create(
          model="gpt-3.5-turbo",
          messages=[
              {"role":"system", "content": f"Refine user the query based on the previous chat history between the AI assistant and user as shorter. It must be refined based on the project details as well\n\nAdd as much as details in the defined query gather them from chat history and user message\nprevious chat: {previous_chat}\nNew user message: {text}\n\nIMPORTANT: Return the refined query string only, no need of any other additional details"},
          ]
        ).choices[0].message.content
        print(text, refined_message)

    message_embed = gemini_config.embed_bulk_chunks([refined_message])[0]
    retrieved_chunks = gemini_config.perform_search_and_get_chunks(chat_id, index, message_embed)
    system = f"""You are a helpful and friendly person. Follow up the conversation naturally and respond to the user based on the provided information.
Try to:
Help your with provided details details
Be concise and conversational, Provide refined answer to make understand the user.
Latest information based on the annoucement time and current time
provide source links properly if user needs
Your are internal system, if you face any difficulties to answer with provided details, don't expose with your response
Try stick with project details only
never try to embed links
Provide most up to date information you have and accurate data to the user available from the context
Analys deeply and answer

Current Date and Time: {datetime.now()}

Never do:
Avoid phrases like "in this context" or "based on the context provided."
Keep responses simple and add as much as details as you can based on the response

Your Name: Groove AI

User Details: first name: {first_name}, last name: {username}"""

    #     template = f"""
    # {system}
    # User first name: {first_name}
    # conversation:
    # """

    #     template += previous_chat
    #     template += f"User: {text}\n"

    # template = f"{system}\n"
    # template += f"User first name: {first_name}"
    # template += previous_chat

    # response = gemini_config.generate_answer(retrieved_chunks, template)
    response = gemini_config.openai_answer(retrieved_chunks, system, chat_memory[user_id], text)

    chat_memory[user_id].append((text, response))

    if len(chat_memory[user_id]) > limit:
        chat_memory[user_id].popleft()

    return response

@settings_check
@registered_only
async def message_handler(update, context):
    chat_type = update.message.chat.type
    user_id = update.message.from_user.id
    text = update.message.text
    first_name = update.message.from_user.first_name
    username = update.message.from_user.username
    chat_id = update.message.chat_id

    bot_username = context.bot.username

    if chat_type == "private":
        await update.message.reply_text(
            text="I'm only available for group chats"
        )
        return

    if not auto_mod.check_and_record(user_id, chat_id):
        until_date = datetime.now() + timedelta(minutes=config.settings[chat_id]['rateLimitTimeout'])
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        await context.bot.send_message(chat_id=chat_id, text=f"@{username} You have been muted for 10 minutes\nReason: Message flooding")
        return

    is_tagged = f'@{bot_username}' in text
    is_reply = update.message.reply_to_message is not None and update.message.reply_to_message.from_user.username == bot_username

    if is_tagged:
        text = text.replace(f'@{bot_username}', 'Goat AI')

    if profanity.contains_profanity(text):
        await update.message.delete()

        user_history = profanity_collection.find_one({"user_id": user_id}) or {"offense_count": 0}
        offense_count = user_history['offense_count'] + 1

        profanity_collection.update_one(
            {"user_id": user_id},
            {"$set": {"offense_count": offense_count}},
            upsert=True
        )

        if offense_count >= config.BAN_THRESHOLD:
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await context.bot.send_message(chat_id=chat_id, text=f"{first_name} has been banned due to repeated offensive language.")
        elif offense_count >= config.MUTE_THRESHOLD:
            permissions = ChatPermissions(can_send_messages=False)
            await context.bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=permissions)
            await context.bot.send_message(chat_id=chat_id, text=f"{first_name} has been muted due to repeated offensive language.")
        else:
            await context.bot.send_message(chat_id=chat_id, text=f"Hey @{username}, please avoid offensive language")

        chat_memory.setdefault(user_id, deque(maxlen=config.HISTORY_LIMIT)).append((text, "Please avoid using offensive language."))
        return

    if not (is_tagged or is_reply):
        return

    try:
        ai_response = await chat_with_memory(update)
        await update.message.reply_text(text=ai_response, parse_mode="html")
    except Exception as error:
        print(f"Error processing message: {error}")
        await context.bot.send_message(chat_id=config.ADMIN_CHAT_ID, text=f"Error processing message from {first_name}: {error}")