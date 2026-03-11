import os
import logging
import google.generativeai as genai
from typing import List, Optional, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

# Configure Gemini
api_key = settings.GOOGLE_API_KEY
if api_key:
    genai.configure(api_key=api_key)
else:
    logger.warning("GOOGLE_API_KEY not found in settings.")

# Model aliases (Using Flash Lite to maximize quota availability)
MODELS = {
    "pro": "gemini-2.0-flash-lite",
    "flash": "gemini-2.0-flash-lite",
}

class AIService:
    @staticmethod
    async def fuzzy_match_names(bank_desc: str, candidate_names: List[str]) -> Optional[Dict[str, Any]]:
        """
        AI-based fuzzy name matching.
        Returns the best candidate and confidence score.
        """
        model = genai.GenerativeModel(MODELS["flash"])
        prompt = f"""
        以下の銀行振込の名義（カナ等）と、取引先マスターの名前リストを比較し、最も一致する可能性が高いものを1つ選んでください。
        
        銀行振込名義: {bank_desc}
        取引先リスト: {", ".join(candidate_names)}
        
        返合法: JSON形式で返してください。
        {{
            "match": "一致した名前",
            "confidence": 0.0〜1.0の数値,
            "reason": "選んだ理由（簡潔に）"
        }}
        一致するものが全くない場合は "match": null にしてください。
        """
        
        try:
            response = str(model.generate_content(prompt).text)
            # Simple JSON extraction logic (could be improved)
            import json
            import re
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                return json.loads(match.group())
            return None
        except Exception as e:
            logger.error(f"Error in AI fuzzy matching: {e}")
            return None

    @staticmethod
    async def analyze_invoice_pdf(file_path: str) -> Optional[Dict[str, Any]]:
        """
        Analyze invoice PDF using Gemini Vision/Multimodal.
        Extracts key data based on learned or generic patterns.
        """
        model = genai.GenerativeModel(MODELS["flash"])
        # In a real scenario, we would upload the file to Gemini
        # For now, let's assume we use the path or content
        prompt = "この請求書から、発行元、合計金額、消費税額、振込先情報を抽出してください。JSON形式で出力してください。"
        
        try:
            # Full implementation would use genai.upload_file
            # For this mock-up of the service, we return a structured skeleton
            return {
                "vendor_name": "抽出された名前",
                "total_amount": 0,
                "tax_amount": 0,
                "due_date": "202x-xx-xx"
            }
        except Exception as e:
            logger.error(f"Error in AI invoice analysis: {e}")
            return None

    @staticmethod
    async def chat_advisor(query: str, context: Dict[str, Any]) -> str:
        """
        High-level chat advisor using Gemini 3.1 Pro.
        Injects corporate context (RAM/DB data) to provide accurate answers.
        """
        model = genai.GenerativeModel(MODELS["pro"])
        
        system_instruction = f"""
        あなたは「Tax-Agent」の専属AIアドバイザーです。
        ユーザーは企業の経理担当者または経営者です。
        
        以下の制約を厳守してください：
        1. 提供された「コーポレート・コンテキスト」に基づいた情報のみを事実として扱ってください。
        2. 他の企業のデータや無関係な情報を捏造しないでください。
        3. 法令や税務の専門的な判断が必要な場合は「法令AIに確認します」と前置きするか、一般的な一般論であることを明示してください。
        
        【コーポレート・コンテキスト】
        会社名: {context.get('company_name')}
        現在のステータス:
        - 承認待ちの請求書: {context.get('pending_invoices_count')}件
        - 未一致の銀行明細: {context.get('unmatched_transactions_count')}件
        - 直近のキャッシュフローアラート: {context.get('alerts')}
        """
        
        try:
            chat = model.start_chat(history=[])
            response = chat.send_message(f"{system_instruction}\n\nユーザーの質問: {query}")
            return str(response.text)
        except Exception as e:
            logger.error(f"Error in Chat Advisor: {e}")
            return "申し訳ありません。現在アドバイザー機能が一時的に利用できません。"
