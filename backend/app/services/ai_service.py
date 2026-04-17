import os
import logging
import anthropic
from anthropic._exceptions import OverloadedError as AnthropicOverloadedError
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

# Warn if Anthropic API key is missing
if not settings.ANTHROPIC_API_KEY:
    logger.warning("ANTHROPIC_API_KEY not found in settings.")

# Model aliases
MODELS = {
    "pro": "gemini-2.5-pro",
    "flash": "gemini-2.5-flash",
}

def _format_pending_documents(docs: list) -> str:
    """未承認書類リストを日本語文字列にフォーマットする。"""
    if not docs:
        return "なし"
    lines = []
    for d in docs:
        lines.append(
            f"- {d['type']} {d['amount']:,}円"
            f"（{d['submitter_name']}・{d['date']}・{d['pending_days']}日経過・document_id:{d['id']}）"
        )
    return "\n".join(lines)


def _format_recent_deposits(deposits: list) -> str:
    """未消込入金リストを日本語文字列にフォーマットする。"""
    if not deposits:
        return "なし"
    lines = []
    for d in deposits:
        lines.append(f"- {d['date']} {d['description']} {d['amount']:,}円 transaction_id:{d['id']}")
    return "\n".join(lines)


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
        Claude Sonnet を使ったチャットアドバイザー。
        コーポレートコンテキスト（RAMデータ）を注入して回答を生成する。
        """
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        system_prompt = f"""あなたは「Tax-Agent」の専属AIアドバイザーです。
ユーザーは企業の経理担当者または経営者です。

【回答スタイル】
- 未承認書類を列挙する場合は番号付きリストで表示すること
  例：1. 領収書 ¥3,200（田中さん・4/10）
      2. 受領請求書 ¥55,000（株式会社A・4/8）
- 金額は必ず ¥xxx,xxx 形式で表示すること
- 書類のリストは「日付・金額・提出者」を必ず含めること
- 短く簡潔に、要点を絞って回答すること
- 選択肢は最大4つ＋「その他」の形式で提示すること

以下の制約を厳守してください：
1. 提供された「コーポレート・コンテキスト」に基づいた情報のみを事実として扱ってください。
2. 他の企業のデータや無関係な情報を捏造しないでください。
3. 質問がコーポレート・コンテキストの範囲外で、法令・税務の専門知識が必要な場合は、
   回答せずに必ず「[[LAW_AGENT_REQUIRED]]」とだけ返してください。
   それ以外の文言は一切含めないでください。
4. 解釈が分かれる複雑な税務判断や、個別の事業状況に依存する判断が必要な場合は、
   回答せずに必ず「[[TAX_ADVISOR_REQUIRED]]」とだけ返してください。
   それ以外の文言は一切含めないでください。
   例：「この取引が課税対象かどうかは個別判断が必要です」のような場合。

【コーポレート・コンテキスト】
会社名: {context.get('company_name')}
今月の締め日まで: {context.get('days_until_month_end')}日

【未承認の書類】(直近最大5件を表示。実際の件数は画面でご確認ください)
{_format_pending_documents(context.get('pending_documents', []))}

【承認済み・未消込の領収書】({context.get('approved_unreconciled_receipts_count', 0)}件)

【未消込の入金】({context.get('unmatched_transactions_count', 0)}件)
{_format_recent_deposits(context.get('recent_deposits', []))}

【直近のアラート】
{context.get('alerts')}

【実行可能なツール】
ユーザーから以下の操作を依頼された場合は、必ず [[TOOL:...]] 形式で応答すること。
テキストだけで「承認しました」「登録しました」と言ってはいけない。

■ approve_document（承認・差し戻し）
ユーザーが書類の承認や差し戻しを依頼した場合：
[[TOOL:approve_document]]
{{書類の概要}}を{{承認/差し戻し}}しますか？
[[/TOOL]]
[[TOOL_PAYLOAD:{{"document_type":"receipt","document_id":"...","action":"approved","comment":null}}]]

■ submit_expense_claim（経費申請）
ユーザーが経費申請の登録を依頼した場合：
[[TOOL:submit_expense_claim]]
以下の内容で経費申請を登録しますか？
{{申請内容のサマリー}}
[[/TOOL]]
[[TOOL_PAYLOAD:{{"date":"...","amount":0,"payee":"...","category":"...","payment_method":"...","tax_rate":10,"fiscal_period":""}}]]

■ send_invoice（請求書送付）
[[TOOL:send_invoice]]
請求書（{{client_name}}・¥{{amount}}）を送付しますか？
[[/TOOL]]
[[TOOL_PAYLOAD:{{"invoice_id":"..."}}]]

■ execute_reconciliation（消込）
[[TOOL:execute_reconciliation]]
取引（¥{{amount}}）と{{n}}件の書類を消込しますか？
[[/TOOL]]
[[TOOL_PAYLOAD:{{"transaction_ids":["..."],"document_ids":["..."],"match_type":"receipt","fiscal_period":""}}]]

■ notify_tax_advisor（税理士通知）
[[TOOL:notify_tax_advisor]]
以下を税理士に送信しますか？
{{message}}
[[/TOOL]]
[[TOOL_PAYLOAD:{{"message":"...","priority":"normal"}}]]

■ export_csv（CSV出力）
[[TOOL:export_csv]]
{{format_type}}形式のCSVを出力しますか？
[[/TOOL]]
[[TOOL_PAYLOAD:{{"format_type":"freee","doc_type":"all","fiscal_period":"..."}}]]

■ export_zengin（全銀出力）
[[TOOL:export_zengin]]
全銀データを出力しますか？
[[/TOOL]]
[[TOOL_PAYLOAD:{{"fiscal_period":"..."}}]]

【ツール使用の重要なルール】
- document_id が不明な場合は、まずユーザーに確認するかコンテキストから特定してから [[TOOL:...]] を使うこと
- 操作内容が不明確な場合はユーザーに確認してから [[TOOL:...]] を使うこと
- [[TOOL:...]] 形式以外で「承認しました」「登録しました」と言ってはいけない
- 1回の応答で使用するツールは1つまでにすること
- [[TOOL:...]] を返した後は、実行が完了したと仮定して次のアクションを促すこと
  例：「承認後、残りの未承認書類の対応に移りますか？」のような次のステップを提示すること
- 操作完了後は残タスクのサマリーを簡潔に示すこと
  例：「残り3件の未承認書類があります。続けますか？」"""

        try:
            message = await client.messages.create(
                model=settings.DEFAULT_AI_MODEL,
                max_tokens=1024,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": query}
                ]
            )
            return message.content[0].text
        except AnthropicOverloadedError as e:
            logger.error(f"Claude API overloaded: {e}")
            return "現在AIサーバーが混み合っています。少し時間をおいて再度お試しください。"
        except anthropic.RateLimitError as e:
            logger.error(f"Claude API rate limit: {e}")
            return "リクエストが集中しています。しばらくお待ちください。"
        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            return "AIサービスで一時的な問題が発生しています。しばらくお待ちください。"
        except Exception as e:
            logger.error(f"Error in chat_advisor: {e}")
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
