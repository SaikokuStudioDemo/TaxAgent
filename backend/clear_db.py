import asyncio
import os
import firebase_admin
from firebase_admin import credentials, auth, firestore
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB_NAME", "tax_agent_db")
FIREBASE_CREDS = os.getenv("FIREBASE_CREDENTIALS_PATH")

def initialize_firebase():
    if not firebase_admin._apps:
        if FIREBASE_CREDS and os.path.exists(FIREBASE_CREDS):
            cred = credentials.Certificate(FIREBASE_CREDS)
            firebase_admin.initialize_app(cred)
            print("Firebase Admin initialized using credentials file.")
        else:
            print("WARNING: Could not find FIREBASE_CREDENTIALS_PATH. Using default credentials.")
            firebase_admin.initialize_app()

async def clear_mongo():
    try:
        client = AsyncIOMotorClient(MONGO_URI)
        db = client[DB_NAME]
        
        corp_count = await db.corporates.count_documents({})
        emp_count = await db.employees.count_documents({})
        print(f"[MongoDB] Found {corp_count} corporates and {emp_count} employees.")
        
        await db.corporates.drop()
        print("[MongoDB] Cleared 'corporates' collection.")
        
        await db.employees.drop()
        print("[MongoDB] Cleared 'employees' collection.")
        
    except Exception as e:
        print(f"[MongoDB] Error: {e}")
    finally:
        client.close()

def clear_firebase():
    try:
        initialize_firebase()
        
        # 1. Clear Firebase Auth Users
        print("[Firebase Auth] Fetching users...")
        page = auth.list_users()
        users_deleted = 0
        while page:
            for user in page.users:
                auth.delete_user(user.uid)
                users_deleted += 1
            page = page.get_next_page()
            
        print(f"[Firebase Auth] Deleted {users_deleted} users.")
        
        # 2. Clear Firestore Collections
        db = firestore.client()
        
        for collection_name in ["corporates", "employees"]:
            print(f"[Firestore] Clearing collection '{collection_name}'...")
            docs = db.collection(collection_name).limit(500).stream()
            deleted = 0
            for doc in docs:
                doc.reference.delete()
                deleted += 1
            print(f"[Firestore] Deleted {deleted} documents from '{collection_name}'.")

    except Exception as e:
        print(f"[Firebase/Firestore] Error: {e}")

async def main():
    print("--- Starting Full Database Cleanup ---")
    clear_firebase()
    await clear_mongo()
    print("--- Cleanup Complete ---")

if __name__ == "__main__":
    reply = input("Are you sure you want to delete ALL users from Firebase and MongoDB? (y/n): ")
    if reply.lower() == 'y':
        asyncio.run(main())
    else:
        print("Cancelled.")
