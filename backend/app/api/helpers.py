"""
Shared dependency helpers for resolving corporate context from Firebase UID.
"""
import logging
from dataclasses import dataclass
from bson import ObjectId
from fastapi import HTTPException, Depends
from typing import Set, Optional, List
from app.db.mongodb import get_database
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)


def serialize_doc(doc: dict) -> dict:
    """Convert ObjectId _id to string id, and stringify any remaining ObjectIds."""
    doc["id"] = str(doc.pop("_id"))
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            doc[k] = str(v)
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
        corporate_id = employee.get("corporate_id")
        if corporate_id:
            return corporate_id, user_id

    raise HTTPException(
        status_code=403,
        detail="Corporate context could not be determined. Access denied.",
    )


FULL_ACCESS_ROLES = {"admin", "accounting", "manager"}


@dataclass
class CorporateContext:
    corporate_id: str
    user_id: str
    firebase_uid: str
    db: object  # AsyncIOMotorDatabase
    role: str = "staff"
    department_id: Optional[str] = None
    project_ids: List[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.project_ids is None:
            self.project_ids = []


async def get_corporate_context(
    current_user: dict = Depends(get_current_user),
) -> CorporateContext:
    """FastAPI dependency: resolves corporate context from the authenticated user."""
    firebase_uid = current_user.get("uid")
    corporate_id, user_id = await resolve_corporate_id(firebase_uid)
    db = get_database()

    role = "staff"
    department_id = None
    project_ids: List[str] = []

    # Corporate admin: full access, no department/project filter
    corporate = await db["corporates"].find_one({"firebase_uid": firebase_uid})
    if corporate:
        role = "admin"
    else:
        employee = await db["employees"].find_one({"firebase_uid": firebase_uid})
        if employee:
            role = employee.get("role", "staff")
            department_id = employee.get("department_id")
            # Collect project IDs this employee belongs to
            proj_cursor = db["project_members"].find(
                {"employee_id": user_id},
                {"project_id": 1},
            )
            proj_docs = await proj_cursor.to_list(length=200)
            project_ids = [p["project_id"] for p in proj_docs if p.get("project_id")]

    return CorporateContext(
        corporate_id=corporate_id,
        user_id=user_id,
        firebase_uid=firebase_uid,
        db=db,
        role=role,
        department_id=department_id,
        project_ids=project_ids,
    )


def build_scope_filter(ctx: CorporateContext) -> dict:
    """Return a MongoDB filter dict that restricts documents to the user's scope.

    Full-access roles (admin, accounting, manager) see everything → returns {}.
    Others see documents that match at least one of:
      - department_id matches the user's department
      - project_id is in the user's project list
      - submitted_by equals the user's own user_id
    """
    if ctx.role in FULL_ACCESS_ROLES:
        return {}

    or_clauses = [{"submitted_by": ctx.user_id}]
    if ctx.department_id:
        or_clauses.append({"department_id": ctx.department_id})
    if ctx.project_ids:
        or_clauses.append({"project_id": {"$in": ctx.project_ids}})

    return {"$or": or_clauses}


def parse_oid(doc_id: str, label: str = "document") -> ObjectId:
    """Parse a string to ObjectId, raising HTTP 400 on failure."""
    try:
        return ObjectId(doc_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid {label} ID")


def build_list_query(corporate_id: str, **filters) -> dict:
    """一覧取得用の MongoDB クエリを組み立てる共通ヘルパー。
    値が None のフィールドは自動でスキップされる。"""
    query: dict = {"corporate_id": corporate_id}
    for key, value in filters.items():
        if value is not None:
            query[key] = value
    return query


async def enrich_with_approval_history(
    db,
    doc: dict,
    document_id: str,
    document_type,
) -> dict:
    """audit_logs から承認履歴を取得してドキュメントに付加する共通ヘルパー。
    document_type は文字列または文字列のリストを受け取る。"""
    dt_filter = {"$in": list(document_type)} if not isinstance(document_type, str) else document_type
    events_cursor = db["audit_logs"].find(
        {"document_id": document_id, "document_type": dt_filter}
    ).sort("timestamp", 1)
    events = await events_cursor.to_list(length=100)
    doc["approval_history"] = [serialize_doc(e) for e in events]
    return doc


async def build_name_map(db, user_ids: Set[str]) -> dict:
    """user_id の集合から {user_id: name} マップを一括取得する。
    employees → corporates の順で検索し、見つからなければ '不明' を使う。"""
    if not user_ids:
        return {}
    oids = []
    for uid in user_ids:
        try:
            oids.append(ObjectId(uid))
        except Exception:
            pass
    if not oids:
        return {}

    name_map: dict = {}
    employees = await db["employees"].find({"_id": {"$in": oids}}).to_list(length=500)
    for e in employees:
        name_map[str(e["_id"])] = e.get("name", "不明")

    unresolved_oids = [o for o in oids if str(o) not in name_map]
    if unresolved_oids:
        corporates = await db["corporates"].find({"_id": {"$in": unresolved_oids}}).to_list(length=100)
        for c in corporates:
            name_map[str(c["_id"])] = c.get("name", "不明")

    return name_map


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
