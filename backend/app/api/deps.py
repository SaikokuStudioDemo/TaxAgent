import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import credentials, auth
from app.core.config import settings

# Initialize Firebase Admin
try:
    # Check if the file exists before trying to load it
    if os.path.exists(settings.FIREBASE_CREDENTIALS_PATH):
        cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred, {
            'storageBucket': settings.FIREBASE_STORAGE_BUCKET
        })
        print("Firebase Admin initialized successfully.")
    else:
        print(f"WARNING: Firebase credentials file not found at {settings.FIREBASE_CREDENTIALS_PATH}")
        print("Falling back to MOCK authentication mode.")
except Exception as e:
    print(f"Error initializing Firebase: {e}")

security = HTTPBearer()

async def get_current_user(cred: HTTPAuthorizationCredentials = Depends(security)):
    """
    Verify the Firebase token or accept a mock token if Firebase is not configured.
    """
    token = cred.credentials
    
    # -------------------------------------------------------------
    # MOCK MODE (For fast development without actual Firebase Auth)
    # Only allow mock tokens in non-production environments
    # -------------------------------------------------------------
    if os.environ.get("ENVIRONMENT", "development") != "production":
        if token == "test-token":
            return {"uid": "seed_corp_a_uid", "email": "admin@example.com"}
        if token == "tax-test-token":
            return {"uid": "tax_firm_uid", "email": "admin@tax-firm.example.com"}
        
    # -------------------------------------------------------------
    # PRODUCTION MODE (Requires active Firebase creds)
    # -------------------------------------------------------------
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def verify_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """ADMIN_UIDS に含まれない UID は 403 を返す。"""
    uid = current_user.get("uid", "")
    if uid not in settings.ADMIN_UIDS:
        raise HTTPException(status_code=403, detail="Admin権限がありません。")
    return current_user
