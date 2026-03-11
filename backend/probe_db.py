import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["tax_agent_db"]
    employees = await db["employees"].find().to_list(10)
    corporates = await db["corporates"].find().to_list(10)
    
    print("--- EMPLOYEES ---")
    for e in employees:
        print(f"UID: {e.get('firebase_uid')}, Parent: {e.get('parent_corporate_id')}")
        
    print("\n--- CORPORATES ---")
    for c in corporates:
        print(f"UID: {c.get('firebase_uid')}, Type: {c.get('corporateType')}")

if __name__ == "__main__":
    asyncio.run(main())
