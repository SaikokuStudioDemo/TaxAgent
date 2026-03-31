"""
Journal Rule Service
Applies journal_rules to receipts/invoices and overwrites the category (account_subject).
"""
from typing import Any


async def apply_journal_rules(
    db: Any,
    corporate_id: str,
    documents: list[dict],
    doc_type: str = "receipt",
) -> list[dict]:
    """
    journal_rules コレクションを参照し、各ドキュメントの category を上書きする。

    doc_type:
    - "receipt" : payee フィールドを取引先として扱い、category（ドキュメント直下）を上書き
    - "invoice" : client_name フィールドを取引先として扱い、line_items[].category を全て上書き

    マッチングロジック:
    - target_field が "品目・摘要" or "摘要"
        → 取引先名 または line_items[].description に対して keyword の部分一致
    - target_field が "取引先名"
        → 取引先名 に対して keyword の部分一致
    - target_field が "勘定科目"
        → category に対して keyword の完全一致（receipt のみ有効）
    - is_active=True のルールのみ適用
    - 複数一致した場合は最初に一致したルール（created_at 昇順）を優先
    """
    if not documents:
        return documents

    cursor = db["journal_rules"].find({
        "corporate_id": corporate_id,
        "is_active": True,
    }).sort("created_at", 1)
    rules = await cursor.to_list(length=500)

    if not rules:
        return documents

    result = []
    for doc in documents:
        matched_rule = None
        for rule in rules:
            if _matches(rule, doc, doc_type):
                matched_rule = rule
                break

        if matched_rule:
            doc = dict(doc)
            if doc_type == "receipt":
                doc["category"] = matched_rule["account_subject"]
            else:
                doc["line_items"] = [
                    {**item, "category": matched_rule["account_subject"]}
                    for item in doc.get("line_items", [])
                ]
            doc["applied_journal_rule_id"] = str(matched_rule["_id"])

        result.append(doc)

    return result


def _matches(rule: dict, doc: dict, doc_type: str = "receipt") -> bool:
    keyword = rule.get("keyword", "")
    target_field = rule.get("target_field", "")

    if not keyword:
        return False

    keyword_lower = keyword.lower()
    base_text = (doc.get("payee") if doc_type == "receipt" else doc.get("client_name")) or ""

    # 品目・摘要 or 摘要 → 取引先名 + line_items description (部分一致)
    if target_field in ("品目・摘要", "摘要"):
        if keyword_lower in base_text.lower():
            return True
        for item in doc.get("line_items", []):
            if keyword_lower in (item.get("description") or "").lower():
                return True
        return False

    # 取引先名 → 取引先名 (部分一致)
    if target_field == "取引先名":
        return keyword_lower in base_text.lower()

    # 勘定科目 → category (完全一致、receipt のみ)
    if target_field == "勘定科目":
        category = (doc.get("category") or "")
        return keyword == category

    # フォールバック: 取引先名に部分一致
    return keyword_lower in base_text.lower()
