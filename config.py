from os import getenv
from dotenv import load_dotenv

load_dotenv()

""" General config """
# Set ENV to any value to use webhook instead of polling for bot. Must be set  in prod environment.
ENV = getenv("ENV")
TZ_OFFSET = 8.0  # (UTC+08:00)
JOB_LIMIT_PER_PERSON = 10
BOT_NAME = "@cron_telebot"
HISTORY_LIMIT = 4


""" Telegram config """
BOT_TOKEN = getenv("BOT_TOKEN")
BOTHOST = getenv("BOTHOST")
URL = getenv('URL')
ADMIN_CHAT_ID = getenv('ADMIN_CHAT_ID')

""" DB config """
MONGODB_URL = getenv("MONGODB_URL")

"""OPEN AI"""
OPENAI_API_KEY = getenv("OPENAI_API_KEY")
MODEL_NAME = getenv("MODEL_NAME")

"""Google Gemini"""
GOOGLE_API_KEY = getenv("GOOGLE_API_KEY")
PINECONE_API_KEY = getenv("PINECONE_API_KEY")

async def notify_admin(update, context, error):
    await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text="Error notification:\n"+error)


settings = dict()

