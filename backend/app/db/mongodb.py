from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

class MongoDB:
    client: AsyncIOMotorClient = None
    db = None

db_ctx = MongoDB()

async def connect_to_mongo():
    print("Connecting to MongoDB...")
    db_ctx.client = AsyncIOMotorClient(settings.MONGODB_URI)
    db_ctx.db = db_ctx.client[settings.MONGODB_DB_NAME]
    print("Connected to MongoDB!")

async def close_mongo_connection():
    print("Closing MongoDB connection...")
    if db_ctx.client:
        db_ctx.client.close()
    print("MongoDB connection closed.")

def get_database():
    return db_ctx.db
