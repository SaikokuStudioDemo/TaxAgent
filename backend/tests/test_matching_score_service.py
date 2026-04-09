"""
Tests for matching_score_service.calculate_match_score

Usage:
    cd backend
    pytest tests/test_matching_score_service.py -v
"""
import pytest
from app.services.matching_score_service import calculate_match_score


# ── ヘルパー ──────────────────────────────────────────────────

def _tx(amount=1000, date="2025-01-15", desc="テスト摘要", norm=None):
    return {
        "amount": amount,
        "transaction_date": date,
        "description": desc,
        "normalized_name": norm,
    }


def _receipt(amount=1000, date="2025-01-15", payee="テスト店舗"):
    return {"amount": amount, "date": date, "payee": payee}


def _invoice(amount=1000, issue_date="2025-01-15", due_date=None, client="テスト会社"):
    return {
        "total_amount": amount,
        "issue_date": issue_date,
        "due_date": due_date,
        "client_name": client,
    }


# ── 金額スコア ─────────────────────────────────────────────────

def test_amount_exact_match_gives_40():
    r = calculate_match_score(_tx(1000), _receipt(1000), "receipt")
    assert r["score_breakdown"]["amount"] == 40


def test_amount_within_500_gives_35():
    r = calculate_match_score(_tx(1000), _receipt(1300), "receipt")
    assert r["score_breakdown"]["amount"] == 35


def test_amount_within_1000_gives_25():
    r = calculate_match_score(_tx(1000), _receipt(1800), "receipt")
    assert r["score_breakdown"]["amount"] == 25


def test_amount_over_1000_returns_score_zero_and_not_candidate():
    r = calculate_match_score(_tx(1000), _receipt(3000), "receipt")
    assert r["score"] == 0
    assert r["is_candidate"] is False
    assert r["score_breakdown"] == {"amount": 0, "date": 0, "name": 0}


# ── 日付スコア ─────────────────────────────────────────────────

def test_date_same_day_gives_30():
    r = calculate_match_score(_tx(1000, "2025-01-15"), _receipt(1000, "2025-01-15"), "receipt")
    assert r["score_breakdown"]["date"] == 30


def test_date_within_3_days_gives_25():
    r = calculate_match_score(_tx(1000, "2025-01-15"), _receipt(1000, "2025-01-17"), "receipt")
    assert r["score_breakdown"]["date"] == 25


def test_date_within_7_days_gives_15():
    r = calculate_match_score(_tx(1000, "2025-01-15"), _receipt(1000, "2025-01-20"), "receipt")
    assert r["score_breakdown"]["date"] == 15


def test_date_within_14_days_gives_5():
    r = calculate_match_score(_tx(1000, "2025-01-15"), _receipt(1000, "2025-01-25"), "receipt")
    assert r["score_breakdown"]["date"] == 5


def test_date_over_14_days_gives_0():
    r = calculate_match_score(_tx(1000, "2025-01-15"), _receipt(1000, "2025-02-28"), "receipt")
    assert r["score_breakdown"]["date"] == 0


def test_missing_date_gives_0():
    tx = {"amount": 1000, "description": "test"}  # no transaction_date
    r = calculate_match_score(tx, _receipt(1000, "2025-01-15"), "receipt")
    assert r["score_breakdown"]["date"] == 0


# ── 名称スコア ─────────────────────────────────────────────────

def test_name_direct_partial_match_gives_30():
    r = calculate_match_score(
        _tx(1000, desc="セブンイレブン川崎店"),
        _receipt(1000, payee="セブンイレブン"),
        "receipt",
    )
    assert r["score_breakdown"]["name"] == 30


def test_name_contained_in_description_gives_30():
    r = calculate_match_score(
        _tx(1000, desc="タクシー東京代"),
        _receipt(1000, payee="タクシー"),
        "receipt",
    )
    assert r["score_breakdown"]["name"] == 30


def test_name_katakana_hiragana_match_gives_20():
    # 摘要: ひらがな "たくしー" ↔ 支払先: カタカナ "タクシー"
    r = calculate_match_score(
        _tx(1000, desc="たくしーだいきん"),
        _receipt(1000, payee="タクシー"),
        "receipt",
    )
    assert r["score_breakdown"]["name"] == 20


def test_name_prefix_3chars_match_gives_10():
    # "スターバックス渋谷店" と "スターバックス" → 先頭5文字 "スターバ" が一致
    r = calculate_match_score(
        _tx(1000, desc="スターバックス渋谷店"),
        _receipt(1000, payee="スターバックスコーヒー"),
        "receipt",
    )
    assert r["score_breakdown"]["name"] == 10


def test_name_no_match_gives_0():
    r = calculate_match_score(
        _tx(1000, desc="ABCショップ"),
        _receipt(1000, payee="xyz商店"),
        "receipt",
    )
    assert r["score_breakdown"]["name"] == 0


def test_name_normalized_name_partial_match():
    r = calculate_match_score(
        _tx(1000, desc="ATM出金", norm="セブンイレブン"),
        _receipt(1000, payee="セブンイレブン神戸店"),
        "receipt",
    )
    assert r["score_breakdown"]["name"] == 30


# ── 総合スコア・is_candidate ───────────────────────────────────

def test_high_score_all_match():
    """金額完全一致・日付1日以内・名称一致 → 80点以上"""
    r = calculate_match_score(
        _tx(3500, "2025-01-15", "セブンイレブン川崎店"),
        _receipt(3500, "2025-01-15", "セブンイレブン"),
        "receipt",
    )
    assert r["score"] >= 80
    assert r["is_candidate"] is True


def test_low_score_amount_match_but_date_and_name_far():
    """金額一致・日付遠い・名称不一致 → date=0 or name=0 のため早期除外"""
    r = calculate_match_score(
        _tx(1000, "2025-01-01", "ABCショップ"),
        _receipt(1000, "2025-03-31", "xyz商店"),
        "receipt",
    )
    # date=0 かつ name=0 → score=0, is_candidate=False
    assert r["score"] == 0
    assert r["is_candidate"] is False
    assert r["score_breakdown"]["amount"] == 40
    assert r["score_breakdown"]["date"] == 0
    assert r["score_breakdown"]["name"] == 0


def test_is_candidate_true_when_score_gte_60():
    """60点以上で is_candidate=True"""
    r = calculate_match_score(
        _tx(1000, "2025-01-15", "テスト店"),
        _receipt(1000, "2025-01-15", "テスト"),
        "receipt",
    )
    # 40 + 30 + 30 = 100点
    assert r["score"] >= 60
    assert r["is_candidate"] is True


def test_invoice_uses_total_amount():
    """請求書は total_amount フィールドを使う"""
    tx = _tx(50000, "2025-01-15", "株式会社テスト")
    inv = _invoice(50000, "2025-01-15", client="株式会社テスト")
    r = calculate_match_score(tx, inv, "invoice")
    assert r["score_breakdown"]["amount"] == 40


def test_invoice_uses_closer_date():
    """請求書は issue_date と due_date のうち近い方を使う"""
    # issue_date: 30日離れ、due_date: 2日離れ → due_date を使うはず
    tx = _tx(1000, "2025-02-01")
    inv = _invoice(1000, issue_date="2025-01-01", due_date="2025-02-03")
    r = calculate_match_score(tx, inv, "invoice")
    assert r["score_breakdown"]["date"] == 25  # ±3日以内


def test_score_breakdown_keys():
    """score_breakdown に amount/date/name キーが必ず含まれる"""
    r = calculate_match_score(_tx(), _receipt(), "receipt")
    assert set(r["score_breakdown"].keys()) == {"amount", "date", "name"}
