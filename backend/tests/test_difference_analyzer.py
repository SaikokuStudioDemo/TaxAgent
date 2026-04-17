"""
Tests for Task#24: 差額原因候補提示（difference_analyzer.py）

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_difference_analyzer.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

CORP_A_ID = str(ObjectId())
CORP_B_ID = str(ObjectId())


# ─────────────────────────────────────────────────────────────────────────────
# モックヘルパー
# ─────────────────────────────────────────────────────────────────────────────

def make_cursor(return_value: list):
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=return_value)
    return cursor


def make_col(find_one=None, find_data=None):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one)
    col.find = MagicMock(return_value=make_cursor(find_data or []))
    return col


def build_mock_db(collections: dict):
    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda k: collections.get(k, make_col()))
    return db


def make_filtering_col(all_docs: list):
    """
    ⑥ corporate_id / _id フィルタを実際に適用するコレクションモック。
    スコープ境界テストで使用する。
    """
    col = MagicMock()

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

    col.find_one = _find_one
    col.find = MagicMock(return_value=make_cursor([]))
    return col


def make_tx(corporate_id: str, deposit_amount: int = 0, amount: int = 0) -> dict:
    return {
        "_id": ObjectId(),
        "corporate_id": corporate_id,
        "deposit_amount": deposit_amount,
        "amount": amount,
        "description": "テスト取引",
    }


def make_receipt(corporate_id: str, amount: int) -> dict:
    return {
        "_id": ObjectId(),
        "corporate_id": corporate_id,
        "amount": amount,
        "approval_status": "approved",
        "reconciliation_status": "unreconciled",
    }


# ─────────────────────────────────────────────────────────────────────────────
# test_bank_fee_pattern_detected
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bank_fee_pattern_detected():
    """差額330円のケースで 'bank_fee' パターンが返ること。"""
    tx = make_tx(CORP_A_ID, deposit_amount=10330)
    receipt = make_receipt(CORP_A_ID, amount=10000)
    tx_id = str(tx["_id"])
    doc_id = str(receipt["_id"])

    mock_db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(find_one=receipt, find_data=[]),
    })

    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(CORP_A_ID, tx_id, [doc_id], "receipt")

    assert result["difference"] == 330
    patterns = [c["pattern"] for c in result["candidates"]]
    assert "bank_fee" in patterns
    bank_fee = next(c for c in result["candidates"] if c["pattern"] == "bank_fee")
    assert "330" in bank_fee["description"]
    assert result["has_candidates"] is True


# ─────────────────────────────────────────────────────────────────────────────
# test_combined_payment_pattern_detected
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_combined_payment_pattern_detected():
    """
    2件の書類合計が取引金額と一致する場合に 'combined_payment' パターンが返ること。
    _find_matching_combination は exclude_ids を除いた候補の中から
    2件の合計が tx_amount と一致する組み合わせを探す。
    → receipt_a は選択済みで除外。receipt_b(8000) + receipt_c(7000) = 15000 が一致。
    """
    tx = make_tx(CORP_A_ID, deposit_amount=15000)
    receipt_a = make_receipt(CORP_A_ID, amount=5000)   # 選択済み（除外対象）
    receipt_b = make_receipt(CORP_A_ID, amount=8000)   # 候補1
    receipt_c = make_receipt(CORP_A_ID, amount=7000)   # 候補2（8000+7000=15000）
    tx_id = str(tx["_id"])
    doc_id = str(receipt_a["_id"])

    mock_db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(
            find_one=receipt_a,
            find_data=[receipt_b, receipt_c],  # _find_matching_combination が受け取る候補
        ),
    })

    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(CORP_A_ID, tx_id, [doc_id], "receipt")

    patterns = [c["pattern"] for c in result["candidates"]]
    assert "combined_payment" in patterns, f"candidates={result['candidates']}"
    combo = next(c for c in result["candidates"] if c["pattern"] == "combined_payment")
    assert combo["difference"] == 0
    assert len(combo["additional_document_ids"]) == 2


# ─────────────────────────────────────────────────────────────────────────────
# test_partial_payment_pattern_detected
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_partial_payment_pattern_detected():
    """取引金額が書類合計より少ない場合に 'partial_payment' パターンが返ること。"""
    tx = make_tx(CORP_A_ID, deposit_amount=5000)
    receipt = make_receipt(CORP_A_ID, amount=10000)  # 請求10000 > 入金5000
    tx_id = str(tx["_id"])
    doc_id = str(receipt["_id"])

    mock_db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(find_one=receipt, find_data=[]),
        "invoices": make_col(find_one=None),
    })

    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(CORP_A_ID, tx_id, [doc_id], "receipt")

    patterns = [c["pattern"] for c in result["candidates"]]
    assert "partial_payment" in patterns
    partial = next(c for c in result["candidates"] if c["pattern"] == "partial_payment")
    assert partial["remaining_amount"] == 5000


# ─────────────────────────────────────────────────────────────────────────────
# test_no_candidates_when_exact_match
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_candidates_when_exact_match():
    """差額0の場合に candidates が空であること。"""
    tx = make_tx(CORP_A_ID, deposit_amount=10000)
    receipt = make_receipt(CORP_A_ID, amount=10000)
    tx_id = str(tx["_id"])
    doc_id = str(receipt["_id"])

    mock_db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(find_one=receipt, find_data=[]),
        "invoices": make_col(find_one=None),
    })

    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(CORP_A_ID, tx_id, [doc_id], "receipt")

    assert result["difference"] == 0
    assert result["candidates"] == []
    assert result["has_candidates"] is False


# ─────────────────────────────────────────────────────────────────────────────
# test_analyze_difference_cross_corporate_blocked  ⑥ make_filtering_col
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_difference_cross_corporate_blocked():
    """
    ⑥ 別法人の transaction_id を渡した場合に error が返ること。
    make_filtering_col で corporate_id フィルタを実際に適用して確認する。
    """
    # CORP_B の取引データ（CORP_A のトークンで取得しようとする）
    tx_b = make_tx(CORP_B_ID, deposit_amount=10000)
    all_txs = [tx_b]

    # corporate_id フィルタを実際に適用するモック
    tx_col = make_filtering_col(all_txs)

    mock_db = build_mock_db({"transactions": tx_col})

    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        # CORP_A として CORP_B の tx_id を指定
        result = await analyze_difference(
            CORP_A_ID,
            transaction_id=str(tx_b["_id"]),
            document_ids=[str(ObjectId())],
            doc_type="receipt",
        )

    assert "error" in result, "別法人の取引が返ってはいけない"


# ─────────────────────────────────────────────────────────────────────────────
# 追加：doc_type バリデーション・取引データなし
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_doc_type_returns_error():
    """⑤ 不正な doc_type を渡した場合に error が返ること。"""
    mock_db = build_mock_db({})
    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(CORP_A_ID, str(ObjectId()), [], "unknown_type")

    assert "error" in result
    assert "Unknown doc_type" in result["error"]


@pytest.mark.asyncio
async def test_transaction_not_found_returns_error():
    """存在しない transaction_id を渡した場合に error が返ること。"""
    mock_db = build_mock_db({"transactions": make_col(find_one=None)})
    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(CORP_A_ID, str(ObjectId()), [str(ObjectId())], "receipt")

    assert "error" in result


@pytest.mark.asyncio
async def test_invalid_transaction_id_returns_error():
    """不正な ObjectId 文字列を渡した場合に error が返ること（クラッシュしない）。"""
    mock_db = build_mock_db({"transactions": make_col(find_one=None)})
    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(CORP_A_ID, "not-a-valid-id", [], "receipt")

    assert "error" in result


@pytest.mark.asyncio
async def test_tx_amount_uses_deposit_amount():
    """③ deposit_amount が優先して使われること（amount フィールドより優先）。"""
    tx = {
        "_id": ObjectId(),
        "corporate_id": CORP_A_ID,
        "deposit_amount": 5000,
        "amount": 9999,  # こちらは使われないこと
    }
    receipt = make_receipt(CORP_A_ID, amount=5000)
    tx_id = str(tx["_id"])
    doc_id = str(receipt["_id"])

    mock_db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(find_one=receipt, find_data=[]),
        "invoices": make_col(find_one=None),
    })

    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(CORP_A_ID, tx_id, [doc_id], "receipt")

    # deposit_amount=5000 が使われれば差額0になる
    assert result["transaction_amount"] == 5000
    assert result["difference"] == 0


# =============================================================================
# 意地悪テスト（Task#24）
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# ① 差額パターン境界値テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bank_fee_pattern_at_threshold_1000():
    """差額ちょうど1000円でも 'bank_fee' パターンが返ること（境界値・含む）。"""
    tx = make_tx(CORP_A_ID, deposit_amount=11000)
    receipt = make_receipt(CORP_A_ID, amount=10000)
    tx_id = str(tx["_id"])
    doc_id = str(receipt["_id"])

    mock_db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(find_one=receipt, find_data=[]),
        "invoices": make_col(find_one=None),
    })

    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(CORP_A_ID, tx_id, [doc_id], "receipt")

    assert result["difference"] == 1000
    patterns = [c["pattern"] for c in result["candidates"]]
    assert "bank_fee" in patterns, "差額1000円（境界値）で bank_fee が返ること"


@pytest.mark.asyncio
async def test_bank_fee_not_detected_above_threshold():
    """差額1001円では 'bank_fee' パターンが返らないこと（境界値・超過）。"""
    tx = make_tx(CORP_A_ID, deposit_amount=11001)
    receipt = make_receipt(CORP_A_ID, amount=10000)
    tx_id = str(tx["_id"])
    doc_id = str(receipt["_id"])

    mock_db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(find_one=receipt, find_data=[]),
        "invoices": make_col(find_one=None),
    })

    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(CORP_A_ID, tx_id, [doc_id], "receipt")

    assert result["difference"] == 1001
    patterns = [c["pattern"] for c in result["candidates"]]
    assert "bank_fee" not in patterns, "差額1001円で bank_fee が返ってはいけない"


@pytest.mark.asyncio
async def test_bank_fee_not_detected_when_exact_match():
    """差額0円の場合に candidates が空であること。"""
    tx = make_tx(CORP_A_ID, deposit_amount=10000)
    receipt = make_receipt(CORP_A_ID, amount=10000)
    tx_id = str(tx["_id"])
    doc_id = str(receipt["_id"])

    mock_db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(find_one=receipt, find_data=[]),
        "invoices": make_col(find_one=None),
    })

    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(CORP_A_ID, tx_id, [doc_id], "receipt")

    assert result["difference"] == 0
    assert result["candidates"] == []
    assert result["has_candidates"] is False


@pytest.mark.asyncio
async def test_partial_payment_not_detected_when_tx_larger():
    """
    取引金額が書類合計より大きい場合（差額 > 0）に
    'partial_payment' パターンが返らないこと。
    partial_payment は tx_amount < doc_total（入金不足）の場合のみ。
    """
    tx = make_tx(CORP_A_ID, deposit_amount=15000)
    receipt = make_receipt(CORP_A_ID, amount=10000)  # tx > doc → 差額 +5000
    tx_id = str(tx["_id"])
    doc_id = str(receipt["_id"])

    mock_db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(find_one=receipt, find_data=[]),
        "invoices": make_col(find_one=None),
    })

    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(CORP_A_ID, tx_id, [doc_id], "receipt")

    assert result["difference"] == 5000  # tx_amount > doc_total
    patterns = [c["pattern"] for c in result["candidates"]]
    assert "partial_payment" not in patterns, \
        "tx > doc の場合に partial_payment が返ってはいけない"


@pytest.mark.asyncio
async def test_multiple_patterns_can_coexist():
    """
    差額が手数料範囲かつまとめ振込の可能性もある場合に
    複数の候補が返ること。
    差額330円（bank_fee 対象）かつ未消込書類の組み合わせも一致する状況。
    """
    # tx=10330、selected=10000（差額330）、かつ DB に 5330+5000=10330 の組み合わせ
    tx = make_tx(CORP_A_ID, deposit_amount=10330)
    selected = make_receipt(CORP_A_ID, amount=10000)
    combo_a = make_receipt(CORP_A_ID, amount=5330)
    combo_b = make_receipt(CORP_A_ID, amount=5000)

    mock_db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(find_one=selected, find_data=[combo_a, combo_b]),
        "invoices": make_col(find_one=None),
    })

    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(
            CORP_A_ID, str(tx["_id"]), [str(selected["_id"])], "receipt"
        )

    patterns = [c["pattern"] for c in result["candidates"]]
    assert "bank_fee" in patterns
    assert "combined_payment" in patterns
    assert len(result["candidates"]) >= 2


# ─────────────────────────────────────────────────────────────────────────────
# ② エラー耐性テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_difference_unknown_doc_type():
    """⑤ doc_type='unknown' を渡した場合に {'error': ...} が返ること。"""
    mock_db = build_mock_db({})
    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(CORP_A_ID, str(ObjectId()), [], "unknown")

    assert "error" in result
    assert "unknown" in result["error"].lower() or "Unknown" in result["error"]


@pytest.mark.asyncio
async def test_analyze_difference_empty_document_ids():
    """document_ids=[] を渡した場合に {'error': '書類データが見つかりません'} が返ること。"""
    tx = make_tx(CORP_A_ID, deposit_amount=10000)
    mock_db = build_mock_db({"transactions": make_col(find_one=tx)})

    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(CORP_A_ID, str(tx["_id"]), [], "receipt")

    assert "error" in result
    assert "書類" in result["error"]


@pytest.mark.asyncio
async def test_analyze_difference_invalid_transaction_id():
    """transaction_id='invalid-id' を渡した場合に {'error': ...} が返ること。"""
    mock_db = build_mock_db({"transactions": make_col(find_one=None)})
    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(CORP_A_ID, "invalid-id", [], "receipt")

    assert "error" in result


@pytest.mark.asyncio
async def test_analyze_difference_invalid_document_id_skipped():
    """
    document_ids に 'invalid-id' が含まれていてもクラッシュしないこと。
    有効な doc_id がなければ {'error': ...} が返ること。
    """
    tx = make_tx(CORP_A_ID, deposit_amount=10000)
    mock_db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(find_one=None),
    })

    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        # 不正ID のみ → docs = [] → error
        result = await analyze_difference(
            CORP_A_ID, str(tx["_id"]), ["invalid-id"], "receipt"
        )

    assert "error" in result  # クラッシュせず error が返ること


@pytest.mark.asyncio
async def test_analyze_difference_mixed_valid_invalid_ids():
    """valid な doc_id と invalid な doc_id が混在する場合に valid のみで計算されること。"""
    tx = make_tx(CORP_A_ID, deposit_amount=10000)
    valid_receipt = make_receipt(CORP_A_ID, amount=10000)
    tx_id = str(tx["_id"])
    valid_id = str(valid_receipt["_id"])

    mock_db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(find_one=valid_receipt, find_data=[]),
        "invoices": make_col(find_one=None),
    })

    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(
            CORP_A_ID, tx_id, ["invalid-id", valid_id], "receipt"
        )

    # クラッシュせず valid のみで計算（差額0）
    assert "error" not in result
    assert result["document_total"] == 10000
    assert result["difference"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# ③ tx_amount フィールドフォールバックテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tx_amount_uses_withdrawal_amount():
    """deposit_amount がなく withdrawal_amount がある場合に withdrawal_amount が使われること。"""
    tx = {
        "_id": ObjectId(),
        "corporate_id": CORP_A_ID,
        "withdrawal_amount": 8000,
        # deposit_amount キーなし
    }
    receipt = make_receipt(CORP_A_ID, amount=8000)
    tx_id = str(tx["_id"])
    doc_id = str(receipt["_id"])

    mock_db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(find_one=receipt, find_data=[]),
        "invoices": make_col(find_one=None),
    })

    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(CORP_A_ID, tx_id, [doc_id], "receipt")

    assert result["transaction_amount"] == 8000
    assert result["difference"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# ⑥ レスポンス形式の一貫性テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_difference_response_has_all_fields():
    """正常処理時のレスポンスに必須フィールドが全て含まれること。"""
    tx = make_tx(CORP_A_ID, deposit_amount=10000)
    receipt = make_receipt(CORP_A_ID, amount=10000)
    tx_id = str(tx["_id"])
    doc_id = str(receipt["_id"])

    mock_db = build_mock_db({
        "transactions": make_col(find_one=tx),
        "receipts": make_col(find_one=receipt, find_data=[]),
        "invoices": make_col(find_one=None),
    })

    with patch("app.services.difference_analyzer.get_database", return_value=mock_db):
        from app.services.difference_analyzer import analyze_difference
        result = await analyze_difference(CORP_A_ID, tx_id, [doc_id], "receipt")

    required_keys = {
        "transaction_id", "transaction_amount", "document_total",
        "difference", "candidates", "has_candidates",
    }
    missing = required_keys - set(result.keys())
    assert not missing, f"レスポンスに不足フィールド: {missing}"
