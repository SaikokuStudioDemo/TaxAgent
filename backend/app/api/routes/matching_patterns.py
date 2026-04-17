"""
matching_patterns ルーター

取引先ごとのマッチングパターン（銀行振込摘要との照合文字列）を管理する。
"""
from fastapi import APIRouter, HTTPException
from fastapi.params import Depends
from datetime import datetime
from bson import ObjectId
from typing import Optional

from app.api.helpers import (
    serialize_doc as _serialize,
    get_corporate_context,
    CorporateContext,
    parse_oid,
)
from app.models.master import MatchingPatternCreate

router = APIRouter()



@router.get("", summary="マッチングパターン一覧を取得する")
async def list_matching_patterns(
    client_id: Optional[str] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    corporate_id でスコープされたパターン一覧を返す。
    client_id を指定すると特定取引先のパターンのみ返す。
    """
    query: dict = {"corporate_id": ctx.corporate_id}
    if client_id:
        query["client_id"] = client_id

    docs = await ctx.db["matching_patterns"].find(query).sort("created_at", -1).to_list(length=5000)
    return [_serialize(d) for d in docs]


@router.post("", summary="マッチングパターンを手動追加する")
async def create_matching_pattern(
    payload: MatchingPatternCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    # 重複チェック
    existing = await ctx.db["matching_patterns"].find_one({
        "corporate_id": ctx.corporate_id,
        "client_id": payload.client_id,
        "pattern": payload.pattern,
    })
    if existing:
        raise HTTPException(status_code=409, detail="同じパターンが既に登録されています")

    doc = {
        "corporate_id": ctx.corporate_id,
        "client_id": payload.client_id,
        "pattern": payload.pattern,
        "source": payload.source,
        "confidence": payload.confidence,
        "created_at": datetime.utcnow(),
        "used_count": 0,
    }
    result = await ctx.db["matching_patterns"].insert_one(doc)
    created = await ctx.db["matching_patterns"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.delete("/{pattern_id}", summary="マッチングパターンを削除する")
async def delete_matching_pattern(
    pattern_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(pattern_id, "matching_pattern")
    result = await ctx.db["matching_patterns"].delete_one({
        "_id": oid,
        "corporate_id": ctx.corporate_id,
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="MatchingPattern not found")
    return {"status": "deleted", "id": pattern_id}
