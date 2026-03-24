"""
Shared dependency helpers for resolving corporate context from Firebase UID.
"""
import logging
from fastapi import HTTPException
from app.db.mongodb import get_database

logger = logging.getLogger(__name__)

async def resolve_corporate_id(firebase_uid: str) -> tuple[str, str]:
    """
    Given a Firebase UID, return (corporate_id, user_id).
    Checks if UID belongs to a corporate admin or an employee.
    Raises 403 if no corporate context can be determined.
    """
    db = get_database()

    # Check corporate admin first
    corporate = await db["corporates"].find_one({"firebase_uid": firebase_uid})
    if corporate:
        cid = str(corporate["_id"])
        return cid, cid  # admin acts as themselves

    # Check employees
    employee = await db["employees"].find_one({"firebase_uid": firebase_uid})
    if employee:
        user_id = str(employee["_id"])
        parent_uid = employee.get("parent_corporate_firebase_uid") or employee.get("parent_corporate_id")
        parent_corp = await db["corporates"].find_one({"firebase_uid": parent_uid})
        if parent_corp:
            return str(parent_corp["_id"]), user_id

    raise HTTPException(
        status_code=403,
        detail="Corporate context could not be determined. Access denied.",
    )
