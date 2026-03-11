import logging
from typing import Dict, Any, List
from app.services.ai_service import AIService
from app.db.mongodb import get_database
from bson import ObjectId

logger = logging.getLogger(__name__)

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
            "status": "pending_approval"
        })
        
        # 3. Bank Transactions Status
        unmatched_tx = await db["bank_transactions"].count_documents({
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
    async def process_query(corporate_id: str, query: str) -> str:
        """
        Main entry point for chat. Coordinates between Corporate Data and AI.
        """
        # Step 1: Securely fetch data ONLY for this corporate_id
        context = await ChatService.get_corporate_context(corporate_id)
        
        # Step 2: Handle Law AI coordination (Placeholder logic)
        # If query contains legal keywords, we could first query a specialized Law AI
        if any(word in query for word in ["法律", "税法", "インボイス制度", "源泉"]):
            # In a real scenario, this would be an API call to a separate Law RAG system
            law_context = "【法令AIからの補足】インボイス制度では、適格請求書発行事業者の登録番号確認が必須です。また、保存期間は原則7年です。"
            query = f"{query}\n\n(参考情報: {law_context})"
        
        # Step 3: Call Gemini with scoped context
        response = await AIService.chat_advisor(query, context)
        return response
