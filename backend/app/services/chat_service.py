import asyncio
import calendar
import logging
import httpx
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Set

from bson import ObjectId

from app.services.ai_service import AIService
from app.db.mongodb import get_database
from app.core.config import settings
from app.api.helpers import build_name_map, build_pending_approval_query

logger = logging.getLogger(__name__)

LAW_AGENT_ID = "tax_01"
LAW_AGENT_REQUIRED_MARKER = "[[LAW_AGENT_REQUIRED]]"
TAX_ADVISOR_REQUIRED_MARKER = "[[TAX_ADVISOR_REQUIRED]]"

# ─────────────────────────────────────────────────────────────────────────────
# Task#31: AI クレジット管理
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_AI_CREDIT_LIMITS: Dict[str, int] = {
    "plan_basic": 100,
    "plan_standard": 500,
    "plan_premium": 2000,
}


async def get_law_agent_url() -> str:
    """
    LAW_AGENT_URL を system_settings から取得する。
    未設定の場合は .env の値にフォールバックする。
    """
    db = get_database()
    setting = await db["system_settings"].find_one({"key": "law_agent_url"})
    if setting and setting.get("value"):
        return setting["value"]
    return settings.LAW_AGENT_URL


async def get_ai_credit_limit(plan_id: str) -> int:
    """
    system_settings から ai_credit_limits を取得する。
    未設定の場合は DEFAULT_AI_CREDIT_LIMITS を使う。
    """
    db = get_database()
    settings_doc = await db["system_settings"].find_one({"key": "ai_credit_limits"})
    if settings_doc and isinstance(settings_doc.get("value"), dict):
        limits: Dict[str, int] = settings_doc["value"]
        return limits.get(plan_id, DEFAULT_AI_CREDIT_LIMITS.get(plan_id, 100))
    return DEFAULT_AI_CREDIT_LIMITS.get(plan_id, 100)


def _calc_pending_days(created_at: Any, today_start: datetime) -> int:
    """datetime から今日までの経過日数を計算する（型安全・負値なし）。"""
    if not isinstance(created_at, datetime):
        return 0
    base = created_at.replace(hour=0, minute=0, second=0, microsecond=0)
    return max(0, (today_start - base).days)


class ChatService:
    @staticmethod
    async def get_corporate_context(corporate_id: str) -> Dict[str, Any]:
        """
        Fetch current status from DB for a specific corporation.
        This provides the 'RAM' (Live Context) for the AI.

        Phase 1: 独立クエリを asyncio.gather で並列取得。
        Phase 2: 取得済み submitted_by から build_name_map を呼ぶ（順次）。
        """
        db = get_database()

        # ── Phase 1: 独立クエリを並列取得 ─────────────────────────────
        _receipts_query = build_pending_approval_query(corporate_id)
        _invoices_query = build_pending_approval_query(
            corporate_id, {"document_type": "received"}
        )
        _approved_unreconciled_query = {
            "corporate_id": corporate_id,
            "approval_status": "approved",
            "reconciliation_status": {"$ne": "reconciled"},
            "is_deleted": {"$ne": True},
        }
        (
            profile,
            pending_receipts_raw,
            pending_invoices_raw,
            recent_deposits_raw,
            unmatched_tx_count,
            alerts_raw,
            pending_receipts_count,
            pending_invoices_count,
            approved_unreconciled_receipts_count,
        ) = await asyncio.gather(
            db["company_profiles"].find_one({"corporate_id": corporate_id}),
            db["receipts"].find(_receipts_query).sort("created_at", -1).to_list(length=5),
            db["invoices"].find(_invoices_query).sort("created_at", -1).to_list(length=5),
            db["transactions"].find({
                "corporate_id": corporate_id,
                "status": "unmatched",
                "deposit_amount": {"$gt": 0},
            }).sort("transaction_date", -1).to_list(length=3),
            db["transactions"].count_documents({
                "corporate_id": corporate_id,
                "status": "unmatched",
            }),
            db["notifications"].find({
                "corporate_id": corporate_id,
                "read": False,
            }).sort("created_at", -1).limit(3).to_list(length=3),
            db["receipts"].count_documents(_receipts_query),
            db["invoices"].count_documents(_invoices_query),
            db["receipts"].count_documents(_approved_unreconciled_query),
        )

        # ── Phase 2: submitter 名前解決（receipts+invoices 取得後に実行） ──
        all_pending = pending_receipts_raw + pending_invoices_raw
        submitter_ids: Set[str] = {
            str(d["submitted_by"]) for d in all_pending if d.get("submitted_by")
        }
        name_map = await build_name_map(db, submitter_ids)

        # ── 未承認書類リスト組み立て ──────────────────────────────────
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        pending_documents: List[Dict[str, Any]] = []

        for doc in pending_receipts_raw:
            pending_documents.append({
                "id": str(doc.get("_id", "")),
                "type": "領収書",
                "amount": doc.get("amount") or doc.get("total_amount") or 0,
                "submitter_name": name_map.get(str(doc.get("submitted_by", "")), "不明"),
                "date": str(doc.get("date") or doc.get("issue_date") or "")[:10],
                "pending_days": _calc_pending_days(doc.get("created_at"), today_start),
            })

        for doc in pending_invoices_raw:
            pending_documents.append({
                "id": str(doc.get("_id", "")),
                "type": "受領請求書",
                "amount": doc.get("total_amount") or doc.get("amount") or 0,
                "submitter_name": name_map.get(str(doc.get("submitted_by", "")), "不明"),
                "date": str(doc.get("date") or doc.get("issue_date") or "")[:10],
                "pending_days": _calc_pending_days(doc.get("created_at"), today_start),
            })

        # ── 未消込入金リスト ──────────────────────────────────────────
        recent_deposits_list: List[Dict[str, Any]] = []
        for tx in recent_deposits_raw:
            txdate = tx.get("transaction_date")
            recent_deposits_list.append({
                "id": str(tx.get("_id", "")),
                "amount": tx.get("deposit_amount") or 0,
                "description": tx.get("description") or "",
                "date": str(txdate)[:10] if txdate else "",
            })

        # ── 今月の残日数 ─────────────────────────────────────────────
        today = date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]
        days_until_month_end = (date(today.year, today.month, last_day) - today).days

        # ── 初回アクセス判定 & last_accessed_at 更新 ─────────────────
        # ObjectId 変換失敗や doc 欠落でもクラッシュしないよう try/except
        is_first_access_today = True
        try:
            corporate_doc = await db["corporates"].find_one(
                {"_id": ObjectId(corporate_id)}
            )
            last_accessed = corporate_doc.get("last_accessed_at") if corporate_doc else None
            if last_accessed:
                diff = datetime.utcnow() - last_accessed
                is_first_access_today = diff > timedelta(hours=1)
            await db["corporates"].update_one(
                {"_id": ObjectId(corporate_id)},
                {"$set": {"last_accessed_at": datetime.utcnow()}},
            )
        except Exception:
            pass  # 不正な ObjectId やドキュメント欠落でも継続

        # ── 会社名・アラート ──────────────────────────────────────────
        company_name = profile.get("company_name", "不明な企業") if profile else "不明な企業"
        alert_msgs = [a.get("message") for a in alerts_raw if a.get("message")]

        return {
            "company_name": company_name,
            "pending_receipts_count": pending_receipts_count,
            "pending_invoices_count": pending_invoices_count,
            "approved_unreconciled_receipts_count": approved_unreconciled_receipts_count,
            "unmatched_transactions_count": unmatched_tx_count,
            "pending_documents": pending_documents,
            "recent_deposits": recent_deposits_list,
            "days_until_month_end": days_until_month_end,
            "is_first_access_today": is_first_access_today,
            "alerts": "; ".join(alert_msgs) if alert_msgs else "特になし",
        }

    @staticmethod
    async def query_law_agent(query: str) -> Optional[str]:
        """
        Call the external Law Agent API for legal/tax FAQ questions.
        Returns the response text, or None if it cannot answer.
        """
        url = f"{await get_law_agent_url()}/api/chat"
        payload = {
            "message": query,
            "agent_id": LAW_AGENT_ID,
            "history": []
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, json=payload)
                res.raise_for_status()
                data = res.json()
                response_text = data.get("response", "")
                if not response_text:
                    return None
                return response_text
        except Exception as e:
            logger.error(f"Law Agent request failed: {e}")
            return None

    @staticmethod
    async def notify_tax_advisor(
        corporate_id: str,
        user_id: Optional[str],
        query: str,
        reason: str = "ai_escalation",
    ) -> None:
        """
        税理士へのエスカレーションを notifications コレクションに記録する。
        実際のメール送信は将来の notification_service が担当。
        現時点では DB への記録のみ行い、失敗しても処理を止めない。
        """
        db = get_database()
        try:
            await db["notifications"].insert_one({
                "corporate_id": corporate_id,
                "type": "tax_advisor_required",
                "user_id": user_id,
                "query": query,
                "reason": reason,
                "status": "pending",
                "read": False,
                "created_at": datetime.utcnow(),
            })
            logger.info(
                f"Tax advisor notification recorded: corporate_id={corporate_id}"
            )
        except Exception as e:
            logger.error(f"Failed to record tax advisor notification: {e}")

    @staticmethod
    async def save_chat_history(
        corporate_id: str,
        user_id: str,
        user_message: str,
        ai_response: str,
    ) -> None:
        """
        ユーザーメッセージと AI 回答を chat_histories に保存する。
        保存失敗してもチャット処理は続行する（例外を外に漏らさない）。
        user と ai の両メッセージに同じ created_at を使うことで
        一括 insert_many で保存する。
        """
        db = get_database()
        now = datetime.utcnow()
        try:
            await db["chat_histories"].insert_many([
                {
                    "corporate_id": corporate_id,
                    "user_id": user_id,
                    "channel_id": None,
                    "role": "user",
                    "content": user_message,
                    "tool_calls": None,
                    "created_at": now,
                },
                {
                    "corporate_id": corporate_id,
                    "user_id": user_id,
                    "channel_id": None,
                    "role": "ai",
                    "content": ai_response,
                    "tool_calls": None,
                    "created_at": now,
                },
            ])
        except Exception as e:
            logger.error(f"Failed to save chat history: {e}")

    @staticmethod
    async def generate_greeting(
        corporate_id: str,
        user_id: Optional[str] = None,
    ) -> str:
        """
        コーポレートコンテキストを元にルールベースで挨拶文を生成する。
        Claude Sonnet は使わない（ログイン毎の API コスト削減・高速化のため）。
        """
        context = await ChatService.get_corporate_context(corporate_id)

        recent_deposits  = context.get("recent_deposits", [])
        days_left        = context.get("days_until_month_end", 0)
        pending_receipts = context.get("pending_receipts_count", 0)
        pending_invoices = context.get("pending_invoices_count", 0)
        unmatched_tx     = context.get("unmatched_transactions_count", 0)
        approved_unreconciled = context.get("approved_unreconciled_receipts_count", 0)

        # ── ユーザー名取得（失敗しても名前なしで継続） ──────────────────
        name = ""
        if user_id:
            try:
                from bson import ObjectId
                db = get_database()
                emp = await db["employees"].find_one(
                    {"_id": ObjectId(user_id)}, {"name": 1}
                )
                if emp:
                    name = emp.get("name", "")
            except Exception:
                pass

        greeting_head = f"{name}さん、現在の状況です。" if name else "現在の状況です。"

        # ── タスクがない場合 ──────────────────────────────────────────────
        total_tasks = pending_receipts + pending_invoices + unmatched_tx + approved_unreconciled
        if total_tasks == 0 and not recent_deposits:
            return (
                f"{greeting_head}\n"
                "現在、対応が必要な作業はありません。\n"
                "何かお手伝いできることがあればお気軽にどうぞ！"
            )

        # ── タスクあり：番号付きリスト ────────────────────────────────────
        items: List[str] = []

        if pending_receipts > 0:
            items.append(f"未承認の領収書が{pending_receipts}件あります")
        if pending_invoices > 0:
            items.append(f"未承認の受領請求書が{pending_invoices}件あります")
        if approved_unreconciled > 0:
            items.append(f"承認済み領収書が{approved_unreconciled}件、未消込です")

        if unmatched_tx > 0:
            if recent_deposits:
                dep = recent_deposits[0]
                items.append(
                    f"未消込の入金があります"
                    f"（直近：{dep.get('description', '')} "
                    f"¥{dep.get('amount', 0):,}）"
                )
            else:
                items.append(f"未消込の銀行明細が{unmatched_tx}件あります")

        if 0 <= days_left <= 3:
            items.append(f"今月の締め日まであと{days_left}日です")

        lines = [greeting_head]
        for i, item in enumerate(items, 1):
            lines.append(f"{i}. {item}")
        lines.append("\nどこから始めますか？\n上記にない場合はお気軽にどうぞ！")

        return "\n".join(lines)

    @staticmethod
    async def process_query(
        corporate_id: str,
        query: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point for chat. Coordinates between Corporate Data and AI.

        ④ 戻り値: {"response": str, "warning": str | None}
          warning は残り利用回数が上限の10%以下になった場合のみ文字列を返す。

        フロー：
          ① 上限チェック（超過なら 429 を raise）
          Claude Sonnet
            → [[LAW_AGENT_REQUIRED]] → Law Agent
            → [[TAX_ADVISOR_REQUIRED]] → 税理士通知
            → 通常回答
          ① 正常レスポンス後に monthly_ai_usage を +1（エラー時は記録しない）
        """
        from fastapi import HTTPException

        db = get_database()

        # ─── ② process_query の先頭：上限チェック ────────────────────────────
        # ① ObjectId(_id) で検索（firebase_uid ではない）
        corp = await db["corporates"].find_one({"_id": ObjectId(corporate_id)})
        plan_id = corp.get("planId", "plan_basic") if corp else "plan_basic"
        limit = await get_ai_credit_limit(plan_id)
        current_usage = corp.get("monthly_ai_usage", 0) if corp else 0

        if current_usage >= limit:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "AI_CREDIT_LIMIT_EXCEEDED",
                    "message": (
                        f"今月のAIチャット利用上限（{limit}回）に達しました。"
                        "プランをアップグレードするか、来月をお待ちください。"
                    ),
                    "current_usage": current_usage,
                    "limit": limit,
                },
            )

        context = await ChatService.get_corporate_context(corporate_id)
        response = await AIService.chat_advisor(query, context)

        if LAW_AGENT_REQUIRED_MARKER in response:
            logger.info(f"Escalating to Law Agent: {query[:80]}")
            law_response = await ChatService.query_law_agent(query)

            if law_response:
                if TAX_ADVISOR_REQUIRED_MARKER in law_response:
                    # Law Agent が「税理士が必要」と判断した場合
                    await ChatService.notify_tax_advisor(
                        corporate_id, user_id, query, "law_agent_escalation"
                    )
                    response = (
                        "この件は専門的な税務判断が必要です。\n\n"
                        "担当の税理士への確認をお勧めします。\n"
                        "税理士への通知を記録しました。"
                    )
                else:
                    # Law Agent が正常回答できた場合
                    response = law_response
            else:
                # Law Agent も回答できなかった場合 → 税理士へエスカレーション
                await ChatService.notify_tax_advisor(
                    corporate_id, user_id, query, "law_agent_no_answer"
                )
                response = (
                    "税法・関連法令のFAQを確認しましたが、"
                    "この件には専門的な税務判断が必要です。\n\n"
                    "担当の税理士への確認をお勧めします。\n"
                    "税理士への通知を記録しました。"
                )

        elif TAX_ADVISOR_REQUIRED_MARKER in response:
            # Claude Sonnet が直接「税理士が必要」と判断した場合
            await ChatService.notify_tax_advisor(
                corporate_id, user_id, query, "direct_escalation"
            )
            response = (
                "この件は専門的な税務判断が必要です。\n\n"
                "担当の税理士への確認をお勧めします。\n"
                "税理士への通知を記録しました。"
            )

        # 履歴を保存（失敗してもレスポンスは返す）
        if user_id:
            await ChatService.save_chat_history(
                corporate_id, user_id, query, response
            )

        # ─── ② process_query の末尾：利用量記録（正常レスポンス後のみ） ────────
        # ① ObjectId(_id) で更新（firebase_uid ではない）
        try:
            await db["corporates"].update_one(
                {"_id": ObjectId(corporate_id)},
                {
                    "$inc": {"monthly_ai_usage": 1},
                    "$set": {"monthly_ai_usage_updated_at": datetime.utcnow()},
                },
            )
        except Exception as e:
            logger.error(f"Failed to record AI usage: {e}")

        # ─── ④ warning の付加（残り10%以下） ────────────────────────────────────
        new_usage = current_usage + 1
        remaining = limit - new_usage
        warning: Optional[str] = None
        if remaining <= limit * 0.1:
            warning = (
                f"AIチャットの残り利用回数が{remaining}回です。"
                "上限に近づいています。"
            )

        return {"response": response, "warning": warning}
