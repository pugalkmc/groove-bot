from collections import deque
from datetime import datetime, timedelta
import auto_mod
import config
import chatbot_functions
from better_profanity import profanity
from database import profanity_collection
from telegram import ChatPermissions
from pinecone_config import index
from database import project_col
from admin_operations import registered_only, settings_check
profanity.load_censor_words()


async def chat_with_memory(update, limit=3):
    user_id = update.message.from_user.id
    text = update.message.text
    first_name = update.message.from_user.first_name
    username = update.message.from_user.username
    chat_id = update.message.chat_id

    if user_id not in chatbot_functions.chat_memory:
        chatbot_functions.chat_memory[user_id] = deque(maxlen=limit)

    refined_message = text
    if len(chatbot_functions.chat_memory[user_id]) >= 1:
        refined_message = chatbot_functions.client.chat.completions.create(
          model="gpt-4o-mini",
          messages=[
              {"role":"system", "content": chatbot_functions.get_refine_prompt(user_id, text)},
          ]
        ).choices[0].message.content

    message_embed = chatbot_functions.embed_bulk_chunks([refined_message])[0]
    retrieved_chunks = chatbot_functions.perform_search_and_get_chunks(chat_id, index, message_embed)
    system = f"""
{chatbot_functions.system_prompt}

User Details: first name: {first_name}, last name: {username}"""

    response = chatbot_functions.openai_answer(retrieved_chunks, system, user_id, text)
    chatbot_functions.chat_memory[user_id].append((text, response))

    return response

default = {
    "status": True,
    "rateLimit": True,
    "rateLimitThreshold": 10,
    "rateLimitTimeout": 10,
    "profanityFilter": True,
    "welcomeNewUsers": True,
    "register": False
}

async def chat_handler_api(user, text, chat_id, limit=3):
    # print(config.settings)
    user_id = user['_id']
    user_name = user['name']
    user_email = user['email']

    if chat_id not in config.settings:
        get_project = project_col.find_one({'groupId': chat_id})
        if not get_project:
            config.settings[chat_id] = default
        else:
            config.settings[chat_id] = get_project['controls']
            config.settings[chat_id]['register'] = True
            config.settings[chat_id]['manager'] = str(get_project['manager'])
    # chat_id = str(chat_id)
    if user_id not in chatbot_functions.chat_memory:
        chatbot_functions.chat_memory[user_id] = deque(maxlen=limit)

    previous_chat = ""

    for user, system in chatbot_functions.chat_memory[user_id]:
        previous_chat += f"User: {user}\nAI: {system}\n"
    refined_message = text
    if len(chatbot_functions.chat_memory[user_id]) >= 1:
        refined_message = chatbot_functions.client.chat.completions.create(
          model="gpt-4o-mini",
          messages=[
              {"role":"system", "content": chatbot_functions.get_refine_prompt(user_id, text)},
          ]
        ).choices[0].message.content
    
    system = f"""
{chatbot_functions.system_prompt}

User Details:
Name: {user_name}, Email: {user_email}
"""
    
    # print(chat_id, config.settings[chat_id])

    message_embed = chatbot_functions.embed_bulk_chunks([refined_message])[0]
    retrieved_chunks = chatbot_functions.perform_search_and_get_chunks(chat_id, index, message_embed)
    response = chatbot_functions.openai_answer(retrieved_chunks, system, user_id, text)
    chatbot_functions.chat_memory[user_id].append((text, response))
    return response


def escape_markdown_v2(text):
    special_characters = r'_*[]()~`>#+-=|{}.!'
    for char in special_characters:
        text = text.replace(char, f"\\{char}")
    return text


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

        chatbot_functions.chat_memory.setdefault(user_id, deque(maxlen=config.HISTORY_LIMIT)).append((text, "Please avoid using offensive language."))
        return

    if not (is_tagged or is_reply):
        return

    try:
        ai_response = await chat_with_memory(update)
        markdown_response = escape_markdown_v2(ai_response)
        await update.message.reply_text(text=markdown_response, parse_mode="MarkdownV2")
    except Exception as error:
        print(f"Error processing message: {error}")
        await context.bot.send_message(chat_id=config.ADMIN_CHAT_ID, text=f"Error processing message from {first_name}: {error}")