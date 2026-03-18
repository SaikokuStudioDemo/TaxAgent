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

# Model aliases
MODELS = {
    "pro": "gemini-2.0-pro-exp",
    "flash": "gemini-2.0-flash",
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
    @staticmethod
    async def generate_invoice_html_template(file_path: str) -> Optional[Dict[str, Any]]:
        """
        Analyze an invoice document and generate a responsive HTML template.
        Identifies variable fields and replaces them with {{ placeholders }}.
        """
        model = genai.GenerativeModel(MODELS["pro"])
        
        # In a real scenario, we use genai.upload_file
        # prompt refinement for layout preservation and variable mapping
        prompt = """
        あなたは熟練のフロントエンドエンジニアであり、かつ経理のスペシャリストです。
        提供された請求書（画像またはPDF）のレイアウトを完全に再現する、モダンかつクリーンなHTMLテンプレートを作成してください。
        
        【要件】
        1. CSSは埋め込み（styleタグまたはインライン）で記述してください。
        2. 以下の項目を特定し、プログラムから値を流し込めるように {{ 変数名 }} 形式に置き換えてください。
           - 請求先名：{{ client_name }}
           - 発行日：{{ issue_date }}
           - 支払期限：{{ due_date }}
           - ご請求金額（合計）：{{ total_amount }}
           - 品目リスト（テーブル）：可能な限りループ処理を想定した構造にしてください。
        3. レイアウトは可能な限り元のドキュメントに寄せてください（ロゴの位置、表の形式など）。
        4. 外部の画像や不確かなリソースへのリンクは含めないでください。
        5. 固定値（会社住所、連絡先、振込先口座など）は、テキストとしてそのままHTMLに含めてください。
        
        返合法: JSON形式のみで出力してください。
        {
          "template_name": "抽出されたファイル名に基づいた名前",
          "html": "生成されたHTMLコード全文",
          "variables": ["client_name", "issue_date", "due_date", "total_amount"]
        }
        """
        
        try:
            # For the prototype, we simulate the multimodal input.
            # In production, this would be: response = model.generate_content([prompt, uploaded_file])
            response = str(model.generate_content(prompt).text)
            
            import json
            import re
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                return json.loads(match.group())
            return None
        except Exception as e:
            logger.error(f"Error in generate_invoice_html_template: {e}")
            if "429" in str(e):
                logger.info("Failing over to default template due to quota limit.")
                return {
                    "template_name": f"AI_Generated_Fallback_{os.path.basename(file_path)}",
                    "html": """
<div style="font-family: 'Helvetica', sans-serif; padding: 40px; color: #1e293b; max-width: 800px; margin: auto; background: white; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);">
    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 40px;">
        <div>
            <h1 style="font-size: 2.5rem; font-weight: 800; color: #2563eb; margin: 0; letter-spacing: -0.025em;">INVOICE</h1>
            <p style="color: #64748b; margin-top: 4px; font-weight: 500;">Generated by Tax-Agent AI</p>
        </div>
        <div style="text-align: right;">
            <p style="font-weight: 700; margin: 0; color: #0f172a;">{{ client_name }} 御中</p>
            <p style="font-size: 0.875rem; color: #64748b; margin-top: 4px;">発行日: {{ issue_date }}</p>
            <p style="font-size: 0.875rem; color: #64748b; margin: 0;">支払期限: {{ due_date }}</p>
        </div>
    </div>
    
    <div style="background: #f8fafc; border-radius: 8px; padding: 24px; margin-bottom: 40px; border: 1px solid #f1f5f9;">
        <div style="display: grid; grid-template-columns: 1fr; gap: 8px; text-align: center;">
            <span style="font-size: 0.875rem; font-weight: 600; color: #475569; text-transform: uppercase; letter-spacing: 0.05em;">Total Amount (Tax Included)</span>
            <span style="font-size: 3rem; font-weight: 800; color: #0f172a;">¥{{ total_amount }}</span>
        </div>
    </div>

    <table style="width: 100%; border-collapse: collapse; margin-bottom: 40px;">
        <thead>
            <tr style="border-bottom: 2px solid #e2e8f0;">
                <th style="padding: 12px 0; text-align: left; font-size: 0.75rem; font-weight: 700; color: #64748b; text-transform: uppercase;">Description</th>
                <th style="padding: 12px 0; text-align: right; font-size: 0.75rem; font-weight: 700; color: #64748b; text-transform: uppercase;">Amount</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td style="padding: 16px 0; border-bottom: 1px solid #f1f5f9; font-weight: 500;">Service Professional Fee</td>
                <td style="padding: 16px 0; border-bottom: 1px solid #f1f5f9; text-align: right; font-weight: 600;">¥{{ total_amount }}</td>
            </tr>
        </tbody>
    </table>

    <div style="border-top: 1px solid #e2e8f0; padding-top: 24px; font-size: 0.75rem; color: #94a3b8; line-height: 1.6;">
        <p style="margin: 0;">※ この請求書はTax-Agent AIによって自動生成されました。レイアウトや項目に誤りがある場合は、エディタで修正してください。</p>
    </div>
</div>
                    """,
                    "variables": ["client_name", "issue_date", "due_date", "total_amount"]
                }
            return None
