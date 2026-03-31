"""
Tests for journal_rule_service.apply_journal_rules

Usage:
    cd backend
    pytest tests/test_journal_rule_service.py -v
"""
import pytest
import pytest_asyncio
from datetime import datetime
from bson import ObjectId

from app.db.mongodb import get_database
from app.services.journal_rule_service import apply_journal_rules


CORP_ID = "test_corp_journal_rule_service"


def _rule(keyword, target_field, account_subject, is_active=True):
    return {
        "_id": ObjectId(),
        "corporate_id": CORP_ID,
        "name": f"テストルール({keyword})",
        "keyword": keyword,
        "target_field": target_field,
        "account_subject": account_subject,
        "tax_division": "課税仕入 10%",
        "is_active": is_active,
        "created_at": datetime.utcnow(),
    }


@pytest_asyncio.fixture(autouse=True)
async def clean_journal_rules():
    """各テスト前後に journal_rules をクリーンアップ"""
    db = get_database()
    await db["journal_rules"].delete_many({"corporate_id": CORP_ID})
    yield
    await db["journal_rules"].delete_many({"corporate_id": CORP_ID})


# ── テストケース ──────────────────────────────────────────────


async def test_keyword_partial_match_overwrites_category():
    """品目・摘要の部分一致でcategoryが上書きされること"""
    db = get_database()
    rule = _rule("タクシー", "品目・摘要", "旅費交通費")
    await db["journal_rules"].insert_one(rule)

    receipts = [{"payee": "帝都タクシー", "category": "交通費", "line_items": []}]
    result = await apply_journal_rules(db, CORP_ID, receipts)

    assert result[0]["category"] == "旅費交通費"
    assert result[0]["applied_journal_rule_id"] == str(rule["_id"])


async def test_inactive_rule_is_not_applied():
    """is_active=False のルールは適用されないこと"""
    db = get_database()
    rule = _rule("Amazon", "品目・摘要", "消耗品費", is_active=False)
    await db["journal_rules"].insert_one(rule)

    receipts = [{"payee": "Amazon Japan", "category": "雑費", "line_items": []}]
    result = await apply_journal_rules(db, CORP_ID, receipts)

    assert result[0]["category"] == "雑費"
    assert "applied_journal_rule_id" not in result[0]


async def test_first_matching_rule_takes_priority():
    """複数ルールが一致した場合は最初に一致したルール（created_at昇順）が優先されること"""
    db = get_database()
    rule_first = _rule("Slack", "品目・摘要", "通信費")
    rule_first["created_at"] = datetime(2024, 1, 1)
    rule_second = _rule("Slack", "品目・摘要", "広告宣伝費")
    rule_second["created_at"] = datetime(2024, 1, 2)
    await db["journal_rules"].insert_many([rule_first, rule_second])

    receipts = [{"payee": "Slack Technologies", "category": "雑費", "line_items": []}]
    result = await apply_journal_rules(db, CORP_ID, receipts)

    assert result[0]["category"] == "通信費"
    assert result[0]["applied_journal_rule_id"] == str(rule_first["_id"])


async def test_no_match_leaves_category_unchanged():
    """一致するルールがない場合はcategoryが変わらないこと"""
    db = get_database()
    rule = _rule("AMAZON", "品目・摘要", "消耗品費")
    await db["journal_rules"].insert_one(rule)

    receipts = [{"payee": "コンビニ", "category": "会議費", "line_items": []}]
    result = await apply_journal_rules(db, CORP_ID, receipts)

    assert result[0]["category"] == "会議費"
    assert "applied_journal_rule_id" not in result[0]


async def test_line_items_description_partial_match():
    """line_items の description に部分一致した場合もcategoryが上書きされること"""
    db = get_database()
    rule = _rule("書籍", "品目・摘要", "新聞図書費")
    await db["journal_rules"].insert_one(rule)

    receipts = [{
        "payee": "オンラインショップ",
        "category": "雑費",
        "line_items": [{"description": "Python書籍購入", "amount": 3000}],
    }]
    result = await apply_journal_rules(db, CORP_ID, receipts)

    assert result[0]["category"] == "新聞図書費"


async def test_vendor_name_field_partial_match():
    """取引先名フィールドで payee に部分一致すること"""
    db = get_database()
    rule = _rule("東京電力", "取引先名", "水道光熱費")
    await db["journal_rules"].insert_one(rule)

    receipts = [{"payee": "東京電力ホールディングス", "category": "雑費", "line_items": []}]
    result = await apply_journal_rules(db, CORP_ID, receipts)

    assert result[0]["category"] == "水道光熱費"


async def test_account_subject_field_exact_match():
    """勘定科目フィールドで category に完全一致すること"""
    db = get_database()
    rule = _rule("雑費", "勘定科目", "消耗品費")
    await db["journal_rules"].insert_one(rule)

    receipts_match = [{"payee": "なんでも屋", "category": "雑費", "line_items": []}]
    receipts_no_match = [{"payee": "なんでも屋", "category": "雑費（その他）", "line_items": []}]

    result_match = await apply_journal_rules(db, CORP_ID, receipts_match)
    result_no_match = await apply_journal_rules(db, CORP_ID, receipts_no_match)

    assert result_match[0]["category"] == "消耗品費"
    assert result_no_match[0]["category"] == "雑費（その他）"


async def test_empty_receipts_returns_empty():
    """空リストを渡した場合は空リストが返ること"""
    db = get_database()
    result = await apply_journal_rules(db, CORP_ID, [])
    assert result == []


# ── 請求書（doc_type="invoice"）のテスト ──────────────────────


async def test_invoice_client_name_match_overwrites_line_items_category():
    """doc_type=invoice: client_name でマッチした場合に line_items[].category が上書きされること"""
    db = get_database()
    rule = _rule("アルダグラム", "取引先名", "ソフトウェア使用料")
    await db["journal_rules"].insert_one(rule)

    invoice = {
        "client_name": "株式会社アルダグラム",
        "line_items": [
            {"description": "KANNA利用料", "category": "支払手数料", "amount": 10000},
            {"description": "オプション費用", "category": "支払手数料", "amount": 2000},
        ],
    }
    result = await apply_journal_rules(db, CORP_ID, [invoice], doc_type="invoice")

    assert result[0]["line_items"][0]["category"] == "ソフトウェア使用料"
    assert result[0]["line_items"][1]["category"] == "ソフトウェア使用料"
    assert result[0]["applied_journal_rule_id"] == str(rule["_id"])


async def test_invoice_line_item_description_match():
    """doc_type=invoice: line_items[].description でマッチした場合に上書きされること"""
    db = get_database()
    rule = _rule("工事", "品目・摘要", "修繕費")
    await db["journal_rules"].insert_one(rule)

    invoice = {
        "client_name": "株式会社エースリメイク",
        "line_items": [
            {"description": "コーキング打替工事", "category": "外注費", "amount": 260000},
        ],
    }
    result = await apply_journal_rules(db, CORP_ID, [invoice], doc_type="invoice")

    assert result[0]["line_items"][0]["category"] == "修繕費"


async def test_invoice_no_match_leaves_line_items_unchanged():
    """doc_type=invoice: マッチしない場合は line_items[].category が変わらないこと"""
    db = get_database()
    rule = _rule("Amazon", "品目・摘要", "消耗品費")
    await db["journal_rules"].insert_one(rule)

    invoice = {
        "client_name": "株式会社Speee",
        "line_items": [
            {"description": "紹介料", "category": "外注費", "amount": 396000},
        ],
    }
    result = await apply_journal_rules(db, CORP_ID, [invoice], doc_type="invoice")

    assert result[0]["line_items"][0]["category"] == "外注費"
    assert "applied_journal_rule_id" not in result[0]


async def test_receipt_doc_type_default_unchanged():
    """doc_type 省略時（デフォルト=receipt）の既存動作が壊れていないこと"""
    db = get_database()
    rule = _rule("タクシー", "品目・摘要", "旅費交通費")
    await db["journal_rules"].insert_one(rule)

    receipts = [{"payee": "帝都タクシー", "category": "交通費", "line_items": []}]
    result = await apply_journal_rules(db, CORP_ID, receipts)  # doc_type 省略

    assert result[0]["category"] == "旅費交通費"
    assert "line_items" in result[0]  # line_items が消えていないこと
