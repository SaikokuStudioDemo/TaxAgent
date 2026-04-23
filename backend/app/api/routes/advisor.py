from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.api.helpers import resolve_corporate_id
from app.core.config import DEFAULT_TAX_RATE
from app.db.mongodb import get_database
from app.services.chat_service import ChatService, get_ai_credit_limit
from app.services.agent_tools import (
    get_pending_list,
    get_document_detail,
    search_client,
    get_approval_status,
    get_budget_comparison,
    read_file,
    suggest_journal_entry,
    suggest_reconciliation,
    draft_expense_claim,
    draft_invoice,
    # Task#17-C: 実行系ツール
    exec_submit_expense_claim,
    exec_send_invoice,
    exec_approve_document,
    exec_execute_reconciliation,
    exec_export_csv,
    exec_export_zengin,
    exec_notify_tax_advisor,
)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# ログイン時の挨拶生成
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/greeting", summary="ログイン時の挨拶を生成する")
async def get_greeting(
    current_user: dict = Depends(get_current_user),
):
    """
    コーポレートコンテキストを元にルールベースで挨拶文を生成する。
    Claude Sonnet は使わない（ログイン毎の API コスト削減のため）。
    """
    firebase_uid = current_user.get("uid")
    corporate_id, user_id = await resolve_corporate_id(firebase_uid)

    greeting = await ChatService.generate_greeting(corporate_id, user_id)
    return {"greeting": greeting}


# ─────────────────────────────────────────────────────────────────────────────
# 既存：AIチャット
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/chat", summary="AIアドバイザーと対話する")
async def chat_with_advisor(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    AI Chat Advisor endpoint.
    ④ 戻り値: {"response": str, "warning": str | None}
    上限超過時は 429 を返す。
    """
    query = payload.get("query")
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    firebase_uid = current_user.get("uid")
    corporate_id, user_id = await resolve_corporate_id(firebase_uid)

    try:
        # process_query は {"response": str, "warning": str | None} を返す
        result = await ChatService.process_query(corporate_id, query, user_id)
        return result
    except HTTPException:
        raise  # 429 等はそのまま伝播
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Advisor error: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# Task#31: AI クレジット残量取得
# ─────────────────────────────────────────────────────────────────────────────

def _get_next_month_first() -> str:
    """翌月1日0:00（JST）の ISO 文字列を返す。"""
    JST = timezone(timedelta(hours=9))
    now = datetime.now(JST)
    if now.month == 12:
        next_month = now.replace(
            year=now.year + 1, month=1, day=1,
            hour=0, minute=0, second=0, microsecond=0
        )
    else:
        next_month = now.replace(
            month=now.month + 1, day=1,
            hour=0, minute=0, second=0, microsecond=0
        )
    return next_month.isoformat()


@router.get("/credits", summary="AIクレジット残量を取得する")
async def get_credits(
    current_user: dict = Depends(get_current_user),
):
    """
    ③ 二重クエリを解消：resolve_corporate_id の戻り値 corporate_id から
       {"_id": ObjectId(corporate_id)} で1回だけ取得する。
    """
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    # ③ ObjectId(_id) で1回だけ取得
    corp = await db["corporates"].find_one({"_id": ObjectId(corporate_id)})

    plan_id = corp.get("planId", "plan_basic") if corp else "plan_basic"
    limit = await get_ai_credit_limit(plan_id)
    current_usage = corp.get("monthly_ai_usage", 0) if corp else 0
    remaining = max(0, limit - current_usage)

    return {
        "plan_id": plan_id,
        "limit": limit,
        "current_usage": current_usage,
        "remaining": remaining,
        "reset_at": _get_next_month_first(),
        "warning": remaining <= limit * 0.1,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 履歴取得
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/history", summary="チャット履歴を取得する")
async def get_chat_history(
    limit: int = 20,
    before: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    自分のチャット履歴を取得する。

    - limit: 最大取得件数（1〜50、デフォルト20）
    - before: このISO8601タイムスタンプより古いメッセージを取得（無限スクロール用）
    - 返却順: created_at ASC（古い順）
    """
    firebase_uid = current_user.get("uid")
    corporate_id, user_id = await resolve_corporate_id(firebase_uid)
    db = get_database()

    query_filter = {
        "corporate_id": corporate_id,
        "user_id": user_id,
    }

    if before:
        try:
            # Python 3.9 対応：Z suffix を +00:00 に変換し tzinfo を除去
            before_str = before.replace("Z", "+00:00")
            before_dt = datetime.fromisoformat(before_str).replace(tzinfo=None)
            query_filter["created_at"] = {"$lt": before_dt}
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid before timestamp format. Use ISO8601.",
            )

    limit = min(max(1, limit), 50)

    # DESC で取得し reverse して ASC に戻す（カーソルページネーション）
    # 二次ソートキー _id で同一 created_at 内の順序を保証
    cursor = (
        db["chat_histories"]
        .find(query_filter)
        .sort([("created_at", -1), ("_id", -1)])
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    docs.reverse()  # ASC に並び替え

    return {
        "messages": [
            {
                "id": str(d["_id"]),
                "role": d["role"],
                "content": d["content"],
                "created_at": d["created_at"].isoformat(),
            }
            for d in docs
        ],
        "count": len(docs),
        "has_more": len(docs) == limit,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 追加：エージェントツール（読み取り系 6 本）
# すべて認証済みユーザーの corporate_id でスコープを絞る。
# ─────────────────────────────────────────────────────────────────────────────

# ── リクエストモデル ─────────────────────────────────────────────────────────

class PendingListRequest(BaseModel):
    list_type: str = "all"  # "receipts" | "invoices" | "transactions" | "all"


class DocumentDetailRequest(BaseModel):
    document_type: str   # "receipt" | "invoice" | "transaction"
    document_id: str


class SearchClientRequest(BaseModel):
    query: str
    limit: int = 5


class ApprovalStatusRequest(BaseModel):
    document_type: str   # "receipt" | "invoice"
    document_id: str


class BudgetComparisonRequest(BaseModel):
    fiscal_period: Optional[str] = None  # "YYYY-MM"。None なら当月


class ReadFileRequest(BaseModel):
    file_url: str
    doc_type: str = "receipt"  # "receipt" | "invoice"


# ── ① 未処理一覧 ─────────────────────────────────────────────────────────────

@router.post("/tools/pending_list", summary="未処理書類・取引の一覧を取得する")
async def tool_get_pending_list(
    payload: PendingListRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    未承認の領収書・受領請求書、未消込の銀行明細を返す。
    list_type で種別を絞り込める。
    """
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    return await get_pending_list(corporate_id, list_type=payload.list_type)


# ── ② ドキュメント詳細 ───────────────────────────────────────────────────────

@router.post("/tools/document_detail", summary="特定ドキュメントの詳細を取得する")
async def tool_get_document_detail(
    payload: DocumentDetailRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    document_type（receipt / invoice / transaction）と document_id を指定して
    詳細情報を取得する。receipt / invoice は承認履歴も付加される。
    """
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    return await get_document_detail(
        corporate_id,
        document_type=payload.document_type,
        document_id=payload.document_id,
    )


# ── ③ 取引先検索 ─────────────────────────────────────────────────────────────

@router.post("/tools/search_client", summary="取引先を名前で検索する")
async def tool_search_client(
    payload: SearchClientRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    取引先名を部分一致（大文字小文字無視）で検索する。
    limit で最大取得件数を指定できる（デフォルト 5）。
    """
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    return await search_client(corporate_id, query=payload.query, limit=payload.limit)


# ── ④ 承認状況確認 ───────────────────────────────────────────────────────────

@router.post("/tools/approval_status", summary="ドキュメントの承認状況を確認する")
async def tool_get_approval_status(
    payload: ApprovalStatusRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    指定した receipt / invoice の承認ステータス・現在ステップ・
    次の承認者名・承認履歴を返す。
    """
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    return await get_approval_status(
        corporate_id,
        document_type=payload.document_type,
        document_id=payload.document_id,
    )


# ── ⑤ 予算対比 ──────────────────────────────────────────────────────────────

@router.post("/tools/budget_comparison", summary="予算対比・実績を確認する")
async def tool_get_budget_comparison(
    payload: BudgetComparisonRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    指定会計期間（YYYY-MM）の予算と実績を比較する。
    fiscal_period を省略すると当月を使う。
    budgets コレクション未実装のため budget_total は現在 None を返す。
    """
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    return await get_budget_comparison(
        corporate_id,
        fiscal_period=payload.fiscal_period,
    )


# ── ⑥ ファイル読み取り（プレースホルダー） ────────────────────────────────────

@router.post("/tools/read_file", summary="ファイルを読み取る（OCR連携予定）")
async def tool_read_file(
    payload: ReadFileRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    将来の Gemini Flash OCR 連携用プレースホルダー。
    現時点では not_implemented を返す。
    """
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    return await read_file(
        corporate_id,
        file_url=payload.file_url,
        doc_type=payload.doc_type,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 提案系ツール（4本）
# ─────────────────────────────────────────────────────────────────────────────

class SuggestJournalEntryRequest(BaseModel):
    document_type: str               # "receipt" | "invoice"
    document_id: str
    amount: Optional[int] = None
    description: Optional[str] = None


class SuggestReconciliationRequest(BaseModel):
    transaction_id: str


class DraftExpenseClaimRequest(BaseModel):
    amount: int
    description: str
    date: str                         # "YYYY-MM-DD"
    category: Optional[str] = None
    payment_method: Optional[str] = None


class DraftInvoiceRequest(BaseModel):
    client_id: str
    amount: int
    description: str
    due_date: Optional[str] = None   # "YYYY-MM-DD"。None なら today+30日
    tax_rate: int = DEFAULT_TAX_RATE


# ── 仕訳提案 ──────────────────────────────────────────────────────────────────

@router.post("/tools/suggest_journal_entry", summary="仕訳を提案する")
async def tool_suggest_journal_entry(
    payload: SuggestJournalEntryRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    ドキュメントの内容から勘定科目・税区分を提案する。
    journal_rules ルール → JOURNAL_MAP キーワード → 雑費 の優先順で照合する。
    """
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    return await suggest_journal_entry(
        corporate_id,
        document_type=payload.document_type,
        document_id=payload.document_id,
        amount=payload.amount,
        description=payload.description,
    )


# ── 消込候補提案 ──────────────────────────────────────────────────────────────

@router.post("/tools/suggest_reconciliation", summary="消込候補を提案する")
async def tool_suggest_reconciliation(
    payload: SuggestReconciliationRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    指定した銀行取引に対してスコアの高い消込候補を最大5件返す。
    """
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    return await suggest_reconciliation(
        corporate_id,
        transaction_id=payload.transaction_id,
    )


# ── 経費申請下書き ─────────────────────────────────────────────────────────────

@router.post("/tools/draft_expense_claim", summary="経費申請の下書きを作成する")
async def tool_draft_expense_claim(
    payload: DraftExpenseClaimRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    経費申請の下書きを作成する（DB への保存なし）。
    category が未指定の場合は description からキーワード推測する。
    confirmation_required=True で返すため、AIが確認を促すことができる。
    """
    firebase_uid = current_user.get("uid")
    corporate_id, user_id = await resolve_corporate_id(firebase_uid)
    return await draft_expense_claim(
        corporate_id,
        user_id=user_id,
        amount=payload.amount,
        description=payload.description,
        date_str=payload.date,
        category=payload.category,
        payment_method=payload.payment_method,
    )


# ── 請求書下書き ──────────────────────────────────────────────────────────────

@router.post("/tools/draft_invoice", summary="請求書の下書きを作成する")
async def tool_draft_invoice(
    payload: DraftInvoiceRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    請求書の下書きを作成する（DB への保存なし）。
    取引先が存在しない場合は error を返す。
    confirmation_required=True で返すため、AIが確認を促すことができる。
    """
    firebase_uid = current_user.get("uid")
    corporate_id, user_id = await resolve_corporate_id(firebase_uid)
    return await draft_invoice(
        corporate_id,
        user_id=user_id,
        client_id=payload.client_id,
        amount=payload.amount,
        description=payload.description,
        due_date=payload.due_date,
        tax_rate=payload.tax_rate,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task#17-C: 実行系ツール（7本）
# ① エンドポイントは advisor.py、ロジックは agent_tools.py の既存パターンに統一
# ─────────────────────────────────────────────────────────────────────────────

class SubmitExpenseClaimRequest(BaseModel):
    date: str
    amount: int
    payee: str
    category: str
    payment_method: str
    tax_rate: int = DEFAULT_TAX_RATE
    file_url: Optional[str] = None
    fiscal_period: str = ""
    confirmed: bool = False


@router.post("/tools/submit_expense_claim", summary="経費申請を登録する")
async def tool_submit_expense_claim(
    payload: SubmitExpenseClaimRequest,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, user_id = await resolve_corporate_id(firebase_uid)
    return await exec_submit_expense_claim(
        corporate_id, user_id, **payload.model_dump()
    )


class SendInvoiceRequest(BaseModel):
    invoice_id: str
    confirmed: bool = False


@router.post("/tools/send_invoice", summary="発行請求書を送付する")
async def tool_send_invoice(
    payload: SendInvoiceRequest,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, user_id = await resolve_corporate_id(firebase_uid)
    return await exec_send_invoice(
        corporate_id, user_id,
        invoice_id=payload.invoice_id,
        confirmed=payload.confirmed,
    )


class ApproveDocumentRequest(BaseModel):
    document_type: str
    document_id: str
    action: str
    comment: Optional[str] = None
    confirmed: bool = False


@router.post("/tools/approve_document", summary="ドキュメントを承認または差し戻しする")
async def tool_approve_document(
    payload: ApproveDocumentRequest,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, user_id = await resolve_corporate_id(firebase_uid)
    return await exec_approve_document(
        corporate_id, user_id, **payload.model_dump()
    )


class ExecuteReconciliationRequest(BaseModel):
    transaction_ids: List[str]
    document_ids: List[str]
    match_type: str
    fiscal_period: str = ""
    confirmed: bool = False


@router.post("/tools/execute_reconciliation", summary="消込を実行する")
async def tool_execute_reconciliation(
    payload: ExecuteReconciliationRequest,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, user_id = await resolve_corporate_id(firebase_uid)
    return await exec_execute_reconciliation(
        corporate_id, user_id, **payload.model_dump()
    )


class ExportCsvRequest(BaseModel):
    format_type: str
    doc_type: str
    fiscal_period: Optional[str] = None
    confirmed: bool = False


@router.post("/tools/export_csv", summary="CSVを出力する（ダウンロードURL返却）")
async def tool_export_csv(
    payload: ExportCsvRequest,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    return await exec_export_csv(
        corporate_id, **payload.model_dump()
    )


class ExportZenginRequest(BaseModel):
    fiscal_period: Optional[str] = None
    confirmed: bool = False


@router.post("/tools/export_zengin", summary="全銀データを出力する（ダウンロードURL返却）")
async def tool_export_zengin(
    payload: ExportZenginRequest,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    return await exec_export_zengin(
        corporate_id, **payload.model_dump()
    )


class NotifyTaxAdvisorRequest(BaseModel):
    message: str
    priority: str = "normal"
    confirmed: bool = False


@router.post("/tools/notify_tax_advisor", summary="税理士にメッセージを送信する")
async def tool_notify_tax_advisor(
    payload: NotifyTaxAdvisorRequest,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, user_id = await resolve_corporate_id(firebase_uid)
    return await exec_notify_tax_advisor(
        corporate_id, user_id, **payload.model_dump()
    )
