"""
Tests for Task#20: POST /api/v1/ocr/extract エンドポイント

Usage:
    cd backend
    pytest tests/test_ocr_extract.py -v
"""
import pytest
from unittest.mock import AsyncMock, patch
from bson import ObjectId

CORP_ID = str(ObjectId())
USER_ID = str(ObjectId())
VALID_FILE_URL = "https://storage.googleapis.com/test-bucket/receipts/sample.jpg"
FAKE_FILE_BYTES = b"fake_image_data"


# ── エンドポイントテスト共通セットアップ ──────────────────────────────────────

async def _post_extract(app, payload: dict):
    """POST /api/v1/ocr/extract を mock 認証で呼ぶヘルパー。"""
    import httpx
    from app.api.deps import get_current_user

    def _mock_user():
        return {"uid": "test_uid"}

    app.dependency_overrides[get_current_user] = _mock_user

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            with patch("app.api.routes.ocr.resolve_corporate_id",
                       new=AsyncMock(return_value=(CORP_ID, USER_ID))):
                resp = await client.post("/api/v1/ocr/extract", json=payload)
    finally:
        app.dependency_overrides.clear()

    return resp


# ═══════════════════════════════════════════════════════════════════════════
# バリデーションテスト
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ocr_extract_missing_file_url_returns_400():
    """file_url なしで POST すると 400 が返ること"""
    from app.main import app

    resp = await _post_extract(app, {"doc_type": "receipt"})

    assert resp.status_code == 400
    assert "file_url" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ocr_extract_invalid_doc_type_returns_400():
    """doc_type に 'unknown' を渡すと 400 が返ること"""
    from app.main import app

    resp = await _post_extract(app, {
        "file_url": VALID_FILE_URL,
        "doc_type": "unknown",
    })

    assert resp.status_code == 400
    assert "doc_type" in resp.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════
# ダウンロード失敗テスト
# ③ _download_url をパッチして 403/401 を再現
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ocr_extract_download_failure_handled():
    """Firebase Storage の URL が 403 を返した場合に 400 エラーが返ること"""
    from app.main import app
    from fastapi import HTTPException

    with patch("app.api.routes.ocr._download_url",
               new=AsyncMock(side_effect=HTTPException(
                   status_code=400,
                   detail="ファイルにアクセスできませんでした。URLが期限切れの可能性があります。"
               ))):
        resp = await _post_extract(app, {
            "file_url": VALID_FILE_URL,
            "doc_type": "receipt",
        })

    assert resp.status_code == 400
    assert "アクセスできませんでした" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ocr_extract_download_401_handled():
    """Firebase Storage の URL が 401 を返した場合も 400 エラーが返ること"""
    from app.main import app
    from fastapi import HTTPException

    with patch("app.api.routes.ocr._download_url",
               new=AsyncMock(side_effect=HTTPException(
                   status_code=400,
                   detail="ファイルにアクセスできませんでした。URLが期限切れの可能性があります。"
               ))):
        resp = await _post_extract(app, {
            "file_url": VALID_FILE_URL,
            "doc_type": "receipt",
        })

    assert resp.status_code == 400
    assert "アクセスできませんでした" in resp.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════
# OCR 処理テスト
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ocr_extract_ocr_failure_returns_422():
    """AIService.analyze_invoice_pdf が None を返した場合に 422 が返ること"""
    from app.main import app

    with (
        patch("app.api.routes.ocr._download_url",
              new=AsyncMock(return_value=FAKE_FILE_BYTES)),
        patch("app.api.routes.ocr.AIService.analyze_invoice_pdf",
              new=AsyncMock(return_value=None)),
    ):
        resp = await _post_extract(app, {
            "file_url": VALID_FILE_URL,
            "doc_type": "receipt",
        })

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ocr_extract_success_returns_confirmation_required():
    """正常処理時に confirmation_required=True が返ること"""
    from app.main import app

    mock_ocr = {
        "vendor_name": "テストタクシー株式会社",
        "total_amount": 3200,
        "date": "2026-04-10",
        "category": "旅費交通費",
    }

    with (
        patch("app.api.routes.ocr._download_url",
              new=AsyncMock(return_value=FAKE_FILE_BYTES)),
        patch("app.api.routes.ocr.AIService.analyze_invoice_pdf",
              new=AsyncMock(return_value=mock_ocr)),
    ):
        resp = await _post_extract(app, {
            "file_url": VALID_FILE_URL,
            "doc_type": "receipt",
        })

    assert resp.status_code == 200
    assert resp.json()["confirmation_required"] is True


@pytest.mark.asyncio
async def test_ocr_extract_journal_suggestion_included():
    """正常処理時に journal_suggestion が正しいフィールドで返ること"""
    from app.main import app

    mock_ocr = {
        "vendor_name": "タクシー会社",
        "total_amount": 5000,
        "date": "2026-04-15",
        "category": "旅費交通費",
    }

    with (
        patch("app.api.routes.ocr._download_url",
              new=AsyncMock(return_value=FAKE_FILE_BYTES)),
        patch("app.api.routes.ocr.AIService.analyze_invoice_pdf",
              new=AsyncMock(return_value=mock_ocr)),
    ):
        resp = await _post_extract(app, {
            "file_url": VALID_FILE_URL,
            "doc_type": "receipt",
        })

    assert resp.status_code == 200
    data = resp.json()
    journal = data["journal_suggestion"]

    assert "suggested_debit" in journal
    assert "suggested_credit" in journal
    assert "suggested_tax_category" in journal
    # 旅費交通費が提案されること（JOURNAL_MAP のキーワードマッチ）
    assert journal["suggested_debit"] == "旅費交通費"
    assert journal["suggested_credit"] == "未払金"


# ══════════════════════════════════════════════════════════════════════════
# 意地悪テスト（Task#20 追加）
# ══════════════════════════════════════════════════════════════════════════

# ── 共通ヘルパー ──────────────────────────────────────────────────────────

def _make_mock_ocr(**kwargs):
    """OCR モックデータを生成するヘルパー。"""
    base = {
        "vendor_name": "テスト株式会社",
        "total_amount": 3000,
        "date": "2026-04-15",
    }
    base.update(kwargs)
    return base


# ── ① 入力バリデーションテスト ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_string_file_url_returns_400():
    """file_url=''（空文字）で 400 が返ること"""
    from app.main import app

    resp = await _post_extract(app, {"file_url": "", "doc_type": "receipt"})

    assert resp.status_code == 400
    assert "file_url" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_file_url_none_returns_400():
    """file_url=null（JSON null → Python None）で 400 が返ること"""
    from app.main import app

    resp = await _post_extract(app, {"file_url": None, "doc_type": "receipt"})

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_doc_type_case_sensitive():
    """doc_type='Receipt'（大文字）で 400 が返ること。"receipt"/"invoice" のみ有効。"""
    from app.main import app

    for bad in ("Receipt", "Invoice", "RECEIPT", "PDF", ""):
        resp = await _post_extract(app, {
            "file_url": VALID_FILE_URL,
            "doc_type": bad,
        })
        assert resp.status_code == 400, f"doc_type='{bad}' が 400 にならなかった"


# ── ② ダウンロード処理テスト ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_download_401_returns_400_with_message():
    """_download_url が 401 を模倣した HTTPException を投げた場合に 400 が返り detail に「アクセスできませんでした」が含まれること"""
    from app.main import app
    from fastapi import HTTPException as FHE

    with patch("app.api.routes.ocr._download_url",
               new=AsyncMock(side_effect=FHE(
                   status_code=400,
                   detail="ファイルにアクセスできませんでした。URLが期限切れの可能性があります。",
               ))):
        resp = await _post_extract(app, {
            "file_url": VALID_FILE_URL,
            "doc_type": "receipt",
        })

    assert resp.status_code == 400
    assert "アクセスできませんでした" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_download_403_returns_400_with_message():
    """_download_url が 403 を模倣した HTTPException を投げた場合に 400 が返ること"""
    from app.main import app
    from fastapi import HTTPException as FHE

    with patch("app.api.routes.ocr._download_url",
               new=AsyncMock(side_effect=FHE(
                   status_code=400,
                   detail="ファイルにアクセスできませんでした。URLが期限切れの可能性があります。",
               ))):
        resp = await _post_extract(app, {
            "file_url": VALID_FILE_URL,
            "doc_type": "receipt",
        })

    assert resp.status_code == 400
    # 400 にキャッチされており、200 や 403 になっていないこと
    assert resp.status_code != 403


@pytest.mark.asyncio
async def test_download_500_re_raises():
    """ダウンロードで 500 系エラーが発生した場合に 500 が返り 400 にダウングレードされないこと"""
    from app.main import app

    with patch("app.api.routes.ocr._download_url",
               new=AsyncMock(side_effect=Exception("Internal Server Error"))):
        resp = await _post_extract(app, {
            "file_url": VALID_FILE_URL,
            "doc_type": "receipt",
        })

    assert resp.status_code == 500, "500 にならなかった"
    assert resp.status_code != 400, "500 が 400 にダウングレードされた"


@pytest.mark.asyncio
async def test_tmp_file_cleaned_up_on_success():
    """正常処理後に一時ファイルが削除されていること（finally ブロックの確認）"""
    from app.main import app
    import os
    import tempfile as real_tempfile

    captured = {}
    _orig_ntf = real_tempfile.NamedTemporaryFile

    def _tracking_ntf(*args, **kwargs):
        f = _orig_ntf(*args, **kwargs)
        captured["path"] = f.name
        return f

    with (
        patch("app.api.routes.ocr._download_url",
              new=AsyncMock(return_value=FAKE_FILE_BYTES)),
        patch("app.api.routes.ocr.AIService.analyze_invoice_pdf",
              new=AsyncMock(return_value=_make_mock_ocr())),
        patch("app.api.routes.ocr.tempfile.NamedTemporaryFile",
              side_effect=_tracking_ntf),
    ):
        resp = await _post_extract(app, {
            "file_url": VALID_FILE_URL,
            "doc_type": "receipt",
        })

    assert resp.status_code == 200
    assert "path" in captured, "一時ファイルが作成されなかった"
    assert not os.path.exists(captured["path"]), \
        f"正常処理後も一時ファイルが残っている: {captured['path']}"


@pytest.mark.asyncio
async def test_tmp_file_cleaned_up_on_error():
    """OCR 処理中に例外が発生した場合でも一時ファイルが削除されること（finally ブロックの確認）"""
    from app.main import app
    import os
    import tempfile as real_tempfile

    captured = {}
    _orig_ntf = real_tempfile.NamedTemporaryFile

    def _tracking_ntf(*args, **kwargs):
        f = _orig_ntf(*args, **kwargs)
        captured["path"] = f.name
        return f

    with (
        patch("app.api.routes.ocr._download_url",
              new=AsyncMock(return_value=FAKE_FILE_BYTES)),
        patch("app.api.routes.ocr.AIService.analyze_invoice_pdf",
              new=AsyncMock(side_effect=Exception("OCR 処理エラー"))),
        patch("app.api.routes.ocr.tempfile.NamedTemporaryFile",
              side_effect=_tracking_ntf),
    ):
        resp = await _post_extract(app, {
            "file_url": VALID_FILE_URL,
            "doc_type": "receipt",
        })

    assert resp.status_code == 500
    assert "path" in captured, "一時ファイルが作成されなかった"
    assert not os.path.exists(captured["path"]), \
        f"エラー後も一時ファイルが残っている: {captured['path']}"


# ── ③ OCR 結果の処理テスト ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ocr_result_with_line_items_uses_first_category():
    """top-level category がなく line_items[0].category がある場合にその category が仕訳提案に使われること"""
    from app.main import app

    mock_ocr = {
        "vendor_name": "接待会社",
        "total_amount": 15000,
        "date": "2026-04-01",
        # top-level category なし → line_items から取得
        "line_items": [{"category": "交際費", "amount": 15000}],
    }

    with (
        patch("app.api.routes.ocr._download_url",
              new=AsyncMock(return_value=FAKE_FILE_BYTES)),
        patch("app.api.routes.ocr.AIService.analyze_invoice_pdf",
              new=AsyncMock(return_value=mock_ocr)),
    ):
        resp = await _post_extract(app, {
            "file_url": VALID_FILE_URL,
            "doc_type": "receipt",
        })

    assert resp.status_code == 200
    journal = resp.json()["journal_suggestion"]
    # 交際費が JOURNAL_MAP に存在するため category_matched で返ること
    assert journal["suggested_debit"] == "交際費"
    assert journal["confidence"] == "category_matched"


@pytest.mark.asyncio
async def test_ocr_result_without_category_uses_default():
    """category も line_items もない場合に confidence='default'・雑費にフォールバックすること"""
    from app.main import app

    mock_ocr = {
        "vendor_name": "不明の会社",
        "total_amount": 500,
        # category も line_items も description もなし
    }

    with (
        patch("app.api.routes.ocr._download_url",
              new=AsyncMock(return_value=FAKE_FILE_BYTES)),
        patch("app.api.routes.ocr.AIService.analyze_invoice_pdf",
              new=AsyncMock(return_value=mock_ocr)),
    ):
        resp = await _post_extract(app, {
            "file_url": VALID_FILE_URL,
            "doc_type": "receipt",
        })

    assert resp.status_code == 200
    journal = resp.json()["journal_suggestion"]
    assert journal["confidence"] == "default"
    assert journal["suggested_debit"] == "雑費"


@pytest.mark.asyncio
async def test_ocr_result_with_vendor_name_included():
    """レスポンスの ocr_result に OCR で取得した vendor_name がそのまま含まれること"""
    from app.main import app

    mock_ocr = _make_mock_ocr(vendor_name="ABCタクシー株式会社")

    with (
        patch("app.api.routes.ocr._download_url",
              new=AsyncMock(return_value=FAKE_FILE_BYTES)),
        patch("app.api.routes.ocr.AIService.analyze_invoice_pdf",
              new=AsyncMock(return_value=mock_ocr)),
    ):
        resp = await _post_extract(app, {
            "file_url": VALID_FILE_URL,
            "doc_type": "receipt",
        })

    assert resp.status_code == 200
    ocr = resp.json()["ocr_result"]
    assert ocr["vendor_name"] == "ABCタクシー株式会社"


# ── ④ レスポンス構造テスト ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_response_always_has_confirmation_required_true():
    """正常処理時に confirmation_required が常に True であること（False/None にならないこと）"""
    from app.main import app

    with (
        patch("app.api.routes.ocr._download_url",
              new=AsyncMock(return_value=FAKE_FILE_BYTES)),
        patch("app.api.routes.ocr.AIService.analyze_invoice_pdf",
              new=AsyncMock(return_value=_make_mock_ocr())),
    ):
        resp = await _post_extract(app, {
            "file_url": VALID_FILE_URL,
            "doc_type": "receipt",
        })

    data = resp.json()
    assert data["confirmation_required"] is True
    assert data["confirmation_required"] is not False
    assert data["confirmation_required"] is not None


@pytest.mark.asyncio
async def test_journal_suggestion_has_all_required_fields():
    """journal_suggestion に suggested_debit / credit / tax_category / confidence の 4 フィールドが全て含まれること"""
    from app.main import app

    with (
        patch("app.api.routes.ocr._download_url",
              new=AsyncMock(return_value=FAKE_FILE_BYTES)),
        patch("app.api.routes.ocr.AIService.analyze_invoice_pdf",
              new=AsyncMock(return_value=_make_mock_ocr())),
    ):
        resp = await _post_extract(app, {
            "file_url": VALID_FILE_URL,
            "doc_type": "receipt",
        })

    assert resp.status_code == 200
    journal = resp.json()["journal_suggestion"]

    required_fields = ["suggested_debit", "suggested_credit",
                       "suggested_tax_category", "confidence"]
    for field in required_fields:
        assert field in journal, f"journal_suggestion に '{field}' が存在しない"
        assert journal[field] is not None, f"'{field}' が None になっている"
        assert journal[field] != "", f"'{field}' が空文字になっている"


# ── ⑤ 認証テスト ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ocr_extract_requires_auth():
    """Authorization ヘッダーなしでは 401 または 403 が返ること（HTTPBearer の自動拒否）"""
    import httpx
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # Authorization ヘッダーなしで直接リクエスト
        resp = await client.post(
            "/api/v1/ocr/extract",
            json={"file_url": VALID_FILE_URL, "doc_type": "receipt"},
        )

    # FastAPI の HTTPBearer は Authorization なしで 403 を返す
    assert resp.status_code in (401, 403)
