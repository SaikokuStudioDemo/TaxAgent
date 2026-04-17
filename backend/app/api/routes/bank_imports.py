from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from bson import ObjectId
import logging

from app.api.helpers import (
    serialize_doc as _serialize,
    get_corporate_context,
    CorporateContext,
    parse_oid,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", summary="インポートファイル一覧を取得する")
async def list_import_files(
    ctx: CorporateContext = Depends(get_corporate_context),
):
    cursor = ctx.db["bank_import_files"].find(
        {"corporate_id": ctx.corporate_id}
    ).sort("imported_at", -1)
    docs = await cursor.to_list(length=200)
    return [_serialize(doc) for doc in docs]


@router.delete("/{file_id}", summary="インポートファイルを削除する")
async def delete_import_file(
    file_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    ファイル単位で一括削除する。
    - bank_import_files からファイルレコードを削除
    - 紐付く transactions を全件削除
    - 紐付く matches を論理削除（is_active: false）
    - 紐付く matches の document_ids の reconciliation_status を unreconciled に戻す
    - 紐付く cash_transactions（source: bank_import）を削除
    """
    oid = parse_oid(file_id, "import_file")

    file_doc = await ctx.db["bank_import_files"].find_one({
        "_id": oid,
        "corporate_id": ctx.corporate_id,
    })
    if not file_doc:
        raise HTTPException(status_code=404, detail="Import file not found")

    # 紐付く transactions を取得
    txs = await ctx.db["transactions"].find(
        {"import_file_id": file_id}
    ).to_list(length=10000)
    tx_ids = [str(tx["_id"]) for tx in txs]

    if tx_ids:
        try:
            # 紐付く matches を論理削除し、書類を unreconciled に戻す
            matches = await ctx.db["matches"].find({
                "transaction_ids": {"$in": tx_ids},
                "is_active": {"$ne": False},
            }).to_list(length=10000)

            for match in matches:
                for did in match.get("document_ids", []):
                    for col in ["receipts", "invoices"]:
                        await ctx.db[col].update_one(
                            {"_id": ObjectId(did)},
                            {"$set": {"reconciliation_status": "unreconciled"}}
                        )
                await ctx.db["matches"].update_one(
                    {"_id": match["_id"]},
                    {"$set": {"is_active": False, "inactivated_at": datetime.utcnow()}}
                )

            # 紐付く cash_transactions を削除
            await ctx.db["cash_transactions"].delete_many(
                {"linked_bank_transaction_id": {"$in": tx_ids}}
            )

            # transactions を削除
            await ctx.db["transactions"].delete_many(
                {"import_file_id": file_id}
            )
        except Exception as e:
            logger.error(f"[bank_imports] delete_import_file: 関連データ削除エラー file_id={file_id}: {e}")
            raise HTTPException(status_code=500, detail="関連データの削除中にエラーが発生しました")

    try:
        # ファイルレコードを削除
        await ctx.db["bank_import_files"].delete_one({"_id": oid})
    except Exception as e:
        logger.error(f"[bank_imports] delete_import_file: ファイルレコード削除エラー file_id={file_id}: {e}")
        raise HTTPException(status_code=500, detail="ファイルレコードの削除中にエラーが発生しました")

    return {
        "status": "deleted",
        "file_id": file_id,
        "deleted_transactions": len(tx_ids),
    }
