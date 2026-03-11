import asyncio
import json
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from bson import ObjectId

# Custom JSON encoder to handle MongoDB ObjectIds and Datetimes
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

async def check_data():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.tax_agent
    
    print("\n" + "="*50)
    print("📊 MongoDB Data Check - 'corporates' Collection")
    print("="*50)
    
    # Retrieve all corporates, sorted by creation date (newest first)
    cursor = db.corporates.find().sort("created_at", -1)
    documents = await cursor.to_list(length=100)
    
    emp_cursor = db.employees.find().sort("created_at", -1)
    emp_documents = await emp_cursor.to_list(length=100)
    
    if not documents and not emp_documents:
        print("\n📭 No data found in the database yet.")
        return

    print(f"\n✅ Found {len(documents)} records:\n")
    
    # Print a summary table-like format for quick glancing
    print(f"{'TYPE':<15} | {'COMPANY NAME':<25} | {'EMAIL/LOGIN':<25} | {'ADVISING TAX FIRM ID'}")
    print("-" * 100)
    for doc in documents:
        corp_type = doc.get("corporateType", "unknown")
        name = doc.get("companyName", "N/A")
        email = doc.get("loginEmail", "N/A")
        adviser = doc.get("advising_tax_firm_id", "None")
        print(f"{corp_type:<15} | {name:<25} | {email:<25} | {adviser}")
    
    print("\n" + "="*50)
    print("📝 Detailed JSON View:")
    print("="*50)
    
    if documents:
        # Print the full JSON data neatly formatted
        print(json.dumps(documents, cls=MongoJSONEncoder, indent=2, ensure_ascii=False))
        
    if emp_documents:
        print("\n" + "="*50)
        print("📊 MongoDB Data Check - 'employees' Collection")
        print("="*50)
        print(f"\n✅ Found {len(emp_documents)} employee records:\n")
        print(json.dumps(emp_documents, cls=MongoJSONEncoder, indent=2, ensure_ascii=False))
    
    print("\n" + "="*50)

if __name__ == "__main__":
    asyncio.run(check_data())
