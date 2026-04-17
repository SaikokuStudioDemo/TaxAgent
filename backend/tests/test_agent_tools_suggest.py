"""
Tests for Task#17-B: AI エージェント 提案系ツール（agent_tools.py 追加4本）

Usage:
    cd backend
    pytest tests/test_agent_tools_suggest.py -v
"""
import pytest
from datetime import datetime, timedelta, date
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

# ── テスト用 corporate_id ─────────────────────────────────────────────────────
CORP_ID = str(ObjectId())
USER_ID = str(ObjectId())
CLIENT_ID = str(ObjectId())


# ── モックヘルパー ─────────────────────────────────────────────────────────────

def make_cursor(return_value: list):
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.limit = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=return_value)
    return cursor


def make_col(find_one=None, find_data=None, count=0):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one)
    col.count_documents = AsyncMock(return_value=count)
    col.insert_one = AsyncMock(return_value=MagicMock())
    col.update_one = AsyncMock(return_value=MagicMock())
    col.find = MagicMock(return_value=make_cursor(find_data or []))
    return col


def build_mock_db(collections: dict):
    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda k: collections.get(k, make_col()))
    return db


# ═══════════════════════════════════════════════════════════════════════════
# journal_map.json のロード確認
# ═══════════════════════════════════════════════════════════════════════════

def test_journal_map_loads_correctly():
    """journal_map.json が正しくロードされ 16 カテゴリが含まれること"""
    from app.services.agent_tools import JOURNAL_MAP

    assert isinstance(JOURNAL_MAP, dict)
    assert len(JOURNAL_MAP) == 16

    required_categories = [
        "旅費交通費", "会議費", "消耗品費", "交際費", "通信費",
        "水道光熱費", "地代家賃", "広告宣伝費", "支払手数料", "外注費",
        "福利厚生費", "新聞図書費", "車両費", "保険料", "修繕費", "雑費",
    ]
    for cat in required_categories:
        assert cat in JOURNAL_MAP, f"カテゴリ '{cat}' が journal_map.json に存在しない"

    # 各エントリに必須フィールドが含まれること
    for name, entry in JOURNAL_MAP.items():
        assert "debit" in entry, f"{name}: debit が欠けている"
        assert "credit" in entry, f"{name}: credit が欠けている"
        assert "tax_category" in entry, f"{name}: tax_category が欠けている"
        assert "keywords" in entry, f"{name}: keywords が欠けている"
        assert isinstance(entry["keywords"], list), f"{name}: keywords がリストでない"


# ═══════════════════════════════════════════════════════════════════════════
# suggest_journal_entry のテスト
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_suggest_journal_entry_rule_matched():
    """journal_rules に一致するルールがある場合に confidence='rule_matched' が返ること"""
    from app.services.agent_tools import suggest_journal_entry

    doc_id = ObjectId()
    receipt = {
        "_id": doc_id,
        "corporate_id": CORP_ID,
        "amount": 5000,
        "payee": "新橋タクシー",
        "description": "タクシー代",
        "category": "",
    }
    rule = {
        "_id": ObjectId(),
        "corporate_id": CORP_ID,
        "keyword": "タクシー",
        "target_field": "description",
        "account_subject": "旅費交通費",
        "tax_division": "課税仕入 10%",
        "is_active": True,
    }

    db = build_mock_db({
        "receipts": make_col(find_one=receipt),
        "journal_rules": make_col(find_data=[rule]),
    })

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await suggest_journal_entry(CORP_ID, "receipt", str(doc_id))

    assert result["confidence"] == "rule_matched"
    assert result["suggested_debit"] == "旅費交通費"
    assert result["suggested_credit"] == "未払金"
    assert result["suggested_tax_category"] == "課税仕入 10%"
    assert result["source_rule_id"] is not None


@pytest.mark.asyncio
async def test_suggest_journal_entry_category_matched():
    """journal_rules がなく category='旅費交通費' の場合に confidence='category_matched' が返ること"""
    from app.services.agent_tools import suggest_journal_entry

    doc_id = ObjectId()
    receipt = {
        "_id": doc_id,
        "corporate_id": CORP_ID,
        "amount": 3000,
        "payee": "テスト店",
        "description": "交通費",
        "category": "旅費交通費",   # ← JOURNAL_MAP のキーと一致
    }

    db = build_mock_db({
        "receipts": make_col(find_one=receipt),
        "journal_rules": make_col(find_data=[]),  # ルールなし
    })

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await suggest_journal_entry(CORP_ID, "receipt", str(doc_id))

    assert result["confidence"] == "category_matched"
    assert result["suggested_debit"] == "旅費交通費"
    assert result["source_rule_id"] is None


@pytest.mark.asyncio
async def test_suggest_journal_entry_keyword_matched():
    """category=None で description に 'タクシー' が含まれる場合に '旅費交通費' が推測されること"""
    from app.services.agent_tools import suggest_journal_entry

    doc_id = ObjectId()
    receipt = {
        "_id": doc_id,
        "corporate_id": CORP_ID,
        "amount": 2000,
        "payee": "タクシー代",
        "description": "タクシー代（客先訪問）",
        "category": "",   # ← category なし
    }

    db = build_mock_db({
        "receipts": make_col(find_one=receipt),
        "journal_rules": make_col(find_data=[]),
    })

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await suggest_journal_entry(CORP_ID, "receipt", str(doc_id))

    assert result["confidence"] == "category_matched"
    assert result["suggested_debit"] == "旅費交通費"


@pytest.mark.asyncio
async def test_suggest_journal_entry_default_fallback():
    """category・description ともにマッチしない場合に confidence='default' + '雑費' が返ること"""
    from app.services.agent_tools import suggest_journal_entry

    doc_id = ObjectId()
    receipt = {
        "_id": doc_id,
        "corporate_id": CORP_ID,
        "amount": 500,
        "payee": "不明な店",
        "description": "xyzxyz",   # どのキーワードにもマッチしない
        "category": "",
    }

    db = build_mock_db({
        "receipts": make_col(find_one=receipt),
        "journal_rules": make_col(find_data=[]),
    })

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await suggest_journal_entry(CORP_ID, "receipt", str(doc_id))

    assert result["confidence"] == "default"
    assert result["suggested_debit"] == "雑費"
    assert result["source_rule_id"] is None


# ═══════════════════════════════════════════════════════════════════════════
# suggest_reconciliation のテスト
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_suggest_reconciliation_finds_candidates():
    """金額・日付が一致する領収書がある場合に candidates に含まれること"""
    from app.services.agent_tools import suggest_reconciliation

    tx_id = ObjectId()
    tx = {
        "_id": tx_id,
        "corporate_id": CORP_ID,
        "deposit_amount": 10000,
        "transaction_date": "2024-01-15",
        "description": "テスト振込",
    }

    matching_receipt = {
        "_id": ObjectId(),
        "corporate_id": CORP_ID,
        "amount": 10000,        # 金額一致 → score += 40
        "date": "2024-01-15",   # 日付一致 → score += 30  (合計70 ≥ 60)
        "payee": "テスト株式会社",
        "approval_status": "approved",
        "reconciliation_status": "unreconciled",
    }

    db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(find_data=[matching_receipt]),
        "invoices": make_col(find_data=[]),
    })

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await suggest_reconciliation(CORP_ID, str(tx_id))

    assert "error" not in result
    assert len(result["candidates"]) >= 1
    assert result["candidates"][0]["document_type"] == "receipt"
    assert result["candidates"][0]["score"] >= 60
    assert result["candidates"][0]["difference"] == 0  # 金額完全一致


@pytest.mark.asyncio
async def test_suggest_reconciliation_no_match():
    """一致するドキュメントが 0 件の場合に candidates が空リストで返ること"""
    from app.services.agent_tools import suggest_reconciliation

    tx_id = ObjectId()
    tx = {
        "_id": tx_id,
        "corporate_id": CORP_ID,
        "deposit_amount": 99999,   # 大幅に金額が異なる → is_candidate=False
        "transaction_date": "2024-01-15",
        "description": "テスト振込",
    }

    receipt_different_amount = {
        "_id": ObjectId(),
        "corporate_id": CORP_ID,
        "amount": 1000,    # 差額 98999円 → score=0 → is_candidate=False
        "date": "2024-01-15",
        "payee": "テスト",
        "approval_status": "approved",
    }

    db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(find_data=[receipt_different_amount]),
        "invoices": make_col(find_data=[]),
    })

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await suggest_reconciliation(CORP_ID, str(tx_id))

    assert "error" not in result
    assert result["candidates"] == []


# ═══════════════════════════════════════════════════════════════════════════
# draft_expense_claim のテスト
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_draft_expense_claim_no_db_write():
    """draft_expense_claim 呼び出し後に receipts コレクションが変更されていないこと"""
    from app.services.agent_tools import draft_expense_claim

    receipts_mock = make_col()
    db = build_mock_db({"receipts": receipts_mock})

    # get_database を mock しても呼ばれないはず（DB 不使用）
    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await draft_expense_claim(
            CORP_ID, USER_ID, 5000, "タクシー代", "2024-01-15"
        )

    # insert_one が呼ばれていないこと
    receipts_mock.insert_one.assert_not_called()
    assert "draft" in result


@pytest.mark.asyncio
async def test_draft_expense_claim_category_inference():
    """description に 'タクシー' を含む場合に category='旅費交通費' と推測されること"""
    from app.services.agent_tools import draft_expense_claim

    result = await draft_expense_claim(
        CORP_ID, USER_ID,
        amount=3000,
        description="タクシー代（得意先往訪）",
        date_str="2024-01-20",
        category=None,   # ← 未指定
    )

    assert "error" not in result
    assert result["draft"]["category"] == "旅費交通費"
    assert result["suggested_journal"]["suggested_debit"] == "旅費交通費"
    assert result["suggested_journal"]["confidence"] == "category_matched"


# ═══════════════════════════════════════════════════════════════════════════
# draft_invoice のテスト
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_draft_invoice_valid_client():
    """存在する client_id で正しい下書きが返ること・total_amount が正確なこと"""
    from app.services.agent_tools import draft_invoice

    client = {
        "_id": ObjectId(CLIENT_ID),
        "corporate_id": CORP_ID,
        "name": "テスト取引先株式会社",
    }

    db = build_mock_db({"clients": make_col(find_one=client)})

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await draft_invoice(
            CORP_ID, USER_ID,
            client_id=CLIENT_ID,
            amount=100000,
            description="コンサルティング料",
            tax_rate=10,
        )

    assert "error" not in result
    draft = result["draft"]
    assert draft["client_name"] == "テスト取引先株式会社"
    assert draft["tax_amount"] == 10000         # 100000 * 10%
    assert draft["total_amount"] == 110000       # amount + tax_amount
    assert draft["delivery_status"] == "unsent"


@pytest.mark.asyncio
async def test_draft_invoice_client_not_found():
    """存在しない client_id で {'error': '取引先が見つかりません'} が返ること"""
    from app.services.agent_tools import draft_invoice

    db = build_mock_db({"clients": make_col(find_one=None)})  # find_one = None

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await draft_invoice(
            CORP_ID, USER_ID,
            client_id=CLIENT_ID,
            amount=50000,
            description="テスト",
        )

    assert result == {"error": "取引先が見つかりません"}


@pytest.mark.asyncio
async def test_draft_invoice_default_due_date():
    """due_date=None の場合に today+30日が設定されること"""
    from app.services.agent_tools import draft_invoice

    client = {"_id": ObjectId(CLIENT_ID), "corporate_id": CORP_ID, "name": "テスト"}
    db = build_mock_db({"clients": make_col(find_one=client)})

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await draft_invoice(
            CORP_ID, USER_ID,
            client_id=CLIENT_ID,
            amount=30000,
            description="テスト",
            due_date=None,
        )

    assert "error" not in result
    expected_due = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
    assert result["draft"]["due_date"] == expected_due


# ═══════════════════════════════════════════════════════════════════════════
# confirmation_required の確認
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_confirmation_required_is_true():
    """draft_expense_claim・draft_invoice の両方で confirmation_required=True であること"""
    from app.services.agent_tools import draft_expense_claim, draft_invoice

    # draft_expense_claim
    claim_result = await draft_expense_claim(
        CORP_ID, USER_ID, 1000, "テスト", "2024-01-01"
    )
    assert claim_result.get("confirmation_required") is True

    # draft_invoice
    client = {"_id": ObjectId(CLIENT_ID), "corporate_id": CORP_ID, "name": "テスト"}
    db = build_mock_db({"clients": make_col(find_one=client)})

    with patch("app.services.agent_tools.get_database", return_value=db):
        invoice_result = await draft_invoice(
            CORP_ID, USER_ID,
            client_id=CLIENT_ID,
            amount=5000,
            description="テスト",
        )
    assert invoice_result.get("confirmation_required") is True


# ── 追加モックヘルパー ─────────────────────────────────────────────────────

def make_cursor_limited(return_value: list):
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.limit = MagicMock(return_value=cursor)

    async def _to_list(length=None):
        return return_value[:length] if length is not None else return_value

    cursor.to_list = _to_list
    return cursor


def make_scoped_col(all_docs: list):
    """corporate_id / _id フィルタを実際に適用するコレクションモック（スコープテスト用）。"""
    col = MagicMock()
    col.count_documents = AsyncMock(return_value=0)
    col.insert_one = AsyncMock(return_value=MagicMock())
    col.update_one = AsyncMock(return_value=MagicMock())
    col.find = MagicMock(return_value=make_cursor_limited([]))

    async def _find_one(query: dict, *args, **kwargs):
        cid = query.get("corporate_id")
        doc_id = query.get("_id")
        for d in all_docs:
            if doc_id is not None and d.get("_id") != doc_id:
                continue
            if cid is not None and d.get("corporate_id") != cid:
                continue
            return d
        return None

    col.find_one = AsyncMock(side_effect=_find_one)
    return col


# ═══════════════════════════════════════════════════════════════════════════
# 意地悪テスト（Task#17-B 追加）
# ═══════════════════════════════════════════════════════════════════════════

# ── ① journal_map.json の整合性テスト ─────────────────────────────────────

def test_journal_map_all_entries_have_required_fields():
    """全 16 エントリに必須フィールドが存在し、空でないこと"""
    from app.services.agent_tools import JOURNAL_MAP

    for name, entry in JOURNAL_MAP.items():
        assert entry.get("debit"),        f"{name}: debit が空または未定義"
        assert entry.get("credit"),       f"{name}: credit が空または未定義"
        assert entry.get("tax_category"), f"{name}: tax_category が空または未定義"
        assert entry.get("keywords"),     f"{name}: keywords が空リスト"


def test_journal_map_keywords_are_strings():
    """全エントリの keywords が文字列のリストであること（None・数値混入なし）"""
    from app.services.agent_tools import JOURNAL_MAP

    for name, entry in JOURNAL_MAP.items():
        for kw in entry["keywords"]:
            assert isinstance(kw, str), \
                f"{name}: keyword '{kw}' が文字列でない（型: {type(kw).__name__}）"
            assert kw is not None, f"{name}: keyword に None が混入している"


def test_lookup_journal_priority_order():
    """category 完全一致が keywords 部分一致より優先されること"""
    from app.services.agent_tools import _lookup_journal

    # category="旅費交通費" + description="電話"（通信費のキーワード）
    # → category 優先のため "旅費交通費" が返るはず（"通信費" ではない）
    result = _lookup_journal(description="電話代", category="旅費交通費")

    assert result["account_name"] == "旅費交通費", \
        "category マッチより keyword マッチが優先されている"
    assert result["confidence"] == "category_matched"


# ── ② suggest_journal_entry の境界値テスト ───────────────────────────────

@pytest.mark.asyncio
async def test_suggest_journal_entry_document_not_found():
    """存在しない document_id を渡した場合に {'error': 'not found'} が返ること"""
    from app.services.agent_tools import suggest_journal_entry

    db = build_mock_db({
        "receipts": make_col(find_one=None),
        "journal_rules": make_col(find_data=[]),
    })

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await suggest_journal_entry(CORP_ID, "receipt", str(ObjectId()))

    assert "error" in result
    assert result["error"] == "not found"


@pytest.mark.asyncio
async def test_suggest_journal_entry_wrong_corporate():
    """別法人のドキュメント ID を渡した場合に {'error': 'not found'} が返ること"""
    from app.services.agent_tools import suggest_journal_entry

    doc_id = ObjectId()
    CORP_B = str(ObjectId())
    doc_b = {
        "_id": doc_id,
        "corporate_id": CORP_B,   # ← 別法人
        "amount": 5000,
        "payee": "別法人テスト",
    }

    db = build_mock_db({
        "receipts": make_scoped_col([doc_b]),
        "journal_rules": make_col(find_data=[]),
    })

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await suggest_journal_entry(CORP_ID, "receipt", str(doc_id))

    assert "error" in result
    assert result["error"] == "not found"


@pytest.mark.asyncio
async def test_suggest_journal_entry_rule_keyword_single():
    """journal_rules の keyword（単数・1文字列）が description に部分一致すること"""
    from app.services.agent_tools import suggest_journal_entry

    doc_id = ObjectId()
    receipt = {
        "_id": doc_id,
        "corporate_id": CORP_ID,
        "amount": 2000,
        "payee": "タクシー代（新橋行き）",
        "description": "タクシー代（新橋行き）",  # ← "タクシー" を含む
        "category": "",
    }
    rule = {
        "_id": ObjectId(),
        "corporate_id": CORP_ID,
        "keyword": "タクシー",     # ← 単数・部分一致でヒットするはず
        "target_field": "description",
        "account_subject": "旅費交通費",
        "tax_division": "課税仕入 10%",
        "is_active": True,
    }

    db = build_mock_db({
        "receipts": make_col(find_one=receipt),
        "journal_rules": make_col(find_data=[rule]),
    })

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await suggest_journal_entry(CORP_ID, "receipt", str(doc_id))

    assert result["confidence"] == "rule_matched"
    assert result["suggested_debit"] == "旅費交通費"
    assert result["source_rule_id"] is not None


@pytest.mark.asyncio
async def test_suggest_journal_entry_empty_description():
    """description が空文字の場合に '雑費' にフォールバックしクラッシュしないこと"""
    from app.services.agent_tools import suggest_journal_entry

    doc_id = ObjectId()
    receipt = {
        "_id": doc_id,
        "corporate_id": CORP_ID,
        "amount": 100,
        "payee": "",
        "description": "",   # ← 空文字
        "category": "",
    }

    db = build_mock_db({
        "receipts": make_col(find_one=receipt),
        "journal_rules": make_col(find_data=[]),
    })

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await suggest_journal_entry(CORP_ID, "receipt", str(doc_id))

    assert "error" not in result
    assert result["suggested_debit"] == "雑費"
    assert result["confidence"] == "default"


# ── ③ suggest_reconciliation の境界値テスト ──────────────────────────────

@pytest.mark.asyncio
async def test_suggest_reconciliation_invalid_transaction_id():
    """不正な transaction_id を渡した場合に {'error': ...} が返ること"""
    from app.services.agent_tools import suggest_reconciliation

    db = build_mock_db({})

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await suggest_reconciliation(CORP_ID, "invalid-id")

    assert "error" in result
    assert isinstance(result["error"], str)


@pytest.mark.asyncio
async def test_suggest_reconciliation_wrong_corporate():
    """別法人の transaction_id を渡した場合に {'error': 'not found'} が返ること"""
    from app.services.agent_tools import suggest_reconciliation

    tx_id = ObjectId()
    CORP_B = str(ObjectId())
    tx = {
        "_id": tx_id,
        "corporate_id": CORP_B,   # ← 別法人
        "deposit_amount": 10000,
        "transaction_date": "2024-01-15",
    }

    db = build_mock_db({"transactions": make_scoped_col([tx])})

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await suggest_reconciliation(CORP_ID, str(tx_id))

    assert "error" in result
    assert result["error"] == "not found"


@pytest.mark.asyncio
async def test_suggest_reconciliation_candidates_sorted_by_score():
    """複数の候補がスコア降順で並んでいること（スコアの高いものが先頭）"""
    from app.services.agent_tools import suggest_reconciliation

    tx_id = ObjectId()
    tx = {
        "_id": tx_id,
        "corporate_id": CORP_ID,
        "deposit_amount": 10000,
        "transaction_date": "2024-01-15",
        "description": "テスト振込",
    }

    # 高スコア：金額完全一致（amount_score=40）
    receipt_high = {
        "_id": ObjectId(),
        "corporate_id": CORP_ID,
        "amount": 10000,
        "date": "2024-01-15",
        "payee": "高スコア",
        "approval_status": "approved",
    }
    # 低スコア：差額500（amount_score=35）
    receipt_low = {
        "_id": ObjectId(),
        "corporate_id": CORP_ID,
        "amount": 10500,
        "date": "2024-01-15",
        "payee": "低スコア",
        "approval_status": "approved",
    }

    # あえて低スコアを先に渡してソートが機能するか確認
    db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(find_data=[receipt_low, receipt_high]),
        "invoices": make_col(find_data=[]),
    })

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await suggest_reconciliation(CORP_ID, str(tx_id))

    assert "error" not in result
    candidates = result["candidates"]
    assert len(candidates) >= 2

    scores = [c["score"] for c in candidates]
    assert scores == sorted(scores, reverse=True), \
        f"スコアが降順になっていない: {scores}"

    assert candidates[0]["description"] == "高スコア"


@pytest.mark.asyncio
async def test_suggest_reconciliation_difference_is_absolute():
    """transaction_amount=1000・doc_amount=1200 の場合に difference=200（絶対値・負値なし）"""
    from app.services.agent_tools import suggest_reconciliation

    tx_id = ObjectId()
    tx = {
        "_id": tx_id,
        "corporate_id": CORP_ID,
        "deposit_amount": 1000,   # ← tx_amount
        "transaction_date": "2024-01-15",
        "description": "テスト",
    }
    receipt = {
        "_id": ObjectId(),
        "corporate_id": CORP_ID,
        "amount": 1200,           # ← doc_amount（差額200）
        "date": "2024-01-15",
        "payee": "テスト",
        "approval_status": "approved",
    }

    db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(find_data=[receipt]),
        "invoices": make_col(find_data=[]),
    })

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await suggest_reconciliation(CORP_ID, str(tx_id))

    assert "error" not in result
    candidates = result["candidates"]
    assert len(candidates) >= 1, "score=65 の候補が is_candidate=True にならなかった"
    assert candidates[0]["difference"] == 200   # abs(1000 - 1200) = 200
    assert candidates[0]["difference"] >= 0     # 負値でないこと


# ── ④ draft_expense_claim の境界値テスト ─────────────────────────────────

@pytest.mark.asyncio
async def test_draft_expense_claim_zero_amount():
    """amount=0 でもクラッシュせず draft が返ること"""
    from app.services.agent_tools import draft_expense_claim

    result = await draft_expense_claim(CORP_ID, USER_ID, 0, "テスト", "2024-01-01")

    assert "error" not in result
    assert "draft" in result
    assert result["draft"]["amount"] == 0


@pytest.mark.asyncio
async def test_draft_expense_claim_no_db_write_verified():
    """draft_expense_claim が get_database を呼ばず receipts に書き込まないこと"""
    from app.services.agent_tools import draft_expense_claim

    receipts_mock = make_col()
    db = build_mock_db({"receipts": receipts_mock})

    with patch("app.services.agent_tools.get_database", return_value=db) as mock_get_db:
        await draft_expense_claim(CORP_ID, USER_ID, 1000, "テスト", "2024-01-01")

    # draft_expense_claim は DB を一切触らないこと
    mock_get_db.assert_not_called()
    receipts_mock.insert_one.assert_not_called()
    receipts_mock.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_draft_expense_claim_default_payment_method():
    """payment_method=None の場合に draft.payment_method='現金' になること"""
    from app.services.agent_tools import draft_expense_claim

    result = await draft_expense_claim(
        CORP_ID, USER_ID, 1000, "テスト", "2024-01-01", payment_method=None
    )

    assert result["draft"]["payment_method"] == "現金"


@pytest.mark.asyncio
async def test_draft_expense_claim_category_override():
    """category='会議費' を明示した場合に description='タクシー代' でも category が '会議費' になること"""
    from app.services.agent_tools import draft_expense_claim

    result = await draft_expense_claim(
        CORP_ID, USER_ID,
        amount=3000,
        description="タクシー代（keywords なら '旅費交通費' になる）",
        date_str="2024-01-01",
        category="会議費",   # ← 明示指定が優先
    )

    assert "error" not in result
    assert result["draft"]["category"] == "会議費"
    assert result["suggested_journal"]["suggested_debit"] == "会議費"


# ── ⑤ draft_invoice の境界値テスト ──────────────────────────────────────

@pytest.mark.asyncio
async def test_draft_invoice_tax_calculation():
    """税率 10% / 8% の tax_amount・total_amount が正確に計算されること"""
    from app.services.agent_tools import draft_invoice

    client = {"_id": ObjectId(CLIENT_ID), "corporate_id": CORP_ID, "name": "テスト"}
    db = build_mock_db({"clients": make_col(find_one=client)})

    # 10% ケース
    with patch("app.services.agent_tools.get_database", return_value=db):
        r10 = await draft_invoice(
            CORP_ID, USER_ID, CLIENT_ID, 10000, "テスト", tax_rate=10
        )
    assert r10["draft"]["tax_amount"] == 1000
    assert r10["draft"]["total_amount"] == 11000

    # 8% ケース（int 切り捨て確認）
    with patch("app.services.agent_tools.get_database", return_value=db):
        r8 = await draft_invoice(
            CORP_ID, USER_ID, CLIENT_ID, 100, "テスト", tax_rate=8
        )
    assert r8["draft"]["tax_amount"] == 8      # int(100 * 8 / 100) = 8
    assert r8["draft"]["total_amount"] == 108


@pytest.mark.asyncio
async def test_draft_invoice_no_db_write_verified():
    """draft_invoice が invoices コレクションに書き込まないこと"""
    from app.services.agent_tools import draft_invoice

    client = {"_id": ObjectId(CLIENT_ID), "corporate_id": CORP_ID, "name": "テスト"}
    invoices_mock = make_col()
    clients_mock = make_col(find_one=client)

    db = build_mock_db({"clients": clients_mock, "invoices": invoices_mock})

    with patch("app.services.agent_tools.get_database", return_value=db):
        await draft_invoice(CORP_ID, USER_ID, CLIENT_ID, 10000, "テスト")

    invoices_mock.insert_one.assert_not_called()
    invoices_mock.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_draft_invoice_due_date_is_30_days_later():
    """due_date=None で today+30 日、明示指定ならその値が使われること"""
    from app.services.agent_tools import draft_invoice

    client = {"_id": ObjectId(CLIENT_ID), "corporate_id": CORP_ID, "name": "テスト"}
    db = build_mock_db({"clients": make_col(find_one=client)})

    # due_date=None → today+30日
    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await draft_invoice(
            CORP_ID, USER_ID, CLIENT_ID, 10000, "テスト", due_date=None
        )
    expected = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
    assert result["draft"]["due_date"] == expected

    # 明示指定
    explicit = "2025-06-30"
    with patch("app.services.agent_tools.get_database", return_value=db):
        result2 = await draft_invoice(
            CORP_ID, USER_ID, CLIENT_ID, 10000, "テスト", due_date=explicit
        )
    assert result2["draft"]["due_date"] == explicit


@pytest.mark.asyncio
async def test_draft_invoice_wrong_corporate_client():
    """別法人の client_id を渡した場合に {'error': '取引先が見つかりません'} が返ること"""
    from app.services.agent_tools import draft_invoice

    CORP_B = str(ObjectId())
    client_b = {
        "_id": ObjectId(CLIENT_ID),
        "corporate_id": CORP_B,   # ← 別法人
        "name": "別法人の取引先",
    }

    db = build_mock_db({"clients": make_scoped_col([client_b])})

    with patch("app.services.agent_tools.get_database", return_value=db):
        result = await draft_invoice(CORP_ID, USER_ID, CLIENT_ID, 10000, "テスト")

    assert result == {"error": "取引先が見つかりません"}


# ── ⑥ advisor エンドポイントテスト ──────────────────────────────────────

@pytest.mark.asyncio
async def test_suggest_tools_endpoints_exist():
    """提案系 4 エンドポイントが認証ありで 200 を返すこと"""
    import httpx
    from app.main import app
    from app.api.deps import get_current_user

    def mock_user():
        return {"uid": "test_uid"}

    app.dependency_overrides[get_current_user] = mock_user

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            with (
                patch("app.api.routes.advisor.resolve_corporate_id",
                      new=AsyncMock(return_value=(CORP_ID, USER_ID))),
                patch("app.api.routes.advisor.suggest_journal_entry",
                      new=AsyncMock(return_value={"suggested_debit": "雑費", "confidence": "default"})),
                patch("app.api.routes.advisor.suggest_reconciliation",
                      new=AsyncMock(return_value={"candidates": []})),
                patch("app.api.routes.advisor.draft_expense_claim",
                      new=AsyncMock(return_value={"draft": {}, "confirmation_required": True,
                                                   "suggested_journal": {}})),
                patch("app.api.routes.advisor.draft_invoice",
                      new=AsyncMock(return_value={"draft": {}, "confirmation_required": True})),
            ):
                r1 = await client.post(
                    "/api/v1/advisor/tools/suggest_journal_entry",
                    json={"document_type": "receipt", "document_id": str(ObjectId())},
                )
                r2 = await client.post(
                    "/api/v1/advisor/tools/suggest_reconciliation",
                    json={"transaction_id": str(ObjectId())},
                )
                r3 = await client.post(
                    "/api/v1/advisor/tools/draft_expense_claim",
                    json={"amount": 1000, "description": "テスト", "date": "2024-01-01"},
                )
                r4 = await client.post(
                    "/api/v1/advisor/tools/draft_invoice",
                    json={"client_id": str(ObjectId()), "amount": 10000, "description": "テスト"},
                )

        assert r1.status_code == 200, f"suggest_journal_entry: {r1.status_code}"
        assert r2.status_code == 200, f"suggest_reconciliation: {r2.status_code}"
        assert r3.status_code == 200, f"draft_expense_claim: {r3.status_code}"
        assert r4.status_code == 200, f"draft_invoice: {r4.status_code}"

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_draft_tools_require_confirmation():
    """draft_expense_claim・draft_invoice のレスポンスに confirmation_required=True が含まれること"""
    import httpx
    from app.main import app
    from app.api.deps import get_current_user

    def mock_user():
        return {"uid": "test_uid"}

    app.dependency_overrides[get_current_user] = mock_user

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            with (
                patch("app.api.routes.advisor.resolve_corporate_id",
                      new=AsyncMock(return_value=(CORP_ID, USER_ID))),
                patch("app.api.routes.advisor.draft_expense_claim",
                      new=AsyncMock(return_value={
                          "draft": {}, "confirmation_required": True, "suggested_journal": {}
                      })),
                patch("app.api.routes.advisor.draft_invoice",
                      new=AsyncMock(return_value={
                          "draft": {}, "confirmation_required": True
                      })),
            ):
                r_claim = await client.post(
                    "/api/v1/advisor/tools/draft_expense_claim",
                    json={"amount": 1000, "description": "テスト", "date": "2024-01-01"},
                )
                r_invoice = await client.post(
                    "/api/v1/advisor/tools/draft_invoice",
                    json={"client_id": str(ObjectId()), "amount": 10000, "description": "テスト"},
                )

        assert r_claim.status_code == 200
        assert r_claim.json()["confirmation_required"] is True

        assert r_invoice.status_code == 200
        assert r_invoice.json()["confirmation_required"] is True

    finally:
        app.dependency_overrides.clear()
