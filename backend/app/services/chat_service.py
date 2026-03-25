import logging
import httpx
from typing import Dict, Any, List, Optional
from app.services.ai_service import AIService
from app.db.mongodb import get_database
from app.core.config import settings
from bson import ObjectId

logger = logging.getLogger(__name__)

LAW_AGENT_ID = "tax_01"

class ChatService:
    @staticmethod
    async def get_corporate_context(corporate_id: str) -> Dict[str, Any]:
        """
        Fetch current status from DB for a specific corporation.
        This provides the 'RAM' (Live Context) for the AI.
        """
        db = get_database()
        
        # 1. Basic Profile
        profile = await db["company_profiles"].find_one({"corporate_id": corporate_id})
        company_name = profile.get("company_name", "不明な企業") if profile else "不明な企業"
        
        # 2. Invoices Status
        pending_invoices = await db["invoices"].count_documents({
            "corporate_id": corporate_id,
            "approval_status": "pending_approval"
        })
        
        # 3. Bank Transactions Status
        unmatched_tx = await db["transactions"].count_documents({
            "corporate_id": corporate_id,
            "status": "unmatched"
        })
        
        # 4. Recent Alerts
        alerts_cursor = db["notifications"].find({
            "corporate_id": corporate_id,
            "read": False
        }).sort("created_at", -1).limit(3)
        alerts = await alerts_cursor.to_list(length=3)
        alert_msgs = [a.get("message") for a in alerts]
        
        return {
            "company_name": company_name,
            "pending_invoices_count": pending_invoices,
            "unmatched_transactions_count": unmatched_tx,
            "alerts": "; ".join(alert_msgs) if alert_msgs else "特になし"
        }

    @staticmethod
    async def query_law_agent(query: str) -> Optional[str]:
        """
        Call the external Law Agent API for legal/tax FAQ questions.
        Returns the response text, or None if it cannot answer.
        """
        url = f"{settings.LAW_AGENT_URL}/api/chat"
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
    async def process_query(corporate_id: str, query: str) -> str:
        """
        Main entry point for chat. Coordinates between Corporate Data and AI.
        Flow:
          1. Try to answer from corporate context (Gemini)
          2. If Gemini signals it cannot answer → ask Law Agent
          3. If Law Agent also cannot answer → return fallback message
        """
        # Step 1: Fetch data scoped to this corporate_id
        context = await ChatService.get_corporate_context(corporate_id)

        # Step 2: Ask Gemini. Instruct it to reply with a special marker if it cannot answer.
        gemini_response = await AIService.chat_advisor(query, context)

        # Step 3: If Gemini couldn't answer, escalate to Law Agent
        if "[[LAW_AGENT_REQUIRED]]" in gemini_response:
            logger.info(f"Escalating to Law Agent for query: {query[:80]}")
            law_response = await ChatService.query_law_agent(query)
            if law_response:
                return law_response
            else:
                return (
                    "申し訳ありません。お客様のデータおよび税法・関連法令のFAQを確認しましたが、"
                    "この質問にはお答えできませんでした。"
                    "担当の税理士、またはお近くの税理士にお問い合わせください。"
                )

        return gemini_response
