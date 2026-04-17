# 意地悪テストのパターン

実装後は必ずこのチェックリストを満たすテストを書くこと。
全テスト PASSED を確認してから次のタスクへ進む。

**実行コマンド**:
```bash
cd backend
PYTHONPATH=. venv/bin/pytest tests/test_xxx.py -v
```

---

## 0. テストファイルの共通セットアップ

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId

# 必ず 2 法人分の ID を用意する
CORP_A_ID = str(ObjectId())
CORP_B_ID = str(ObjectId())

# ── Motor カーソルモック ──────────────────────────────────────────────────────

def make_cursor(return_value: list):
    """sort().limit().to_list() チェーンのモック"""
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.limit = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=return_value)
    return cursor

def make_col(find_one=None, find_data=None, count=0, agg_data=None):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one)
    col.count_documents = AsyncMock(return_value=count)
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    col.find = MagicMock(return_value=make_cursor(find_data or []))
    col.aggregate = MagicMock(return_value=make_cursor(agg_data or []))
    return col

def make_filtering_col(all_docs: list):
    """corporate_id / _id フィルタを実際に適用するコレクションモック（スコープテスト必須）"""
    col = MagicMock()
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=0))
    col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))

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

    async def _to_list(length=None):
        return []  # find() はデフォルト空

    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = _to_list
    col.find = MagicMock(return_value=cursor)
    col.find_one = _find_one
    col.count_documents = AsyncMock(return_value=0)
    return col
```

---

## 1. スコープ境界（別法人データの漏洩確認）

**必須**: 全ての読み取り・更新・削除エンドポイントで確認する。

```python
@pytest.mark.asyncio
async def test_scope_isolation_read():
    """法人 B のドキュメントを法人 A のトークンで取得できないこと"""
    from app.services.my_service import get_something

    doc_b = {"_id": ObjectId(), "corporate_id": CORP_B_ID, "data": "法人Bの秘密"}
    col = make_filtering_col([doc_b])

    with patch("app.services.my_service.get_database") as mock_get_db:
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=col)
        mock_get_db.return_value = mock_db

        # 法人 A として法人 B の doc_id を指定
        result = await get_something(CORP_A_ID, str(doc_b["_id"]))

    assert "error" in result or result is None, "別法人のデータが返ってはいけない"


@pytest.mark.asyncio
async def test_scope_isolation_update():
    """法人 B のドキュメントを法人 A が更新できないこと"""
    from app.services.my_service import update_something

    col = make_filtering_col([])  # 法人 A からは何も見えない
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=0))

    with patch(...):
        result = await update_something(CORP_A_ID, str(ObjectId()))

    # matched_count=0 → エラーまたは not found が返ること
    assert col.update_one.call_args[0][0].get("corporate_id") == CORP_A_ID, \
        "update_one の第1引数に corporate_id フィルタが含まれていること"
```

---

## 2. 不正なIDを渡した場合のエラー処理

```python
@pytest.mark.asyncio
async def test_invalid_object_id():
    """不正な ObjectId 文字列を渡した場合に error が返ること（500 にならないこと）"""
    from app.services.my_service import get_something

    result = await get_something(CORP_A_ID, document_id="not-a-valid-id")

    assert "error" in result
    assert "Invalid" in result["error"] or "invalid" in result["error"].lower()


@pytest.mark.asyncio
async def test_empty_id():
    """空文字を渡した場合も安全に処理されること"""
    from app.services.my_service import get_something

    result = await get_something(CORP_A_ID, document_id="")
    assert "error" in result


@pytest.mark.asyncio
async def test_nonexistent_id():
    """存在しない有効な ObjectId を渡した場合に not found が返ること"""
    from app.services.my_service import get_something

    with patch(...) as mock_get_db:
        # find_one が None を返すよう設定
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=make_col(find_one=None))
        mock_get_db.return_value = mock_db

        result = await get_something(CORP_A_ID, document_id=str(ObjectId()))

    assert "error" in result
    assert "not found" in result["error"].lower()
```

---

## 3. DBへの意図しない書き込みなし確認

**提案系ツール（draft_xxx, suggest_xxx）では必須**。

```python
@pytest.mark.asyncio
async def test_no_db_write_on_suggest():
    """suggest / draft 系ツールが DB に書き込まないこと"""
    from app.services.agent_tools import suggest_journal_entry

    write_col = make_col(find_one={"_id": ObjectId(), "corporate_id": CORP_A_ID, "amount": 1000})

    with patch("app.services.agent_tools.get_database") as mock_get_db:
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=write_col)
        mock_get_db.return_value = mock_db

        result = await suggest_journal_entry(CORP_A_ID, "receipt", str(ObjectId()))

    # 書き込み系メソッドが呼ばれていないことを確認
    write_col.insert_one.assert_not_called()
    write_col.update_one.assert_not_called()
    write_col.delete_one.assert_not_called()

    # 正しくレスポンスが返っていること
    assert "suggested_debit" in result or "error" in result


@pytest.mark.asyncio
async def test_confirmation_required_flag():
    """draft 系ツールが confirmation_required=True を返すこと"""
    from app.services.agent_tools import draft_expense_claim

    result = await draft_expense_claim(
        CORP_A_ID, user_id="user1",
        amount=5000, description="交通費", date_str="2025-04-01"
    )

    assert result.get("confirmation_required") is True
    assert "draft" in result
```

---

## 4. 認証なしアクセスの拒否確認

FastAPI エンドポイントの結合テストで確認する。

```python
from fastapi.testclient import TestClient

def test_unauthenticated_access(client: TestClient):
    """認証ヘッダーなしで 401 または 403 が返ること"""
    response = client.get("/api/v1/receipts")
    assert response.status_code in (401, 403)


def test_wrong_token(client: TestClient):
    """不正なトークンで 401 または 403 が返ること"""
    response = client.get(
        "/api/v1/receipts",
        headers={"Authorization": "Bearer invalid-token-xyz"}
    )
    assert response.status_code in (401, 403)
```

---

## 5. 境界値（上限・下限・ちょうどの値）

```python
@pytest.mark.asyncio
async def test_list_upper_limit():
    """一覧取得が上限件数（20件）を超えて返さないこと"""
    from app.services.agent_tools import get_pending_list

    # 25 件のダミーデータ
    many_docs = [
        {"_id": ObjectId(), "corporate_id": CORP_A_ID, "approval_status": "pending_approval"}
        for _ in range(25)
    ]
    # to_list(length=20) が実際に 20 件に制限するモック
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(side_effect=lambda length=None: many_docs[:length])
    col = make_col()
    col.find = MagicMock(return_value=cursor)

    with patch(...):
        result = await get_pending_list(CORP_A_ID, list_type="receipts")

    assert len(result["receipts"]) <= 20


@pytest.mark.asyncio
async def test_zero_results():
    """データが 0 件の場合に空リストが返ること（エラーにならないこと）"""
    from app.services.agent_tools import get_pending_list

    with patch("app.services.agent_tools.get_database") as mock_get_db:
        col = make_col(find_data=[])
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=col)
        mock_get_db.return_value = mock_db

        result = await get_pending_list(CORP_A_ID)

    assert result["receipts"] == []
    assert result["invoices"] == []
    assert result["total_count"] == 0


def test_amount_boundary():
    """金額 0・負値・最大値の境界テスト"""
    assert calc_something(amount=0) == expected_zero
    assert calc_something(amount=-1) is None or ...  # 仕様による
    assert calc_something(amount=999_999_999) == ...
```

---

## 6. 正規表現インジェクション・特殊文字テスト

**`search_client` のような部分一致検索で必須**。

```python
@pytest.mark.asyncio
async def test_regex_injection_safe():
    """正規表現のメタキャラクタを含むクエリでクラッシュしないこと"""
    from app.services.agent_tools import search_client

    dangerous_inputs = [
        ".*",           # 全件マッチする正規表現
        "(.+)+",        # ReDoS パターン
        "[a-z]+",       # 文字クラス
        "\\d+",         # エスケープシーケンス
        "株式会社(?!)",  # ネガティブ先読み
        "あ" * 500,     # 超長文字列
        "",             # 空文字
        "   ",          # 空白のみ
    ]

    for query in dangerous_inputs:
        col = make_col(find_data=[])
        with patch("app.services.agent_tools.get_database") as mock_get_db:
            mock_db = MagicMock()
            mock_db.__getitem__ = MagicMock(return_value=col)
            mock_get_db.return_value = mock_db

            # クラッシュしないこと（エラーが返っても OK）
            result = await search_client(CORP_A_ID, query=query)
            assert isinstance(result, dict), f"query={query!r} でクラッシュした"


@pytest.mark.asyncio
async def test_special_chars_in_description():
    """description に特殊文字が含まれる場合でも仕訳提案が返ること"""
    from app.services.agent_tools import draft_expense_claim

    special_descs = [
        "タクシー代 $100",
        'カフェ "スターバックス"',
        "改行\nテスト",
        "<script>alert(1)</script>",
    ]
    for desc in special_descs:
        result = await draft_expense_claim(
            CORP_A_ID, "user1", 1000, desc, "2025-04-01"
        )
        assert "error" not in result or "draft" in result, f"desc={desc!r} で失敗"
```

---

## チェックリスト

実装したら以下を全て確認する。

- [ ] 別法人ID で同じ doc_id を指定してデータが返らないこと
- [ ] 不正な ObjectId（"abc", "", "123"）でエラーレスポンスが返ること
- [ ] 存在しない有効 ObjectId で not found が返ること
- [ ] 提案系ツールで insert_one / update_one / delete_one が呼ばれないこと
- [ ] `confirmation_required: True` が含まれること
- [ ] 上限件数（通常 20〜200）を超えて返さないこと
- [ ] 0件時に空リストが返りクラッシュしないこと
- [ ] 正規表現メタキャラクタを含むクエリでクラッシュしないこと
- [ ] 認証なしで 401/403 が返ること（エンドポイントテスト）
