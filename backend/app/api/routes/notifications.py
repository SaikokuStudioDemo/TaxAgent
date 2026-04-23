"""
通知 API
ログイン中の法人への通知一覧を返す。
"""
import logging

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", summary="通知一覧を取得する")
async def list_notifications(current_user: dict = Depends(get_current_user)):
    """Return all notifications for this corporate (most recent first)."""
    from app.api.helpers import resolve_corporate_id
    from app.db.mongodb import get_database

    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    cursor = db["notifications"].find({"corporate_id": corporate_id}).sort("sent_at", -1)
    docs = await cursor.to_list(length=200)
    for doc in docs:
        doc["id"] = str(doc.pop("_id"))
    return docs
