import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "tax_agent"

async def migrate():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    
    collections = await db.list_collection_names()
    
    if "bank_transactions" in collections:
        print("Renaming 'bank_transactions' to 'transactions'...")
        await db["bank_transactions"].rename("transactions")
        print("Successfully renamed collection.")
    else:
        print("'bank_transactions' collection not found. Skipping rename.")
        
    client.close()

if __name__ == "__main__":
    asyncio.run(migrate())
