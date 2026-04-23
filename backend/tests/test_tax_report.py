"""
Tests for Task#38: 税務申告サポートデータ集計

Usage:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_tax_report.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

CORP_ID = "test_corp_id"
CORP_B_ID = "other_corp_id"


# ─────────────────────────────────────────────────────────────────────────────
# モックヘルパー
# ─────────────────────────────────────────────────────────────────────────────

def make_cursor(return_value: list):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=return_value)
    return cursor


def make_col(find_data=None):
    col = MagicMock()
    col.find = MagicMock(return_value=make_cursor(find_data or []))
    return col


def build_mock_db(collections: dict = None):
    db = MagicMock()
    cols = collections or {}
    db.__getitem__ = MagicMock(side_effect=lambda k: cols.get(k, make_col()))
    return db


def issued_inv(amount: int, tax_rate=0.10, period="2025-04") -> dict:
    return {
        "_id": ObjectId(), "corporate_id": CORP_ID,
        "document_type": "issued", "approval_status": "approved",
        "fiscal_period": period, "total_amount": amount, "tax_rate": tax_rate,
        "line_items": [],
    }


def received_inv(amount: int, tax_rate=0.10, period="2025-04") -> dict:
    return {
        "_id": ObjectId(), "corporate_id": CORP_ID,
        "document_type": "received", "approval_status": "approved",
        "fiscal_period": period, "total_amount": amount, "tax_rate": tax_rate,
    }


def receipt_doc(amount: int, tax_rate=10, period="2025-04") -> dict:
    return {
        "_id": ObjectId(), "corporate_id": CORP_ID,
        "approval_status": "approved",
        "fiscal_period": period, "amount": amount, "tax_rate": tax_rate,
    }


# ─────────────────────────────────────────────────────────────────────────────
# test_tax_report_10_percent_calculation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tax_report_10_percent_calculation():
    """tax_rate=10 の領収書 11,000円 → taxable_10=11000・consumption_tax_10=1000。"""
    from app.services.tax_report_service import get_tax_report

    mock_db = build_mock_db({
        "invoices": make_col(find_data=[]),
        "receipts": make_col(find_data=[receipt_doc(11000, tax_rate=10)]),
    })

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    p = result["purchases"]
    assert p["taxable_10"] == 11000
    assert p["consumption_tax_10"] == round(11000 * 10 / 110)  # 1000


@pytest.mark.asyncio
async def test_tax_report_8_percent_calculation():
    """tax_rate=8 の領収書 10,800円 → taxable_8=10800・consumption_tax_8=800。"""
    from app.services.tax_report_service import get_tax_report

    mock_db = build_mock_db({
        "invoices": make_col(find_data=[]),
        "receipts": make_col(find_data=[receipt_doc(10800, tax_rate=8)]),
    })

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    p = result["purchases"]
    assert p["taxable_8"] == 10800
    assert p["consumption_tax_8"] == round(10800 * 8 / 108)  # 800


@pytest.mark.asyncio
async def test_tax_report_zero_rate_goes_to_exempt():
    """tax_rate=0 のデータが tax_exempt に集計されること。"""
    from app.services.tax_report_service import get_tax_report

    mock_db = build_mock_db({
        "invoices": make_col(find_data=[]),
        "receipts": make_col(find_data=[receipt_doc(5000, tax_rate=0)]),
    })

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    p = result["purchases"]
    assert p["tax_exempt"] == 5000
    assert p["taxable_10"] == 0
    assert p["taxable_8"] == 0


@pytest.mark.asyncio
async def test_tax_rate_int_and_float_both_work():
    """tax_rate=10（int）と tax_rate=0.10（float）が同じ結果になること。"""
    from app.services.tax_report_service import get_tax_report

    mock_db_int = build_mock_db({
        "invoices": make_col(find_data=[]),
        "receipts": make_col(find_data=[receipt_doc(11000, tax_rate=10)]),
    })
    mock_db_float = build_mock_db({
        "invoices": make_col(find_data=[received_inv(11000, tax_rate=0.10)]),
        "receipts": make_col(find_data=[]),
    })

    with patch("app.services.tax_report_service.get_database", return_value=mock_db_int):
        result_int = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    with patch("app.services.tax_report_service.get_database", return_value=mock_db_float):
        result_float = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    assert result_int["purchases"]["consumption_tax_10"] == result_float["purchases"]["consumption_tax_10"]


@pytest.mark.asyncio
async def test_tax_payable_calculation():
    """売上消費税 10,000円・仕入消費税 3,000円 → tax_payable=7,000。"""
    from app.services.tax_report_service import get_tax_report

    # 売上側: 11,000円 税込 10% → 消費税 1,000円
    # 売上合計が 110,000円になるように設定（×10）
    sales_inv = issued_inv(110000, tax_rate=0.10)  # 消費税 10,000円
    # 仕入側: 33,000円 税込 10% → 消費税 3,000円
    purch_inv = received_inv(33000, tax_rate=0.10)

    # issued と received を同じ invoices コレクションから返す
    call_count = {"n": 0}
    def find_side(query):
        call_count["n"] += 1
        dt = query.get("document_type")
        if dt == "issued":
            return make_cursor([sales_inv])
        elif dt == "received":
            return make_cursor([purch_inv])
        return make_cursor([])

    invoices_col = MagicMock()
    invoices_col.find = MagicMock(side_effect=find_side)
    receipts_col = make_col(find_data=[])

    mock_db = build_mock_db({"invoices": invoices_col, "receipts": receipts_col})

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    sales_tax = result["sales"]["total_consumption_tax"]
    purchase_tax = result["purchases"]["deductible_tax"]
    assert result["summary"]["tax_payable"] == sales_tax - purchase_tax
    assert result["summary"]["has_refund"] is False


@pytest.mark.asyncio
async def test_tax_refund_when_purchases_exceed_sales():
    """仕入消費税が売上消費税を超える場合に has_refund=True・tax_refund > 0。"""
    from app.services.tax_report_service import get_tax_report

    # 売上: 1,100円 → 消費税 100円
    # 仕入: 110,000円 → 消費税 10,000円（仕入 > 売上）
    def find_side(query):
        dt = query.get("document_type")
        if dt == "issued":
            return make_cursor([issued_inv(1100, tax_rate=0.10)])
        elif dt == "received":
            return make_cursor([received_inv(110000, tax_rate=0.10)])
        return make_cursor([])

    invoices_col = MagicMock()
    invoices_col.find = MagicMock(side_effect=find_side)
    mock_db = build_mock_db({"invoices": invoices_col, "receipts": make_col(find_data=[])})

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    assert result["summary"]["has_refund"] is True
    assert result["summary"]["tax_refund"] > 0
    assert result["summary"]["tax_payable"] == 0


@pytest.mark.asyncio
async def test_unapproved_excluded():
    """approval_status='approved' フィルタがクエリに含まれること（未承認は除外）。"""
    from app.services.tax_report_service import get_tax_report

    receipts_col = make_col(find_data=[])
    invoices_col = make_col(find_data=[])
    mock_db = build_mock_db({"invoices": invoices_col, "receipts": receipts_col})

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    receipts_query = receipts_col.find.call_args[0][0]
    assert receipts_query.get("approval_status") == "approved"


@pytest.mark.asyncio
async def test_cross_corporate_blocked():
    """別法人のデータが集計に含まれないこと（corporate_id フィルタ確認）。"""
    from app.services.tax_report_service import get_tax_report

    receipts_col = make_col(find_data=[])
    invoices_col = make_col(find_data=[])
    mock_db = build_mock_db({"invoices": invoices_col, "receipts": receipts_col})

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    receipts_q = receipts_col.find.call_args[0][0]
    assert receipts_q.get("corporate_id") == CORP_ID

    # invoices は複数回呼ばれるので最後のコールで確認
    invoices_q = invoices_col.find.call_args[0][0]
    assert invoices_q.get("corporate_id") == CORP_ID


@pytest.mark.asyncio
async def test_monthly_filter():
    """month=3 を指定した場合に fiscal_period フィルタが '2025-03' のみになること。"""
    from app.services.tax_report_service import get_tax_report

    receipts_col = make_col(find_data=[])
    invoices_col = make_col(find_data=[])
    mock_db = build_mock_db({"invoices": invoices_col, "receipts": receipts_col})

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=3)

    assert result["fiscal_periods"] == ["2025-03"]
    receipts_q = receipts_col.find.call_args[0][0]
    fps = receipts_q.get("fiscal_period", {}).get("$in", [])
    assert fps == ["2025-03"]


@pytest.mark.asyncio
async def test_accounting_role_required():
    """staff ロールで GET /exports/tax-report すると 403 が返ること。"""
    from fastapi import HTTPException
    from app.api.routes.exports import get_tax_report_endpoint

    staff_emp = {"_id": ObjectId(), "firebase_uid": "staff_uid", "role": "staff"}
    mock_db = build_mock_db({
        "corporates": MagicMock(find_one=AsyncMock(return_value=None)),
        "employees": MagicMock(find_one=AsyncMock(return_value=staff_emp)),
    })

    with patch("app.api.routes.exports.get_database", return_value=mock_db), \
         patch("app.api.routes.exports.resolve_corporate_id",
               new_callable=AsyncMock, return_value=(CORP_ID, CORP_ID)):
        with pytest.raises(HTTPException) as exc:
            await get_tax_report_endpoint(
                fiscal_year=2025, month=None, current_user={"uid": "staff_uid"}
            )

    assert exc.value.status_code == 403


# =============================================================================
# 意地悪テスト（Task#38）
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# ① 消費税逆算の精度テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tax_10_reverse_calculation_precision():
    """
    10% 逆算精度テスト。
    ※ プロンプトの 10,001円→910円 は誤りで正しくは 909円（round(10001*10/110)）。
    """
    from app.services.tax_report_service import get_tax_report

    cases = [
        (11000, 1000),   # 端数なし
        (11100, 1009),   # round(11100*10/110) = 1009
        (10001, 909),    # round(10001*10/110) = 909（プロンプトの 910 は誤り）
    ]
    for amount, expected_tax in cases:
        mock_db = build_mock_db({
            "invoices": make_col(find_data=[]),
            "receipts": make_col(find_data=[receipt_doc(amount, tax_rate=10)]),
        })
        with patch("app.services.tax_report_service.get_database", return_value=mock_db):
            result = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

        actual = result["purchases"]["consumption_tax_10"]
        assert actual == expected_tax, \
            f"{amount}円: 期待値={expected_tax}円 実際={actual}円"


@pytest.mark.asyncio
async def test_tax_8_reverse_calculation_precision():
    """8% 逆算精度テスト。"""
    from app.services.tax_report_service import get_tax_report

    cases = [
        (10800, 800),   # 端数なし
        (10000, 741),   # round(10000*8/108) = round(740.74...) = 741（四捨五入）
    ]
    for amount, expected_tax in cases:
        mock_db = build_mock_db({
            "invoices": make_col(find_data=[]),
            "receipts": make_col(find_data=[receipt_doc(amount, tax_rate=8)]),
        })
        with patch("app.services.tax_report_service.get_database", return_value=mock_db):
            result = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

        actual = result["purchases"]["consumption_tax_8"]
        assert actual == expected_tax, \
            f"{amount}円: 期待値={expected_tax}円 実際={actual}円"


@pytest.mark.asyncio
async def test_total_equals_sum_of_categories():
    """taxable_10 + taxable_8 + tax_exempt == total が常に成立すること。"""
    from app.services.tax_report_service import get_tax_report

    mock_db = build_mock_db({
        "invoices": make_col(find_data=[]),
        "receipts": make_col(find_data=[
            receipt_doc(11000, tax_rate=10),
            receipt_doc(10800, tax_rate=8),
            receipt_doc(5000, tax_rate=0),
        ]),
    })
    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    p = result["purchases"]
    category_sum = p["taxable_10"] + p["taxable_8"] + p["tax_exempt"]
    assert category_sum == p["total"], \
        f"taxable_10+taxable_8+tax_exempt={category_sum} ≠ total={p['total']}"


# ─────────────────────────────────────────────────────────────────────────────
# ② tax_rate の型混在テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_int_rate_10_same_as_float_010():
    """tax_rate=10（int）と tax_rate=0.10（float）で同じ consumption_tax が返ること。"""
    from app.services.tax_report_service import get_tax_report

    amount = 11000
    mock_int = build_mock_db({"invoices": make_col(find_data=[]), "receipts": make_col(find_data=[receipt_doc(amount, tax_rate=10)])})
    mock_float = build_mock_db({"invoices": make_col(find_data=[received_inv(amount, tax_rate=0.10)]), "receipts": make_col(find_data=[])})

    with patch("app.services.tax_report_service.get_database", return_value=mock_int):
        r_int = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)
    with patch("app.services.tax_report_service.get_database", return_value=mock_float):
        r_float = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    assert r_int["purchases"]["consumption_tax_10"] == r_float["purchases"]["consumption_tax_10"]


@pytest.mark.asyncio
async def test_int_rate_8_same_as_float_008():
    """tax_rate=8（int）と tax_rate=0.08（float）で同じ結果になること。"""
    from app.services.tax_report_service import get_tax_report

    amount = 10800
    mock_int = build_mock_db({"invoices": make_col(find_data=[]), "receipts": make_col(find_data=[receipt_doc(amount, tax_rate=8)])})
    mock_float = build_mock_db({"invoices": make_col(find_data=[received_inv(amount, tax_rate=0.08)]), "receipts": make_col(find_data=[])})

    with patch("app.services.tax_report_service.get_database", return_value=mock_int):
        r_int = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)
    with patch("app.services.tax_report_service.get_database", return_value=mock_float):
        r_float = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    assert r_int["purchases"]["consumption_tax_8"] == r_float["purchases"]["consumption_tax_8"]


@pytest.mark.asyncio
async def test_int_rate_0_goes_to_exempt():
    """tax_rate=0（int）が tax_exempt に集計されること。"""
    from app.services.tax_report_service import get_tax_report

    mock_db = build_mock_db({"invoices": make_col(find_data=[]), "receipts": make_col(find_data=[receipt_doc(5000, tax_rate=0)])})
    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    assert result["purchases"]["tax_exempt"] == 5000
    assert result["purchases"]["taxable_10"] == 0


@pytest.mark.asyncio
async def test_float_rate_0_goes_to_exempt():
    """tax_rate=0.0（float）が tax_exempt に集計されること。"""
    from app.services.tax_report_service import get_tax_report

    mock_db = build_mock_db({"invoices": make_col(find_data=[received_inv(3000, tax_rate=0.0)]), "receipts": make_col(find_data=[])})
    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    assert result["purchases"]["tax_exempt"] == 3000


# ─────────────────────────────────────────────────────────────────────────────
# ③ line_items 集計テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_line_items_total_overrides_invoice_total():
    """
    ① 修正確認：total_amount=110,000 だが line_items 合計=99,000 の場合に
    total=99,000 で集計されること（total_amount は使われない）。
    """
    from app.services.tax_report_service import get_tax_report

    inv = {
        "_id": ObjectId(), "corporate_id": CORP_ID,
        "document_type": "issued", "approval_status": "approved",
        "fiscal_period": "2025-04",
        "total_amount": 110000,   # ← これは使われない
        "tax_rate": 0.10,
        "line_items": [
            {"tax_rate": 0.10, "subtotal": 55000},
            {"tax_rate": 0.10, "subtotal": 44000},
        ],
    }

    def find_side(query):
        if query.get("document_type") == "issued":
            return make_cursor([inv])
        return make_cursor([])

    invoices_col = MagicMock()
    invoices_col.find = MagicMock(side_effect=find_side)
    mock_db = build_mock_db({"invoices": invoices_col, "receipts": make_col(find_data=[])})

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    assert result["sales"]["total"] == 99000, \
        f"total={result['sales']['total']} (期待値: 99000)"


@pytest.mark.asyncio
async def test_line_items_mixed_rates():
    """line_items に 10% と 8% が混在する場合にそれぞれ正しく分類されること。"""
    from app.services.tax_report_service import get_tax_report

    inv = {
        "_id": ObjectId(), "corporate_id": CORP_ID,
        "document_type": "issued", "approval_status": "approved",
        "fiscal_period": "2025-04", "total_amount": 21800, "tax_rate": 0.10,
        "line_items": [
            {"tax_rate": 0.10, "subtotal": 11000},   # 10% 商品
            {"tax_rate": 0.08, "subtotal": 10800},   # 8% 軽減
        ],
    }

    def find_side(query):
        if query.get("document_type") == "issued":
            return make_cursor([inv])
        return make_cursor([])

    invoices_col = MagicMock()
    invoices_col.find = MagicMock(side_effect=find_side)
    mock_db = build_mock_db({"invoices": invoices_col, "receipts": make_col(find_data=[])})

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    s = result["sales"]
    assert s["taxable_10"] == 11000
    assert s["taxable_8"] == 10800
    assert s["total"] == 21800


@pytest.mark.asyncio
async def test_no_line_items_uses_total_amount():
    """line_items が空の場合に total_amount で集計されること。"""
    from app.services.tax_report_service import get_tax_report

    inv = {
        "_id": ObjectId(), "corporate_id": CORP_ID,
        "document_type": "issued", "approval_status": "approved",
        "fiscal_period": "2025-04", "total_amount": 55000, "tax_rate": 0.10,
        "line_items": [],  # 空
    }

    def find_side(query):
        if query.get("document_type") == "issued":
            return make_cursor([inv])
        return make_cursor([])

    invoices_col = MagicMock()
    invoices_col.find = MagicMock(side_effect=find_side)
    mock_db = build_mock_db({"invoices": invoices_col, "receipts": make_col(find_data=[])})

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    assert result["sales"]["total"] == 55000


# ─────────────────────────────────────────────────────────────────────────────
# ④ 納付税額・還付テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tax_payable_never_negative():
    """tax_payable は常に 0 以上であること（仕入 > 売上でも 0）。"""
    from app.services.tax_report_service import get_tax_report

    # 売上消費税 100円・仕入消費税 9,000円
    def find_side(query):
        if query.get("document_type") == "issued":
            return make_cursor([issued_inv(1100, tax_rate=0.10)])
        elif query.get("document_type") == "received":
            return make_cursor([received_inv(99000, tax_rate=0.10)])
        return make_cursor([])

    invoices_col = MagicMock()
    invoices_col.find = MagicMock(side_effect=find_side)
    mock_db = build_mock_db({"invoices": invoices_col, "receipts": make_col(find_data=[])})

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    assert result["summary"]["tax_payable"] >= 0, "tax_payable が負になった"
    assert result["summary"]["tax_payable"] == 0


@pytest.mark.asyncio
async def test_tax_refund_correct_when_purchases_exceed():
    """売上消費税 5,000円・仕入消費税 8,000円 → tax_refund=3,000・has_refund=True。"""
    from app.services.tax_report_service import get_tax_report

    # 売上: 55,000円 税込10% → 消費税 5,000円
    # 仕入: 88,000円 税込10% → 消費税 8,000円
    def find_side(query):
        if query.get("document_type") == "issued":
            return make_cursor([issued_inv(55000, tax_rate=0.10)])
        elif query.get("document_type") == "received":
            return make_cursor([received_inv(88000, tax_rate=0.10)])
        return make_cursor([])

    invoices_col = MagicMock()
    invoices_col.find = MagicMock(side_effect=find_side)
    mock_db = build_mock_db({"invoices": invoices_col, "receipts": make_col(find_data=[])})

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    sales_tax = round(55000 * 10 / 110)   # 5000
    purchase_tax = round(88000 * 10 / 110)  # 8000
    expected_refund = purchase_tax - sales_tax  # 3000

    assert result["summary"]["has_refund"] is True
    assert result["summary"]["tax_refund"] == expected_refund
    assert result["summary"]["tax_payable"] == 0


@pytest.mark.asyncio
async def test_both_tax_payable_and_refund_not_positive():
    """tax_payable と tax_refund が同時に正の値にならないこと。"""
    from app.services.tax_report_service import get_tax_report

    for inv_amount, receipt_amount in [(110000, 33000), (11000, 220000), (110000, 110000)]:
        def find_side(query, inv_a=inv_amount, r_a=receipt_amount):
            if query.get("document_type") == "issued":
                return make_cursor([issued_inv(inv_a, tax_rate=0.10)])
            elif query.get("document_type") == "received":
                return make_cursor([received_inv(r_a, tax_rate=0.10)])
            return make_cursor([])

        invoices_col = MagicMock()
        invoices_col.find = MagicMock(side_effect=find_side)
        mock_db = build_mock_db({"invoices": invoices_col, "receipts": make_col(find_data=[])})

        with patch("app.services.tax_report_service.get_database", return_value=mock_db):
            result = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

        s = result["summary"]
        assert not (s["tax_payable"] > 0 and s["tax_refund"] > 0), \
            f"inv={inv_amount} r={receipt_amount}: payable={s['tax_payable']} refund={s['tax_refund']} が同時に正"


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ 集計期間テスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_yearly_report_includes_all_12_months():
    """month を省略した場合に fiscal_periods に 12 ヶ月分含まれること。"""
    from app.services.tax_report_service import get_tax_report

    receipts_col = make_col(find_data=[])
    invoices_col = make_col(find_data=[])
    mock_db = build_mock_db({"invoices": invoices_col, "receipts": receipts_col})

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=None)

    assert len(result["fiscal_periods"]) == 12
    assert "2025-01" in result["fiscal_periods"]
    assert "2025-12" in result["fiscal_periods"]


@pytest.mark.asyncio
async def test_monthly_report_excludes_other_months():
    """month=6 を指定した場合にクエリの fiscal_period が '2025-06' のみになること。"""
    from app.services.tax_report_service import get_tax_report

    receipts_col = make_col(find_data=[])
    invoices_col = make_col(find_data=[])
    mock_db = build_mock_db({"invoices": invoices_col, "receipts": receipts_col})

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=6)

    assert result["fiscal_periods"] == ["2025-06"]
    q = receipts_col.find.call_args[0][0]
    assert q["fiscal_period"]["$in"] == ["2025-06"]


@pytest.mark.asyncio
async def test_fiscal_year_boundary():
    """fiscal_year=2025 のクエリに 2024-xx の fiscal_period が含まれないこと。"""
    from app.services.tax_report_service import get_tax_report

    receipts_col = make_col(find_data=[])
    invoices_col = make_col(find_data=[])
    mock_db = build_mock_db({"invoices": invoices_col, "receipts": receipts_col})

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=None)

    for fp in result["fiscal_periods"]:
        assert fp.startswith("2025-"), f"2025年以外の期間が含まれている: {fp}"
    assert "2024-12" not in result["fiscal_periods"]


# ─────────────────────────────────────────────────────────────────────────────
# ⑥ スコープテスト
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sales_cross_corporate_blocked():
    """別法人の発行請求書が売上に含まれないこと（corporate_id フィルタ確認）。"""
    from app.services.tax_report_service import get_tax_report

    invoices_col = make_col(find_data=[])
    mock_db = build_mock_db({"invoices": invoices_col, "receipts": make_col(find_data=[])})

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    # issued クエリのフィルタを確認（複数の find 呼び出しの中から issued を探す）
    issued_calls = [
        c for c in invoices_col.find.call_args_list
        if c[0][0].get("document_type") == "issued"
    ]
    assert len(issued_calls) > 0
    assert issued_calls[0][0][0].get("corporate_id") == CORP_ID


@pytest.mark.asyncio
async def test_purchases_cross_corporate_blocked():
    """別法人の領収書・受領請求書が仕入に含まれないこと（corporate_id フィルタ確認）。"""
    from app.services.tax_report_service import get_tax_report

    receipts_col = make_col(find_data=[])
    invoices_col = make_col(find_data=[])
    mock_db = build_mock_db({"invoices": invoices_col, "receipts": receipts_col})

    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    # receipts クエリのフィルタ確認
    receipts_q = receipts_col.find.call_args[0][0]
    assert receipts_q.get("corporate_id") == CORP_ID

    # received クエリのフィルタ確認
    received_calls = [
        c for c in invoices_col.find.call_args_list
        if c[0][0].get("document_type") == "received"
    ]
    assert len(received_calls) > 0
    assert received_calls[0][0][0].get("corporate_id") == CORP_ID
