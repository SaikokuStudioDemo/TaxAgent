from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import Optional
from datetime import datetime

from app.api.helpers import (
    serialize_doc as _serialize,
    get_corporate_context,
    CorporateContext,
    parse_oid,
    extract_fiscal_period,
)
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)
router = APIRouter()


async def detect_and_create_transfers(db, corporate_id: str) -> int:
    """
    同一 corporate_id の unmatched 取引から、同日同額の credit/debit ペアを検出し
    match_type: "transfer" として消込する。
    """
    unmatched = await db["transactions"].find(
        {"corporate_id": corporate_id, "status": "unmatched"}
    ).to_list(length=5000)

    # (transaction_date, amount, source_type) でグループ化
    # source_type を揃えることで bank↔card の誤検知を防ぐ
    groups: dict = defaultdict(lambda: {"credit": [], "debit": []})
    for tx in unmatched:
        key = (tx.get("transaction_date", ""), tx.get("amount", 0), tx.get("source_type", ""))
        tx_type = tx.get("transaction_type", "debit")
        if tx_type in ("credit", "deposit"):
            groups[key]["credit"].append(tx)
        else:
            groups[key]["debit"].append(tx)

    created = 0
    for (date, amount), sides in groups.items():
        credits = sides["credit"]
        debits = sides["debit"]
        pairs = min(len(credits), len(debits))
        for i in range(pairs):
            c_tx = credits[i]
            d_tx = debits[i]
            c_id = str(c_tx["_id"])
            d_id = str(d_tx["_id"])

            # 既存の transfer match がないか確認
            existing = await db["matches"].find_one({
                "corporate_id": corporate_id,
                "match_type": "transfer",
                "transaction_ids": {"$all": [c_id, d_id]},
            })
            if existing:
                continue

            match_doc = {
                "corporate_id": corporate_id,
                "match_type": "transfer",
                "transaction_ids": [d_id, c_id],
                "document_ids": [],
                "total_transaction_amount": amount,
                "total_document_amount": 0,
                "difference": 0,
                "matched_by": "system",
                "account_subject": "普通預金",
                "tax_division": "対象外",
                "fiscal_period": d_tx.get("fiscal_period", ""),
                "matched_at": datetime.utcnow(),
                "is_active": True,
            }
            await db["matches"].insert_one(match_doc)
            from bson import ObjectId
            await db["transactions"].update_many(
                {"_id": {"$in": [c_tx["_id"], d_tx["_id"]]}},
                {"$set": {"status": "transferred"}}
            )
            created += 1

    return created


@router.post("", summary="明細を一括インポートする")
async def import_transactions(
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    Bulk import bank or card transactions from a parsed CSV/statement.
    Payload: { source_type: "bank"|"card", account_name: str, transactions: [...] }
    """
    source_type = payload.get("source_type", "bank")
    account_name = payload.get("account_name", "")
    transactions = payload.get("transactions", [])

    if not transactions:
        raise HTTPException(status_code=400, detail="No transactions provided.")

    # インポートファイルレコードを作成
    import_file_doc = {
        "corporate_id": ctx.corporate_id,
        "source_type": source_type,
        "account_name": account_name,
        "file_name": payload.get("file_name", "unknown.csv"),
        "row_count": len(transactions),
        "status": "completed",
        "imported_at": datetime.utcnow(),
    }
    file_result = await ctx.db["bank_import_files"].insert_one(import_file_doc)
    import_file_id = str(file_result.inserted_id)

    # 既存データの重複チェック用キーセットを取得
    existing_keys = set()
    existing_cursor = ctx.db["transactions"].find(
        {"corporate_id": ctx.corporate_id},
        {"transaction_date": 1, "description": 1, "amount": 1, "source_type": 1},
    )
    async for ex in existing_cursor:
        existing_keys.add((
            ex.get("transaction_date", ""),
            ex.get("description", ""),
            ex.get("amount", 0),
            ex.get("source_type", ""),
        ))

    docs = []
    skipped_count = 0
    for t in transactions:
        date_str = t.get("transaction_date", t.get("date", ""))
        fiscal_period = extract_fiscal_period(date_str)
        dup_key = (date_str, t.get("description", ""), t.get("amount", 0), source_type)
        if dup_key in existing_keys:
            skipped_count += 1
            continue
        existing_keys.add(dup_key)
        docs.append({
            "corporate_id": ctx.corporate_id,
            "source_type": source_type,
            "account_name": account_name,
            "transaction_date": date_str,
            "description": t.get("description", ""),
            "normalized_name": t.get("normalized_name"),
            "amount": t.get("amount", 0),
            "transaction_type": t.get("transaction_type", "debit"),
            "status": "unmatched",
            "fiscal_period": fiscal_period,
            "import_file_id": import_file_id,
            "imported_at": datetime.utcnow(),
        })

    if not docs:
        return {
            "status": "success",
            "imported_count": 0,
            "skipped_count": skipped_count,
            "import_file_id": import_file_id,
        }

    result = await ctx.db["transactions"].insert_many(docs)

    # 自動マッチング処理
    from app.services.auto_expense_rules import match_auto_expense
    for i, doc in enumerate(docs):
        inserted_id = result.inserted_ids[i]
        rule = match_auto_expense(doc)
        if rule is None:
            continue

        match_doc = {
            "corporate_id": ctx.corporate_id,
            "match_type": "auto_expense",
            "transaction_ids": [str(inserted_id)],
            "document_ids": [],
            "total_transaction_amount": doc.get("amount", 0),
            "total_document_amount": 0,
            "difference": 0,
            "matched_by": "system",
            "no_document_reason": rule["name"],
            "auto_rule_key": rule["key"],
            "account_subject": rule["account_subject"],
            "tax_division": rule["tax_division"],
            "fiscal_period": doc.get("fiscal_period", ""),
            "matched_at": datetime.utcnow(),
            "auto_suggested": False,
            "user_action": "system",
            "score": None,
            "score_breakdown": None,
        }
        await ctx.db["matches"].insert_one(match_doc)

        await ctx.db["transactions"].update_one(
            {"_id": inserted_id},
            {"$set": {"status": "matched"}}
        )

    # 現金取引の自動検知
    from app.services.auto_expense_rules import match_cash_transaction
    for i, doc in enumerate(docs):
        inserted_id = result.inserted_ids[i]

        if doc.get("status") == "matched":
            continue

        cash_rule = match_cash_transaction(doc)
        if cash_rule is None:
            continue

        default_account = await ctx.db["cash_accounts"].find_one({
            "corporate_id": ctx.corporate_id
        })
        if default_account is None:
            continue

        cash_doc = {
            "corporate_id": ctx.corporate_id,
            "cash_account_id": str(default_account["_id"]),
            "transaction_date": doc.get("transaction_date", ""),
            "amount": doc.get("amount", 0),
            "direction": cash_rule["cash_direction"],
            "description": doc.get("description", ""),
            "category": cash_rule["category"],
            "fiscal_period": doc.get("fiscal_period", ""),
            "source": "bank_import",
            "linked_bank_transaction_id": str(inserted_id),
            "status": "unmatched",
            "created_at": datetime.utcnow(),
        }
        await ctx.db["cash_transactions"].insert_one(cash_doc)
        await ctx.db["transactions"].update_one(
            {"_id": inserted_id},
            {"$set": {"status": "transferred"}}
        )
        await ctx.db["matches"].insert_one({
            "corporate_id": ctx.corporate_id,
            "match_type": "transfer",
            "transaction_ids": [str(inserted_id)],
            "document_ids": [],
            "total_transaction_amount": doc.get("amount", 0),
            "total_document_amount": 0,
            "difference": 0,
            "matched_by": "system",
            "account_subject": "現金",
            "tax_division": "対象外",
            "fiscal_period": doc.get("fiscal_period", ""),
            "matched_at": datetime.utcnow(),
            "is_active": True,
            "auto_rule_key": cash_rule["key"],
            "no_document_reason": cash_rule["name"],
        })

    # AI Matching Hook: Fetch candidates for fuzzy matching
    try:
        clients_cursor = ctx.db["clients"].find({"corporate_id": ctx.corporate_id})
        clients = await clients_cursor.to_list(length=1000)
        client_names = [c.get("name") for c in clients if c.get("name")]
    except Exception as e:
        logger.error(f"Post-import AI analysis failed: {e}")

    # 口座間振替の自動検知
    try:
        transfer_count = await detect_and_create_transfers(ctx.db, ctx.corporate_id)
        if transfer_count > 0:
            logger.info(f"Auto-detected {transfer_count} transfer pair(s)")
    except Exception as e:
        logger.error(f"Transfer detection failed: {e}")

    return {
        "status": "success",
        "imported_count": len(result.inserted_ids),
        "skipped_count": skipped_count,
        "import_file_id": import_file_id,
    }


@router.post("/extract-pdf", summary="PDFから取引データを抽出する（保存しない）")
async def extract_pdf(
    file: UploadFile = File(...),
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    PDFから取引データを抽出してプレビュー用に返す。DBへの保存は行わない。
    実際の保存は POST /transactions で行う。
    """
    from app.services.bank_pdf_parser import parse_bank_pdf
    from app.services.transaction_classifier import classify_transaction_type

    file_bytes = await file.read()
    extracted = await parse_bank_pdf(file_bytes)

    if not extracted:
        raise HTTPException(
            status_code=422,
            detail="PDFからデータを抽出できませんでした。ファイルを確認してください。"
        )

    transactions = []
    for t in extracted:
        withdrawal = t.get("withdrawal_amount", 0) or 0
        deposit = t.get("deposit_amount", 0) or 0
        amount = t.get("amount") or max(withdrawal, deposit)
        description = t.get("description", "")
        tx_type = classify_transaction_type(withdrawal, deposit, description)
        transactions.append({
            "date": t.get("transaction_date", ""),
            "description": description,
            "amount": amount,
            "withdrawal_amount": withdrawal,
            "deposit_amount": deposit,
            "transaction_type": tx_type,
        })

    return {"transactions": transactions, "count": len(transactions)}


@router.post("/import-pdf", summary="PDF明細をインポートする")
async def import_pdf(
    file: UploadFile = File(...),
    source_type: str = Form(...),
    account_name: str = Form(""),
    file_name: str = Form(""),
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    銀行・カードのPDF明細をアップロードして取引データを抽出・保存する。
    OCR処理はbank_pdf_parser.pyで行う（差し替え可能）。
    """
    from app.services.bank_pdf_parser import parse_bank_pdf
    from app.services.transaction_classifier import classify_transaction_type

    file_bytes = await file.read()

    extracted = await parse_bank_pdf(file_bytes, source_type)
    if not extracted:
        raise HTTPException(
            status_code=422,
            detail="PDFからデータを抽出できませんでした。ファイルを確認してください。"
        )

    import_file_doc = {
        "corporate_id": ctx.corporate_id,
        "source_type": source_type,
        "account_name": account_name or source_type,
        "file_name": file_name or file.filename or "import.pdf",
        "file_type": "pdf",
        "row_count": len(extracted),
        "status": "completed",
        "imported_at": datetime.utcnow(),
    }
    file_result = await ctx.db["bank_import_files"].insert_one(import_file_doc)
    import_file_id = str(file_result.inserted_id)

    # 既存データの重複チェック用キーセットを取得
    existing_keys = set()
    existing_cursor = ctx.db["transactions"].find(
        {"corporate_id": ctx.corporate_id},
        {"transaction_date": 1, "description": 1, "amount": 1, "source_type": 1},
    )
    async for ex in existing_cursor:
        existing_keys.add((
            ex.get("transaction_date", ""),
            ex.get("description", ""),
            ex.get("amount", 0),
            ex.get("source_type", ""),
        ))

    docs = []
    skipped_count = 0
    for t in extracted:
        date_str = t.get("transaction_date", "")
        fiscal_period = extract_fiscal_period(date_str)
        withdrawal = t.get("withdrawal_amount", 0) or 0
        deposit = t.get("deposit_amount", 0) or 0
        amount = t.get("amount") or max(withdrawal, deposit)
        description = t.get("description", "")
        tx_type = classify_transaction_type(withdrawal, deposit, description)

        dup_key = (date_str, description, amount, source_type)
        if dup_key in existing_keys:
            skipped_count += 1
            continue
        existing_keys.add(dup_key)

        docs.append({
            "corporate_id": ctx.corporate_id,
            "source_type": source_type,
            "account_name": account_name,
            "transaction_date": date_str,
            "description": description,
            "withdrawal_amount": withdrawal,
            "deposit_amount": deposit,
            "amount": amount,
            "transaction_type": tx_type,
            "import_file_id": import_file_id,
            "status": "unmatched",
            "fiscal_period": fiscal_period,
            "imported_at": datetime.utcnow(),
        })

    if not docs:
        if skipped_count > 0:
            return {
                "status": "success",
                "imported_count": 0,
                "skipped_count": skipped_count,
                "import_file_id": import_file_id,
            }
        raise HTTPException(status_code=422, detail="有効なデータが抽出されませんでした。")

    result = await ctx.db["transactions"].insert_many(docs)

    from app.services.auto_expense_rules import match_auto_expense, match_cash_transaction

    for i, doc in enumerate(docs):
        inserted_id = result.inserted_ids[i]

        rule = match_auto_expense(doc)
        if rule:
            match_doc = {
                "corporate_id": ctx.corporate_id,
                "match_type": "auto_expense",
                "transaction_ids": [str(inserted_id)],
                "document_ids": [],
                "total_transaction_amount": doc.get("amount", 0),
                "total_document_amount": 0,
                "difference": 0,
                "matched_by": "system",
                "no_document_reason": rule["name"],
                "auto_rule_key": rule["key"],
                "account_subject": rule["account_subject"],
                "tax_division": rule["tax_division"],
                "fiscal_period": doc.get("fiscal_period", ""),
                "matched_at": datetime.utcnow(),
                "is_active": True,
                "auto_suggested": False,
                "user_action": "system",
            }
            await ctx.db["matches"].insert_one(match_doc)
            await ctx.db["transactions"].update_one(
                {"_id": inserted_id}, {"$set": {"status": "matched"}}
            )
            continue

        cash_rule = match_cash_transaction(doc)
        if cash_rule:
            default_account = await ctx.db["cash_accounts"].find_one(
                {"corporate_id": ctx.corporate_id}
            )
            if default_account:
                cash_doc = {
                    "corporate_id": ctx.corporate_id,
                    "cash_account_id": str(default_account["_id"]),
                    "transaction_date": doc.get("transaction_date", ""),
                    "amount": doc.get("amount", 0),
                    "direction": cash_rule["cash_direction"],
                    "description": doc.get("description", ""),
                    "category": cash_rule["category"],
                    "fiscal_period": doc.get("fiscal_period", ""),
                    "source": "bank_import",
                    "linked_bank_transaction_id": str(inserted_id),
                    "status": "unmatched",
                    "created_at": datetime.utcnow(),
                }
                await ctx.db["cash_transactions"].insert_one(cash_doc)
                await ctx.db["transactions"].update_one(
                    {"_id": inserted_id}, {"$set": {"status": "transferred"}}
                )
                await ctx.db["matches"].insert_one({
                    "corporate_id": ctx.corporate_id,
                    "match_type": "transfer",
                    "transaction_ids": [str(inserted_id)],
                    "document_ids": [],
                    "total_transaction_amount": doc.get("amount", 0),
                    "total_document_amount": 0,
                    "difference": 0,
                    "matched_by": "system",
                    "account_subject": "現金",
                    "tax_division": "対象外",
                    "fiscal_period": doc.get("fiscal_period", ""),
                    "matched_at": datetime.utcnow(),
                    "is_active": True,
                    "auto_rule_key": cash_rule["key"],
                    "no_document_reason": cash_rule["name"],
                })

    # 口座間振替の自動検知
    try:
        transfer_count = await detect_and_create_transfers(ctx.db, ctx.corporate_id)
        if transfer_count > 0:
            logger.info(f"Auto-detected {transfer_count} transfer pair(s)")
    except Exception as e:
        logger.error(f"Transfer detection failed: {e}")

    return {
        "status": "success",
        "imported_count": len(result.inserted_ids),
        "skipped_count": skipped_count,
        "import_file_id": import_file_id,
    }


@router.get("", summary="明細一覧を取得する")
async def list_transactions(
    source_type: Optional[str] = None,
    status: Optional[str] = None,
    fiscal_period: Optional[str] = None,
    import_file_id: Optional[str] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    query: dict = {"corporate_id": ctx.corporate_id}
    if source_type:
        query["source_type"] = source_type
    if status:
        query["status"] = status
    if fiscal_period:
        query["fiscal_period"] = fiscal_period
    if import_file_id:
        query["import_file_id"] = import_file_id

    cursor = ctx.db["transactions"].find(query).sort("transaction_date", -1)
    docs = await cursor.to_list(length=1000)
    return [_serialize(doc) for doc in docs]


@router.patch("/{transaction_id}", summary="明細を更新する")
async def update_transaction(
    transaction_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(transaction_id, "transaction")

    doc = await ctx.db["transactions"].find_one({
        "_id": oid,
        "corporate_id": ctx.corporate_id,
    })
    if doc is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if doc.get("status") == "matched":
        raise HTTPException(status_code=403, detail="消込済みの明細は編集できません")

    allowed = {"transaction_date", "description", "amount"}
    update_fields = {k: v for k, v in payload.items() if k in allowed}
    if not update_fields:
        raise HTTPException(status_code=400, detail="更新可能なフィールドがありません")

    if "transaction_date" in update_fields:
        date_str = update_fields["transaction_date"]
        update_fields["fiscal_period"] = date_str[:7] if date_str else doc.get("fiscal_period", "")

    await ctx.db["transactions"].update_one(
        {"_id": oid},
        {"$set": update_fields},
    )
    updated = await ctx.db["transactions"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{transaction_id}", summary="明細を削除する")
async def delete_transaction(
    transaction_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(transaction_id, "transaction")

    result = await ctx.db["transactions"].delete_one({
        "_id": oid,
        "corporate_id": ctx.corporate_id,
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"status": "deleted", "transaction_id": transaction_id}
