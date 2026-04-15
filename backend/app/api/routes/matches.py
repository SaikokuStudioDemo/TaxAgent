from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime
from bson import ObjectId

from app.api.helpers import (
    serialize_doc as _serialize,
    get_corporate_context,
    CorporateContext,
    parse_oid,
    get_doc_or_404,
)
from app.services.matching_score_service import calculate_match_score
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


async def _write_match_events(db, corporate_id: str, document_ids: list, action: str, user_id: str = "system", comment=None):
    """document_ids に紐づく audit_logs（matched / unmatched）を書き込む共通ヘルパー。"""
    now = datetime.utcnow()
    for did in document_ids:
        # receipts / invoices どちらか判断
        doc_type = "receipt"
        try:
            rec = await db["receipts"].find_one({"_id": ObjectId(did)})
            if not rec:
                doc_type = "invoice"
        except Exception:
            doc_type = "invoice"
        await db["audit_logs"].insert_one({
            "corporate_id": corporate_id,
            "document_type": doc_type,
            "document_id": did,
            "step": 99,
            "action": action,
            "approver_id": user_id,
            "comment": comment,
            "timestamp": now,
        })


@router.post("", summary="マッチング（消込）を作成する")
async def create_match(
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    Create a match linking transactions to receipts or invoices.

    Auto-matching rules:
      - If |difference| < AUTO_MATCH_THRESHOLD (¥1,000):
          差額を「支払手数料」として自動処理
      - If |difference| >= ¥1,000: requires manual difference_treatment in payload

    Payload:
      match_type: "receipt" | "invoice"
      transaction_ids: list of transaction IDs
      document_ids: list of receipt/invoice IDs
      difference_treatment: str (optional, overrides auto-detection)
      matched_by: "manual" | "ai"
      fiscal_period: str (YYYY-MM)
      auto_suggested: bool (候補から実行したか)
    """
    AUTO_MATCH_THRESHOLD = 1000

    transaction_ids = payload.get("transaction_ids", [])
    document_ids = payload.get("document_ids", [])
    match_type = payload.get("match_type", "receipt")
    fiscal_period = payload.get("fiscal_period", datetime.utcnow().strftime("%Y-%m"))

    if match_type not in ("receipt", "invoice", "transfer", "reconciliation"):
        raise HTTPException(status_code=400, detail=f"無効な match_type: {match_type}")

    # ── transfer タイプの特別処理 ─────────────────────────
    if match_type == "transfer":
        if len(transaction_ids) != 2:
            raise HTTPException(status_code=400, detail="transfer タイプは transaction_ids を2件指定してください")

        t_total = 0
        first_tx = None
        for tid in transaction_ids:
            try:
                t = await ctx.db["transactions"].find_one({"_id": ObjectId(tid)})
                if t:
                    if t_total == 0:
                        t_total = t.get("amount", 0)
                    if first_tx is None:
                        first_tx = t
            except Exception:
                pass

        if not fiscal_period and first_tx:
            fiscal_period = first_tx.get("fiscal_period", datetime.utcnow().strftime("%Y-%m"))

        match_doc = {
            "corporate_id": ctx.corporate_id,
            "match_type": "transfer",
            "transaction_ids": transaction_ids,
            "document_ids": [],
            "total_transaction_amount": t_total,
            "total_document_amount": 0,
            "difference": 0,
            "matched_by": payload.get("matched_by", "manual"),
            "account_subject": "普通預金",
            "tax_division": "対象外",
            "fiscal_period": fiscal_period,
            "matched_at": datetime.utcnow(),
            "is_active": True,
            "auto_suggested": False,
            "user_action": "confirmed",
            "confirmed_at": datetime.utcnow(),
        }
        result = await ctx.db["matches"].insert_one(match_doc)

        for tid in transaction_ids:
            try:
                await ctx.db["transactions"].update_one(
                    {"_id": ObjectId(tid)}, {"$set": {"status": "transferred"}}
                )
            except Exception:
                pass

        created = await ctx.db["matches"].find_one({"_id": result.inserted_id})
        return _serialize(created)

    # ── reconciliation タイプの特別処理 ────────────────────────
    if match_type == "reconciliation":
        t_total = 0
        first_tx = None
        for tid in transaction_ids:
            try:
                t = await ctx.db["transactions"].find_one({"_id": ObjectId(tid)})
                if t:
                    t_total += t.get("amount", 0)
                    if first_tx is None:
                        first_tx = t
            except Exception:
                pass

        if not fiscal_period and first_tx:
            fiscal_period = first_tx.get("fiscal_period", datetime.utcnow().strftime("%Y-%m"))

        match_doc = {
            "corporate_id": ctx.corporate_id,
            "match_type": "reconciliation",
            "transaction_ids": transaction_ids,
            "document_ids": document_ids,
            "total_transaction_amount": t_total,
            "total_document_amount": 0,
            "difference": 0,
            "account_subject": payload.get("account_subject", ""),
            "memo": payload.get("memo", ""),
            "matched_by": payload.get("matched_by", "manual"),
            "fiscal_period": fiscal_period,
            "matched_at": datetime.utcnow(),
            "is_active": True,
            "user_action": "confirmed",
            "confirmed_at": datetime.utcnow(),
        }
        result = await ctx.db["matches"].insert_one(match_doc)

        for tid in transaction_ids:
            try:
                await ctx.db["transactions"].update_one(
                    {"_id": ObjectId(tid)}, {"$set": {"status": "matched"}}
                )
            except Exception:
                pass

        for did in document_ids:
            try:
                # 領収書・請求書どちらか判断して reconciliation_status を更新
                for col in ("receipts", "invoices"):
                    r = await ctx.db[col].update_one(
                        {"_id": ObjectId(did)},
                        {"$set": {"reconciliation_status": "reconciled"}},
                    )
                    if r.matched_count:
                        break
            except Exception:
                pass

        # transaction-level イベントは書類の有無にかかわらず常に記録
        account_subject = payload.get("account_subject", "")
        memo = payload.get("memo", "")
        now = datetime.utcnow()
        for tid in transaction_ids:
            await ctx.db["audit_logs"].insert_one({
                "corporate_id": ctx.corporate_id,
                "entity_type": "transaction",
                "transaction_id": tid,
                "action": "matched",
                "approver_id": ctx.user_id,
                "account_subject": account_subject,
                "comment": memo or f"照合確定（{account_subject}）",
                "timestamp": now,
            })

        # document-level イベント（書類が紐付いている場合）
        if document_ids:
            await _write_match_events(ctx.db, ctx.corporate_id, document_ids, "matched",
                                      ctx.user_id, f"照合確定（{account_subject}）")

        created = await ctx.db["matches"].find_one({"_id": result.inserted_id})
        return _serialize(created)

    collection = "receipts" if match_type == "receipt" else "invoices"

    # ── 金額集計 ───────────────────────────────────────
    t_total = 0
    first_tx = None
    for tid in transaction_ids:
        try:
            t = await ctx.db["transactions"].find_one({"_id": ObjectId(tid)})
            if t:
                t_total += t.get("amount", 0)
                if first_tx is None:
                    first_tx = t
        except Exception:
            pass
    # fallback: bank_transactions (legacy)
    if t_total == 0:
        for tid in transaction_ids:
            try:
                t = await ctx.db["bank_transactions"].find_one({"_id": ObjectId(tid)})
                if t:
                    t_total += t.get("amount", 0)
                    if first_tx is None:
                        first_tx = t
            except Exception:
                pass

    d_total = 0
    first_doc = None
    for did in document_ids:
        try:
            d = await ctx.db[collection].find_one({"_id": ObjectId(did)})
            if d:
                d_total += d.get("amount" if match_type == "receipt" else "total_amount", 0)
                if first_doc is None:
                    first_doc = d
        except Exception:
            pass

    difference = t_total - d_total
    abs_diff = abs(difference)

    # ── 差額処理の決定 ─────────────────────────────────
    auto_resolved = False
    difference_treatment = payload.get("difference_treatment")
    journal_entries = payload.get("journal_entries", [])

    if abs_diff == 0:
        difference_treatment = None
        auto_resolved = True
    elif abs_diff < AUTO_MATCH_THRESHOLD:
        auto_resolved = True
        if difference_treatment is None:
            difference_treatment = "支払手数料"
        if abs_diff > 0 and not journal_entries:
            journal_entries = [{
                "debit_account": difference_treatment if difference > 0 else "売掛金",
                "credit_account": "普通預金" if difference > 0 else difference_treatment,
                "amount": abs_diff,
                "description": f"差額自動処理（{difference_treatment}）¥{abs_diff:,}",
                "auto_generated": True,
            }]
    else:
        if not difference_treatment:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"差額が¥{abs_diff:,}あります（閾値¥{AUTO_MATCH_THRESHOLD:,}超）。"
                    f"差額の処理方法（difference_treatment）を指定してください。"
                ),
            )

    # ── スコア計算 ─────────────────────────────────────
    score_result: dict = {}
    if first_tx and first_doc:
        score_result = calculate_match_score(first_tx, first_doc, match_type)

    receipt_ids = payload.get("receipt_ids", [])

    match_doc = {
        "corporate_id": ctx.corporate_id,
        "match_type": match_type,
        "transaction_ids": transaction_ids,
        "document_ids": document_ids,
        "receipt_ids": receipt_ids,
        "total_transaction_amount": t_total,
        "total_document_amount": d_total,
        "difference": abs_diff,
        "difference_direction": "bank_over" if difference > 0 else ("doc_over" if difference < 0 else "equal"),
        "difference_treatment": difference_treatment,
        "auto_resolved": auto_resolved,
        "matched_by": payload.get("matched_by", "manual"),
        "journal_entries": journal_entries,
        "fiscal_period": fiscal_period,
        "matched_at": datetime.utcnow(),
        "score": score_result.get("score"),
        "score_breakdown": score_result.get("score_breakdown"),
        "auto_suggested": payload.get("auto_suggested", False),
        "user_action": "confirmed",
        "confirmed_at": datetime.utcnow(),
    }

    result = await ctx.db["matches"].insert_one(match_doc)

    # ── ステータス更新 ─────────────────────────────────
    for tid in transaction_ids:
        try:
            await ctx.db["transactions"].update_one(
                {"_id": ObjectId(tid)}, {"$set": {"status": "matched"}}
            )
        except Exception:
            pass
        try:
            await ctx.db["bank_transactions"].update_one(
                {"_id": ObjectId(tid)}, {"$set": {"status": "matched"}}
            )
        except Exception:
            pass

    for did in document_ids:
        try:
            await ctx.db[collection].update_one(
                {"_id": ObjectId(did)}, {"$set": {"reconciliation_status": "reconciled"}}
            )
        except Exception:
            pass

    for rid in receipt_ids:
        try:
            await ctx.db["receipts"].update_one(
                {"_id": ObjectId(rid)}, {"$set": {"reconciliation_status": "reconciled"}}
            )
        except Exception:
            pass

    # ── 消込イベント記録 ───────────────────────────────────────
    all_doc_ids = list(document_ids) + list(payload.get("receipt_ids", []))
    if all_doc_ids:
        await _write_match_events(ctx.db, ctx.corporate_id, all_doc_ids, "matched", ctx.user_id)

    # ── invoice消込時に matching_patterns を自動登録 ───────────
    if match_type == "invoice":
        try:
            # 摘要テキストを収集
            descriptions = []
            for tid in transaction_ids:
                try:
                    t = await ctx.db["transactions"].find_one({"_id": ObjectId(tid)})
                    if t and t.get("description"):
                        descriptions.append(t["description"])
                except Exception:
                    pass

            for did in document_ids:
                try:
                    inv = await ctx.db["invoices"].find_one({"_id": ObjectId(did)})
                    if not inv:
                        continue
                    # vendor_id（received）または client_id（issued）を取得
                    client_ref_id = inv.get("vendor_id") or inv.get("client_id")
                    if not client_ref_id:
                        # IDがなければ名前でフォールバック検索
                        search_name = inv.get("vendor_name") or inv.get("client_name")
                        if search_name:
                            cl = await ctx.db["clients"].find_one({
                                "corporate_id": ctx.corporate_id,
                                "name": search_name,
                            })
                            if cl:
                                client_ref_id = str(cl["_id"])
                    if not client_ref_id:
                        continue
                    client_id_str = str(client_ref_id)
                    for desc in descriptions:
                        if not desc:
                            continue
                        existing = await ctx.db["matching_patterns"].find_one({
                            "corporate_id": ctx.corporate_id,
                            "client_id": client_id_str,
                            "pattern": desc,
                        })
                        if not existing:
                            await ctx.db["matching_patterns"].insert_one({
                                "corporate_id": ctx.corporate_id,
                                "client_id": client_id_str,
                                "pattern": desc,
                                "source": "manual_match",
                                "confidence": 1.0,
                                "created_at": datetime.utcnow(),
                                "used_count": 0,
                            })
                except Exception:
                    pass
        except Exception:
            pass  # matching_patterns 登録失敗はマッチング結果に影響させない

    created = await ctx.db["matches"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.get("/candidates", summary="消込候補ペアを取得する")
async def get_candidates(
    match_type: str = "receipt",
    fiscal_period: Optional[str] = None,
    invoice_type: Optional[str] = None,  # "issued" | "received"
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    未消込の取引明細と未消込ドキュメントを全件取得し、
    スコアリングして is_candidate=True のペアのみ返す。

    invoice_type:
        "issued"   → 入金系取引（credit / deposit）のみ対象
        "received" → 出金系取引（debit / withdrawal）のみ対象

    Returns:
        [{ transaction, document, score, score_breakdown }, ...]
        score の降順でソート
    """
    # 未消込 transactions を取得
    tx_query: dict = {
        "corporate_id": ctx.corporate_id,
        "status": {"$nin": ["matched", "transferred"]},
    }
    if fiscal_period:
        tx_query["fiscal_period"] = fiscal_period

    # invoice_type に応じて transaction_type を絞り込む
    if match_type == "invoice":
        if invoice_type == "received":
            tx_query["transaction_type"] = {"$in": ["debit", "withdrawal"]}
        elif invoice_type == "issued":
            tx_query["transaction_type"] = {"$in": ["credit", "deposit"]}

    txs = await ctx.db["transactions"].find(tx_query).to_list(length=1000)

    # auto_expense で処理済みの transaction_ids を除外
    auto_expense_matches = await ctx.db["matches"].find(
        {
            "corporate_id": ctx.corporate_id,
            "match_type": "auto_expense",
            "is_active": {"$ne": False},
        }
    ).to_list(length=1000)

    auto_expense_tx_ids = set()
    for m in auto_expense_matches:
        for tid in m.get("transaction_ids", []):
            auto_expense_tx_ids.add(tid)

    if auto_expense_tx_ids:
        txs = [t for t in txs if str(t["_id"]) not in auto_expense_tx_ids]

    # 未消込 documents を取得
    doc_collection = "receipts" if match_type == "receipt" else "invoices"
    doc_query: dict = {
        "corporate_id": ctx.corporate_id,
        "reconciliation_status": {"$in": ["unreconciled", None, ""]},
        "is_deleted": {"$ne": True},
    }
    if fiscal_period:
        doc_query["fiscal_period"] = fiscal_period

    docs = await ctx.db[doc_collection].find(doc_query).to_list(length=1000)

    if not txs or not docs:
        return []

    # ── matching_patterns コレクションからパターンマップを構築（invoice のみ）──
    # client_id/vendor_id → [pattern_str, ...]
    client_patterns_map: dict = {}
    if match_type == "invoice":
        entity_ids = set()
        for doc in docs:
            if doc.get("document_type") == "received":
                if doc.get("vendor_id"):
                    entity_ids.add(str(doc["vendor_id"]))
            else:
                if doc.get("client_id"):
                    entity_ids.add(str(doc["client_id"]))
        if entity_ids:
            patterns_docs = await ctx.db["matching_patterns"].find(
                {
                    "corporate_id": ctx.corporate_id,
                    "client_id": {"$in": list(entity_ids)},
                }
            ).to_list(length=5000)
            for p in patterns_docs:
                cid = p["client_id"]
                if p.get("pattern"):
                    client_patterns_map.setdefault(cid, []).append(p["pattern"])

    # スコアリング（全組み合わせ）
    candidates = []
    for tx in txs:
        for doc in docs:
            bank_display_patterns = None
            if match_type == "invoice":
                if doc.get("document_type") == "received":
                    # received請求書: vendor_id の bank_display_names を使用
                    vendor_id = str(doc.get("vendor_id", ""))
                    bank_display_patterns = client_patterns_map.get(vendor_id)
                else:
                    # issued請求書: client_id の bank_display_names を使用
                    client_id = str(doc.get("client_id", ""))
                    bank_display_patterns = client_patterns_map.get(client_id)
            result = calculate_match_score(tx, doc, match_type, bank_display_patterns)
            if result["is_candidate"]:
                candidates.append({
                    "transaction": _serialize(dict(tx)),
                    "document": _serialize(dict(doc)),
                    "score": result["score"],
                    "score_breakdown": result["score_breakdown"],
                })

    # スコア降順でソート
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


@router.get("/candidates/by-applicant", summary="申請者別の消込候補を取得する")
async def get_candidates_by_applicant(
    fiscal_period: Optional[str] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    クレジットカード / 振込出金の取引明細と、申請者の領収書をAIファジーマッチングで紐付け候補を返す。

    Returns:
        [{ transaction, receipts: [{receipt, employee}], best_employee }]
    """
    from app.services.ai_service import AIService

    # 未消込のクレジット / 出金系 transactions
    tx_query: dict = {
        "corporate_id": ctx.corporate_id,
        "status": {"$nin": ["matched", "transferred"]},
        "transaction_type": {"$in": ["debit", "withdrawal", "credit_payment"]},
    }
    if fiscal_period:
        tx_query["fiscal_period"] = fiscal_period

    txs = await ctx.db["transactions"].find(tx_query).to_list(length=500)

    # 従業員一覧（bank_display_name があるもの優先）
    employees = await ctx.db["employees"].find(
        {"corporate_id": ctx.corporate_id, "status": {"$ne": "inactive"}}
    ).to_list(length=500)

    emp_map = {str(e["_id"]): e for e in employees}

    # 未消込の領収書（申請者IDあり）
    receipt_query: dict = {
        "corporate_id": ctx.corporate_id,
        "reconciliation_status": {"$in": ["unreconciled", None, ""]},
        "is_deleted": {"$ne": True},
        "applicant_id": {"$exists": True, "$ne": None},
    }
    if fiscal_period:
        receipt_query["fiscal_period"] = fiscal_period

    receipts = await ctx.db["receipts"].find(receipt_query).to_list(length=1000)

    if not txs or not receipts:
        return []

    # 申請者IDごとに領収書をグループ化
    receipts_by_applicant: dict = {}
    for r in receipts:
        aid = str(r.get("applicant_id", ""))
        if aid:
            receipts_by_applicant.setdefault(aid, []).append(r)

    # 従業員名リスト（AIマッチング用）
    emp_names = []
    for e in employees:
        display = e.get("bank_display_name") or e.get("name", "")
        if display:
            emp_names.append(display)
    emp_name_to_id = {}
    for e in employees:
        display = e.get("bank_display_name") or e.get("name", "")
        if display:
            emp_name_to_id[display] = str(e["_id"])

    results = []
    for tx in txs:
        desc = tx.get("description", "")
        if not desc or not emp_names:
            continue

        ai_result = await AIService.fuzzy_match_names(desc, emp_names)
        if not ai_result or not ai_result.get("match") or ai_result.get("confidence", 0) < 0.5:
            continue

        matched_name = ai_result["match"]
        emp_id = emp_name_to_id.get(matched_name)
        if not emp_id:
            continue

        emp = emp_map.get(emp_id)
        applicant_receipts = receipts_by_applicant.get(emp_id, [])

        results.append({
            "transaction": _serialize(dict(tx)),
            "employee": _serialize(dict(emp)) if emp else None,
            "receipts": [_serialize(dict(r)) for r in applicant_receipts],
            "confidence": ai_result.get("confidence"),
            "match_reason": ai_result.get("reason"),
        })

    return results


@router.post("/ai-suggest-bank-names", summary="AIで取引先の銀行表示名を自動提案・登録する")
async def ai_suggest_bank_names(
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    未消込の請求書と取引明細を分析し、AIが取引先マスターの bank_display_names を自動提案・登録する。

    フロー:
    1. 未消込の請求書（client_id あり）から、関係する取引先IDを収集
    2. 未消込の取引明細の摘要（description）をユニーク化して収集
    3. 取引先ごとに1回だけ AIService.fuzzy_match_names(bank_desc=摘要, candidates=全取引先名) を呼ぶ
       → AIコール数 = ユニーク摘要数（通常 数件〜数十件）
    4. confidence >= threshold なら bank_display_names に追加
    5. 結果サマリーを返す

    Payload:
      fiscal_period: str (optional)
      confidence_threshold: float (default 0.85)
      dry_run: bool (default false) - 登録せずに結果のみ返す
    """
    from app.services.ai_service import AIService

    fiscal_period = payload.get("fiscal_period")
    threshold = float(payload.get("confidence_threshold", 0.85))
    dry_run = bool(payload.get("dry_run", False))

    TRANSFER_KEYWORDS = ("振込", "入金")
    AMOUNT_TOLERANCE = 1000
    added_results = []
    already_added: set = set()  # (client_id, pattern) の重複防止
    total_ai_calls = 0

    # 未消込 transactions を取得
    tx_query: dict = {
        "corporate_id": ctx.corporate_id,
        "status": {"$nin": ["matched", "transferred"]},
    }
    if fiscal_period:
        tx_query["fiscal_period"] = fiscal_period
    txs = await ctx.db["transactions"].find(tx_query).to_list(length=1000)

    if not txs:
        return {"status": "no_transactions", "added": [], "dry_run": dry_run}

    async def _process_group(
        invoices_group: list,
        id_field: str,        # "client_id" | "vendor_id"
        tx_type_filter: Optional[str],  # "credit" | "debit" | None
    ) -> None:
        """請求書グループとトランザクションを照合してAIでbank_display_namesを提案・登録する。"""
        nonlocal total_ai_calls

        if not invoices_group:
            return

        # 対象client/vendorのIDを収集
        entity_ids = list({str(inv.get(id_field)) for inv in invoices_group if inv.get(id_field)})
        entities = await ctx.db["clients"].find(
            {"_id": {"$in": [ObjectId(eid) for eid in entity_ids if ObjectId.is_valid(eid)]}}
        ).to_list(length=500)
        entity_map = {str(e["_id"]): e for e in entities}
        entity_names = [e.get("name", "") for e in entities if e.get("name")]
        name_to_id = {e.get("name", ""): str(e["_id"]) for e in entities}

        if not entity_names:
            return

        # matching_patterns から既登録パターンを一括取得
        existing_patterns_docs = await ctx.db["matching_patterns"].find(
            {"corporate_id": ctx.corporate_id, "client_id": {"$in": entity_ids}}
        ).to_list(length=5000)
        existing_pattern_set: set = {
            (p["client_id"], p["pattern"]) for p in existing_patterns_docs
        }

        # 対象金額リスト
        inv_amounts = [int(inv.get("total_amount", inv.get("amount", 0))) for inv in invoices_group]

        # 絞り込み: 振込・入金系かつ金額が一致するユニーク摘要
        filtered_txs = txs
        if tx_type_filter:
            tx_type_values = (
                ["credit", "deposit"] if tx_type_filter == "credit"
                else ["debit", "withdrawal"]
            )
            filtered_txs = [t for t in txs if t.get("transaction_type") in tx_type_values]

        unique_descs = list({
            tx.get("description", "").strip()
            for tx in filtered_txs
            if tx.get("description", "").strip()
            and any(kw in tx.get("description", "") for kw in TRANSFER_KEYWORDS)
            and any(abs(int(tx.get("amount", 0)) - a) <= AMOUNT_TOLERANCE for a in inv_amounts)
        })

        if not unique_descs:
            return

        # AIコール
        for desc in unique_descs:
            total_ai_calls += 1
            ai_result = await AIService.fuzzy_match_names(desc, entity_names)

            if not ai_result or not ai_result.get("match"):
                continue

            matched_name = ai_result["match"]
            confidence = float(ai_result.get("confidence", 0))

            if confidence < threshold:
                logger.info(f"AI skipped (conf={confidence:.2f}): {desc!r} → {matched_name!r}")
                continue

            entity_id = name_to_id.get(matched_name)
            if not entity_id:
                continue

            pair_key = (entity_id, desc)
            if pair_key in already_added or pair_key in existing_pattern_set:
                continue
            already_added.add(pair_key)

            result_entry = {
                "client_id": entity_id,
                "client_name": matched_name,
                "pattern": desc,
                "confidence": confidence,
                "reason": ai_result.get("reason", ""),
            }
            added_results.append(result_entry)

            if not dry_run:
                await ctx.db["matching_patterns"].insert_one({
                    "corporate_id": ctx.corporate_id,
                    "client_id": entity_id,
                    "pattern": desc,
                    "source": "ai_suggest",
                    "confidence": confidence,
                    "created_at": datetime.utcnow(),
                    "used_count": 0,
                })

    # ── 1. issued請求書（client_idベース・入金系取引）──────────────
    issued_query: dict = {
        "corporate_id": ctx.corporate_id,
        "reconciliation_status": {"$in": ["unreconciled", None, ""]},
        "is_deleted": {"$ne": True},
        "document_type": {"$ne": "received"},
        "client_id": {"$exists": True, "$ne": None},
    }
    if fiscal_period:
        issued_query["fiscal_period"] = fiscal_period
    issued_invoices = await ctx.db["invoices"].find(issued_query).to_list(length=500)
    await _process_group(issued_invoices, "client_id", "credit")

    # ── 2. received請求書（vendor_idベース・出金系取引）─────────────
    # 承認状態に関わらずマッチング対象とする
    # 正常フローでは承認前に銀行取引が存在しないため自然にマッチしない
    # 例外的に支払いが先行した場合は自動マッチングして実態を正しく反映する
    received_query: dict = {
        "corporate_id": ctx.corporate_id,
        "reconciliation_status": {"$in": ["unreconciled", None, ""]},
        "is_deleted": {"$ne": True},
        "document_type": "received",
        "vendor_id": {"$exists": True, "$ne": None},
    }
    if fiscal_period:
        received_query["fiscal_period"] = fiscal_period
    received_invoices = await ctx.db["invoices"].find(received_query).to_list(length=500)
    await _process_group(received_invoices, "vendor_id", "debit")

    if not issued_invoices and not received_invoices:
        return {"status": "no_invoices", "added": [], "dry_run": dry_run}

    return {
        "status": "ok",
        "ai_calls": total_ai_calls,
        "added_count": len(added_results),
        "added": added_results,
        "dry_run": dry_run,
    }


@router.get("", summary="マッチング一覧を取得する")
async def list_matches(
    match_type: Optional[str] = None,
    fiscal_period: Optional[str] = None,
    transaction_id: Optional[str] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    query: dict = {"corporate_id": ctx.corporate_id, "is_active": {"$ne": False}}
    if match_type:
        query["match_type"] = match_type
    if fiscal_period:
        query["fiscal_period"] = fiscal_period
    if transaction_id:
        query["transaction_ids"] = transaction_id

    cursor = ctx.db["matches"].find(query).sort("matched_at", -1)
    docs = await cursor.to_list(length=500)

    result = []
    for doc in docs:
        serialized = _serialize(doc)
        if doc.get("match_type") == "auto_expense":
            tx_ids = doc.get("transaction_ids", [])
            if tx_ids:
                try:
                    tx = await ctx.db["transactions"].find_one({"_id": ObjectId(tx_ids[0])})
                    if tx:
                        serialized["transaction_date"] = tx.get("transaction_date")
                        serialized["transaction_description"] = tx.get("description")
                except Exception:
                    pass
        result.append(serialized)
    return result


@router.get("/{match_id}", summary="マッチング詳細を取得する")
async def get_match(
    match_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    doc = await get_doc_or_404(ctx.db, "matches", match_id, ctx.corporate_id, "match")
    if doc.get("is_active") is False:
        raise HTTPException(status_code=404, detail="Match not found")
    return _serialize(doc)


@router.patch("/{match_id}", summary="マッチング情報を更新する")
async def patch_match(
    match_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """user_action などのメタデータを更新する。"""
    oid = parse_oid(match_id, "match")
    allowed_fields = {"user_action", "note"}
    update_data = {k: v for k, v in payload.items() if k in allowed_fields}

    if not update_data:
        raise HTTPException(status_code=400, detail="更新可能なフィールドがありません")

    result = await ctx.db["matches"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Match not found")

    updated = await ctx.db["matches"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{match_id}", summary="マッチングを解除する")
async def delete_match(
    match_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    Unmatch: 論理削除（is_active: false）し、紐付いた transaction/document を unmatched に戻す。
    """
    match = await get_doc_or_404(ctx.db, "matches", match_id, ctx.corporate_id, "match")

    collection = "receipts" if match.get("match_type") == "receipt" else "invoices"
    for tid in match.get("transaction_ids", []):
        try:
            await ctx.db["transactions"].update_one(
                {"_id": ObjectId(tid)}, {"$set": {"status": "unmatched"}}
            )
        except Exception:
            pass
        try:
            await ctx.db["bank_transactions"].update_one(
                {"_id": ObjectId(tid)}, {"$set": {"status": "unmatched"}}
            )
        except Exception:
            pass
    for did in match.get("document_ids", []):
        try:
            await ctx.db[collection].update_one(
                {"_id": ObjectId(did)},
                {"$set": {"reconciliation_status": "unreconciled", "approval_status": "approved"}}
            )
        except Exception:
            pass

    for rid in match.get("receipt_ids", []):
        try:
            await ctx.db["receipts"].update_one(
                {"_id": ObjectId(rid)},
                {"$set": {"reconciliation_status": "unreconciled"}}
            )
        except Exception:
            pass

    await ctx.db["matches"].update_one(
        {"_id": match["_id"]},
        {"$set": {"is_active": False, "inactivated_at": datetime.utcnow()}},
    )

    # transaction-level イベント（reconciliation タイプは常に記録）
    if match.get("match_type") == "reconciliation":
        for tid in match.get("transaction_ids", []):
            await ctx.db["audit_logs"].insert_one({
                "corporate_id": ctx.corporate_id,
                "entity_type": "transaction",
                "transaction_id": tid,
                "action": "unmatched",
                "approver_id": ctx.user_id,
                "comment": "照合を取り消し",
                "timestamp": datetime.utcnow(),
            })

    all_doc_ids = list(match.get("document_ids", [])) + list(match.get("receipt_ids", []))
    if all_doc_ids:
        await _write_match_events(ctx.db, ctx.corporate_id, all_doc_ids, "unmatched", ctx.user_id, "照合を取り消し")

    return {"status": "unmatched", "match_id": match_id}
