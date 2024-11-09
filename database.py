from pymongo import MongoClient
from config import MONGODB_URL

client = MongoClient(MONGODB_URL)
db = client['aibot']
project_col = db['projects']
user_col = db['users']
profanity_collection = db['profanitys']
mutes_col = db['mutes']
warnings_col = db['warnings']