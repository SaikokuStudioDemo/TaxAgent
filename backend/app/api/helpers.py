"""
Shared dependency helpers for resolving corporate context from Firebase UID.
"""
import logging
from dataclasses import dataclass
from bson import ObjectId
from fastapi import HTTPException, Depends
from app.db.mongodb import get_database
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)


def serialize_doc(doc: dict) -> dict:
    """Convert ObjectId _id to string id for JSON serialization."""
    doc["id"] = str(doc.pop("_id"))
    return doc


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


@dataclass
class CorporateContext:
    corporate_id: str
    user_id: str
    firebase_uid: str
    db: object  # AsyncIOMotorDatabase


async def get_corporate_context(
    current_user: dict = Depends(get_current_user),
) -> CorporateContext:
    """FastAPI dependency: resolves corporate context from the authenticated user."""
    firebase_uid = current_user.get("uid")
    corporate_id, user_id = await resolve_corporate_id(firebase_uid)
    db = get_database()
    return CorporateContext(
        corporate_id=corporate_id,
        user_id=user_id,
        firebase_uid=firebase_uid,
        db=db,
    )


def parse_oid(doc_id: str, label: str = "document") -> ObjectId:
    """Parse a string to ObjectId, raising HTTP 400 on failure."""
    try:
        return ObjectId(doc_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid {label} ID")


async def get_doc_or_404(
    db,
    collection: str,
    doc_id: str,
    corporate_id: str,
    label: str = "document",
) -> dict:
    """Fetch a document by ID scoped to corporate_id, raising 400/404 as needed."""
    oid = parse_oid(doc_id, label)
    doc = await db[collection].find_one({"_id": oid, "corporate_id": corporate_id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"{label.capitalize()} not found")
    return doc
