"""
helpers.py のユーティリティ関数テスト
extract_fiscal_period / ApprovalStatus / is_approved
"""
import pytest
from unittest.mock import patch
from app.api.helpers import extract_fiscal_period, ApprovalStatus, is_approved


# ─── extract_fiscal_period ────────────────────────────────────────

def test_extract_fiscal_period_from_date():
    assert extract_fiscal_period("2025-03-15") == "2025-03"

def test_extract_fiscal_period_no_date():
    with patch("app.api.helpers.datetime") as mock_dt:
        mock_dt.utcnow.return_value.strftime.return_value = "2025-03"
        result = extract_fiscal_period(None)
    assert result == "2025-03"

def test_extract_fiscal_period_boundary_first_day():
    assert extract_fiscal_period("2025-03-01") == "2025-03"

def test_extract_fiscal_period_boundary_last_day():
    assert extract_fiscal_period("2025-03-31") == "2025-03"

def test_extract_fiscal_period_year_boundary():
    assert extract_fiscal_period("2024-12-31") == "2024-12"
    assert extract_fiscal_period("2025-01-01") == "2025-01"

def test_extract_fiscal_period_empty_string():
    # 空文字は falsy → 現在月を返す
    with patch("app.api.helpers.datetime") as mock_dt:
        mock_dt.utcnow.return_value.strftime.return_value = "2025-04"
        result = extract_fiscal_period("")
    assert result == "2025-04"


# ─── is_approved ─────────────────────────────────────────────────

def test_is_approved_approved():
    assert is_approved(ApprovalStatus.APPROVED) is True

def test_is_approved_auto_approved():
    assert is_approved(ApprovalStatus.AUTO_APPROVED) is True

def test_is_approved_pending():
    assert is_approved(ApprovalStatus.PENDING) is False

def test_is_approved_rejected():
    assert is_approved(ApprovalStatus.REJECTED) is False

def test_is_approved_draft():
    assert is_approved(ApprovalStatus.DRAFT) is False

def test_is_approved_unknown():
    assert is_approved("unknown_status") is False

def test_is_approved_empty():
    assert is_approved("") is False


# ─── ApprovalStatus 定数値確認 ─────────────────────────────────────

def test_approval_status_constants():
    assert ApprovalStatus.DRAFT == "draft"
    assert ApprovalStatus.PENDING == "pending_approval"
    assert ApprovalStatus.APPROVED == "approved"
    assert ApprovalStatus.AUTO_APPROVED == "auto_approved"
    assert ApprovalStatus.REJECTED == "rejected"
