"""
Journal Rule Service
Applies journal_rules to receipts/invoices and overwrites the category (account_subject).
Priority: corporate rules > tax firm rules > Admin journal map
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from bson import ObjectId


async def _load_journal_map(db: Any) -> Dict[str, Any]:
    """system_settings から勘定科目マスターを取得する。未設定時は journal_map.json にフォールバック。"""
    setting = await db["system_settings"].find_one({"key": "journal_map"})
    if setting and setting.get("value"):
        return setting["value"]
    json_path = Path(__file__).parent.parent / "data" / "journal_map.json"
    with open(json_path) as f:
        return json.load(f)


async def apply_journal_rules(
    db: Any,
    corporate_id: str,
    documents: List[Dict[str, Any]],
    doc_type: str = "receipt",
) -> List[Dict[str, Any]]:
    """
    仕訳ルールを適用する。優先順位：配下法人ルール > 税理士法人ルール > Admin標準マスター

    doc_type:
    - "receipt" : payee フィールドを取引先として扱い、category を上書き
    - "invoice" : client_name フィールドを取引先として扱い、line_items[].category を全て上書き
    """
    if not documents:
        return documents

    # 1. 配下法人ルールを取得
    corporate_rules: List[Dict[str, Any]] = await db["journal_rules"].find(
        {"corporate_id": corporate_id, "is_active": True}
    ).sort("created_at", 1).to_list(length=500)

    # 2. 税理士法人ルールを取得（フォールバック用）
    tax_firm_rules: List[Dict[str, Any]] = []
    try:
        corporate = await db["corporates"].find_one({"_id": ObjectId(corporate_id)})
        if corporate and corporate.get("advising_tax_firm_id"):
            tax_firm = await db["corporates"].find_one(
                {"firebase_uid": corporate["advising_tax_firm_id"]}
            )
            if tax_firm:
                tax_firm_rules = await db["journal_rules"].find(
                    {"corporate_id": str(tax_firm["_id"]), "is_active": True}
                ).sort("created_at", 1).to_list(length=500)
    except Exception:
        pass

    # 3. Admin標準マスターを取得（最終フォールバック）
    journal_map = await _load_journal_map(db)

    results: List[Dict[str, Any]] = []
    for doc in documents:
        matched = _apply_rules(corporate_rules, doc, doc_type)
        if matched is None:
            matched = _apply_rules(tax_firm_rules, doc, doc_type)
        if matched is None:
            matched = _apply_journal_map(journal_map, doc, doc_type)
        results.append(matched if matched is not None else doc)

    return results


def _apply_rules(
    rules: List[Dict[str, Any]],
    doc: Dict[str, Any],
    doc_type: str,
) -> Optional[Dict[str, Any]]:
    """ルール一覧に対してドキュメントをマッチングし、一致すれば category を上書きしたコピーを返す。"""
    for rule in rules:
        if _matches(rule, doc, doc_type):
            result = dict(doc)
            if doc_type == "receipt":
                result["category"] = rule["account_subject"]
            else:
                result["line_items"] = [
                    {**item, "category": rule["account_subject"]}
                    for item in doc.get("line_items", [])
                ]
            result["applied_journal_rule_id"] = str(rule["_id"])
            return result
    return None


def _apply_journal_map(
    journal_map: Dict[str, Any],
    doc: Dict[str, Any],
    doc_type: str,
) -> Optional[Dict[str, Any]]:
    """Admin標準マスターのキーワードに対してマッチングし、一致すれば category を上書きしたコピーを返す。"""
    base_text = (doc.get("payee") if doc_type == "receipt" else doc.get("client_name")) or ""
    descriptions = [(item.get("description") or "") for item in doc.get("line_items", [])]

    for subject_name, entry in journal_map.items():
        for kw in entry.get("keywords", []):
            kw_lower = kw.lower()
            if kw_lower in base_text.lower():
                return _make_journal_map_result(doc, doc_type, subject_name)
            for desc in descriptions:
                if kw_lower in desc.lower():
                    return _make_journal_map_result(doc, doc_type, subject_name)
    return None


def _make_journal_map_result(doc: Dict[str, Any], doc_type: str, subject_name: str) -> Dict[str, Any]:
    result = dict(doc)
    if doc_type == "receipt":
        result["category"] = subject_name
    else:
        result["line_items"] = [
            {**item, "category": subject_name}
            for item in doc.get("line_items", [])
        ]
    result["applied_journal_map_subject"] = subject_name
    return result


def _matches(rule: Dict[str, Any], doc: Dict[str, Any], doc_type: str = "receipt") -> bool:
    keyword = rule.get("keyword", "")
    target_field = rule.get("target_field", "")

    if not keyword:
        return False

    keyword_lower = keyword.lower()
    base_text = (doc.get("payee") if doc_type == "receipt" else doc.get("client_name")) or ""

    if target_field in ("品目・摘要", "摘要"):
        if keyword_lower in base_text.lower():
            return True
        for item in doc.get("line_items", []):
            if keyword_lower in (item.get("description") or "").lower():
                return True
        return False

    if target_field == "取引先名":
        return keyword_lower in base_text.lower()

    if target_field == "勘定科目":
        return keyword == (doc.get("category") or "")

    return keyword_lower in base_text.lower()
