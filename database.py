from pymongo import MongoClient

client = MongoClient('mongodb+srv://pugalkmc:pugalkmc@cluster0.dzcnjxc.mongodb.net/')
db = client['aibot']
project_col = db['projects']
user_col = db['users']
profanity_collection = db['profanitys']
mutes_col = db['mutes']
warnings_col = db['warnings']