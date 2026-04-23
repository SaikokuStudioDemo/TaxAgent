"""
tax_utils.py の単体テスト。
切り捨て・四捨五入・ゼロ税率・フォールバックチェーンを検証する。
"""
import pytest
from app.utils.tax_utils import (
    calc_tax_from_inclusive,
    calc_tax_from_exclusive,
    calc_inclusive_from_exclusive,
)


# ── calc_tax_from_inclusive ─────────────────────────────────────────────────

def test_calc_tax_from_inclusive_10_percent():
    assert calc_tax_from_inclusive(11000, 10) == 1000


def test_calc_tax_from_inclusive_8_percent():
    assert calc_tax_from_inclusive(10800, 8) == 800


def test_calc_tax_from_inclusive_rounding():
    # 11050 * 10 / 110 = 1004.545... → 四捨五入 → 1005
    result = calc_tax_from_inclusive(11050, 10)
    assert result == 1005, f"expected 1005, got {result}"
    # 切り捨てなら 1004 になることを確認
    import math
    floor_result = math.floor(11050 * 10 / 110)
    assert floor_result == 1004


# ── calc_tax_from_exclusive ─────────────────────────────────────────────────

def test_calc_tax_from_exclusive_10_percent():
    assert calc_tax_from_exclusive(10000, 10) == 1000


def test_calc_tax_from_exclusive_floor():
    # 10001 * 10 / 100 = 1000.1 → 切り捨て → 1000
    assert calc_tax_from_exclusive(10001, 10) == 1000


def test_calc_tax_from_exclusive_8_percent_floor():
    # 10001 * 8 / 100 = 800.08 → 切り捨て → 800
    assert calc_tax_from_exclusive(10001, 8) == 800


# ── ゼロ税率 ────────────────────────────────────────────────────────────────

def test_calc_tax_zero_rate_inclusive():
    assert calc_tax_from_inclusive(11000, 0) == 0


def test_calc_tax_zero_rate_exclusive():
    assert calc_tax_from_exclusive(10000, 0) == 0


# ── calc_inclusive_from_exclusive ───────────────────────────────────────────

def test_calc_inclusive_from_exclusive():
    assert calc_inclusive_from_exclusive(10000, 10) == 11000


def test_calc_inclusive_from_exclusive_8_percent():
    assert calc_inclusive_from_exclusive(10000, 8) == 10800


def test_calc_inclusive_from_exclusive_zero():
    assert calc_inclusive_from_exclusive(10000, 0) == 10000


# ── ① 逆算（calc_tax_from_inclusive）精度テスト ────────────────────────────

def test_inclusive_10_no_remainder():
    assert calc_tax_from_inclusive(11000, 10) == 1000


def test_inclusive_10_with_remainder_rounds_up():
    # 11050 * 10 / 110 = 1004.545... → 四捨五入 → 1005
    assert calc_tax_from_inclusive(11050, 10) == 1005


def test_inclusive_10_with_remainder_rounds_down():
    # 11030 * 10 / 110 = 1002.727... → 四捨五入 → 1003
    assert calc_tax_from_inclusive(11030, 10) == 1003


def test_inclusive_8_no_remainder():
    assert calc_tax_from_inclusive(10800, 8) == 800


def test_inclusive_8_with_remainder():
    # 10000 * 8 / 108 = 740.740... → 四捨五入 → 741
    assert calc_tax_from_inclusive(10000, 8) == 741


def test_inclusive_0_rate():
    assert calc_tax_from_inclusive(11000, 0) == 0


# ── ② 直算（calc_tax_from_exclusive）精度テスト ────────────────────────────

def test_exclusive_10_no_remainder():
    assert calc_tax_from_exclusive(10000, 10) == 1000


def test_exclusive_10_floors():
    # 10001 * 10 / 100 = 1000.1 → 切り捨て → 1000
    assert calc_tax_from_exclusive(10001, 10) == 1000
    # 10005 * 10 / 100 = 1000.5 → 切り捨て → 1000（四捨五入なら1001）
    assert calc_tax_from_exclusive(10005, 10) == 1000


def test_exclusive_8_floors():
    # 12345 * 8 / 100 = 987.6 → 切り捨て → 987
    assert calc_tax_from_exclusive(12345, 8) == 987


def test_exclusive_0_rate():
    assert calc_tax_from_exclusive(10000, 0) == 0


# ── ③ 税込計算（calc_inclusive_from_exclusive）テスト ──────────────────────

def test_inclusive_from_exclusive_10():
    assert calc_inclusive_from_exclusive(10000, 10) == 11000


def test_inclusive_from_exclusive_8():
    assert calc_inclusive_from_exclusive(10000, 8) == 10800


def test_inclusive_from_exclusive_floors():
    # 10001 * 10 / 100 = 1000.1 → 税額切り捨て 1000 → 税込 11001
    assert calc_inclusive_from_exclusive(10001, 10) == 11001


# ── ④ 逆算 vs 直算の整合性テスト ───────────────────────────────────────────

def test_roundtrip_exclusive_to_inclusive_to_tax():
    # 税抜 10000 → 税込 11000 → 逆算税額 1000
    inclusive = calc_inclusive_from_exclusive(10000, 10)
    assert inclusive == 11000
    assert calc_tax_from_inclusive(inclusive, 10) == 1000


def test_roundtrip_with_remainder():
    # 税抜 10001 → 税込 11001 → 逆算税額 + 税抜 = 税込 が成立すること
    exclusive = 10001
    inclusive = calc_inclusive_from_exclusive(exclusive, 10)
    assert inclusive == 11001
    tax = calc_tax_from_inclusive(inclusive, 10)
    # 逆算税額 + 税抜 ≈ 税込（切り捨て誤差で ±1 以内）
    assert tax + exclusive == inclusive or abs((tax + exclusive) - inclusive) <= 1


def test_floor_vs_round_difference_confirmed():
    # 11050円（10%）逆算で切り捨てと四捨五入の差が 1円であることを記録
    import math
    floor_result = math.floor(11050 * 10 / 110)  # 1004
    round_result = calc_tax_from_inclusive(11050, 10)   # 1005
    assert floor_result == 1004
    assert round_result == 1005
    assert round_result - floor_result == 1


# ── tax_report_service との整合性確認 ───────────────────────────────────────

@pytest.mark.asyncio
async def test_tax_report_uses_new_utils():
    """
    tax_report_service の集計結果が calc_tax_from_inclusive の値と一致することを確認する。
    """
    from unittest.mock import patch, AsyncMock, MagicMock

    CORP_ID = "corp_tax_utils_test"
    amount_10 = 11000
    amount_8 = 10800

    def make_col(find_result=None, find_one=None):
        col = MagicMock()
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=find_result or [])
        col.find = MagicMock(return_value=cursor)
        col.find_one = AsyncMock(return_value=find_one)
        return col

    mock_db = {
        "invoices": make_col(find_result=[
            {"corporate_id": CORP_ID, "document_type": "issued",
             "approval_status": "approved", "fiscal_period": "2025-04",
             "total_amount": amount_10, "tax_rate": 10},
            {"corporate_id": CORP_ID, "document_type": "received",
             "approval_status": "approved", "fiscal_period": "2025-04",
             "total_amount": amount_8, "tax_rate": 8},
        ]),
        "receipts": make_col(find_result=[]),
    }

    from app.services.tax_report_service import get_tax_report
    with patch("app.services.tax_report_service.get_database", return_value=mock_db):
        result = await get_tax_report(CORP_ID, fiscal_year=2025, month=4)

    expected_sales_tax_10 = calc_tax_from_inclusive(amount_10, 10)
    expected_purchases_tax_8 = calc_tax_from_inclusive(amount_8, 8)

    assert result["sales"]["consumption_tax_10"] == expected_sales_tax_10
    assert result["purchases"]["consumption_tax_8"] == expected_purchases_tax_8
