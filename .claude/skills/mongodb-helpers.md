# MongoDB ヘルパー関数リファレンス

`app/api/helpers.py` に定義された共通ヘルパーを必ず使うこと。同じ処理を自前で書かない。

---

## serialize_doc

```python
from app.api.helpers import serialize_doc

def serialize_doc(doc: dict) -> dict
```

**何をするか**: `_id`（ObjectId）→ `id`（str）に変換し、残りの ObjectId フィールドも全て文字列化する。

**使いどころ**: DB から取得したドキュメントをAPIレスポンスとして返す直前に必ず通す。

```python
# ✅ 正しい使い方
doc = await db["receipts"].find_one({"_id": oid})
return serialize_doc(doc)

# 一覧の場合
docs = await cursor.to_list(length=100)
return [serialize_doc(d) for d in docs]
```

**注意**: 破壊的変換（`doc` 自体を変更する）。コピーが必要な場合は `serialize_doc(dict(doc))` とする。

---

## get_doc_or_404

```python
from app.api.helpers import get_doc_or_404

async def get_doc_or_404(
    db,
    collection: str,
    doc_id: str,
    corporate_id: str,
    label: str = "document",
) -> dict
```

**何をするか**: `doc_id`（文字列）→ ObjectId 変換 → `corporate_id` スコープで取得。
- 不正なIDなら HTTP 400
- 見つからなければ HTTP 404

**使いどころ**: 単一ドキュメント取得の標準パターン。`parse_oid` + `find_one` + `None チェック` を全部やってくれる。

```python
# ✅ 推奨パターン
@router.get("/{receipt_id}")
async def get_receipt(
    receipt_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    doc = await get_doc_or_404(ctx.db, "receipts", receipt_id, ctx.corporate_id, "receipt")
    return serialize_doc(doc)

# ❌ アンチパターン（自前で書かない）
oid = ObjectId(receipt_id)  # 例外処理なし → 500になる
doc = await db["receipts"].find_one({"_id": oid})  # corporate_id フィルタなし → スコープ漏洩
```

---

## build_name_map

```python
from app.api.helpers import build_name_map

async def build_name_map(db, user_ids: Set[str]) -> dict
# 戻り値: {"user_id_str": "氏名", ...}
```

**何をするか**: 複数 user_id を一括で名前解決する。`employees` → `corporates` の順で検索。

**使いどころ**: 一覧取得時に `submitted_by` → 名前に変換する。N+1クエリを防ぐため **必ずまとめて呼ぶ**。

```python
# ✅ 正しい使い方（一括取得）
docs = await cursor.to_list(length=100)
submitter_ids: Set[str] = {str(d["submitted_by"]) for d in docs if d.get("submitted_by")}
name_map = await build_name_map(db, submitter_ids)

for doc in docs:
    doc["submitter_name"] = name_map.get(str(doc.get("submitted_by", "")), "不明")

# ❌ アンチパターン（ループ内で都度クエリ）
for doc in docs:
    emp = await db["employees"].find_one({"_id": ObjectId(doc["submitted_by"])})  # N+1
```

---

## enrich_with_approval_history

```python
from app.api.helpers import enrich_with_approval_history

async def enrich_with_approval_history(
    db,
    doc: dict,
    document_id: str,
    document_type,   # str または List[str]
) -> dict
```

**何をするか**: `audit_logs` から承認履歴を時系列で取得し `doc["approval_history"]` に追加する。

**使いどころ**: 詳細取得エンドポイントで承認履歴を付加するとき。

```python
# ✅ 使い方
doc = await get_doc_or_404(ctx.db, "receipts", receipt_id, ctx.corporate_id)
doc = await enrich_with_approval_history(ctx.db, doc, receipt_id, "receipt")
return serialize_doc(doc)

# document_type に複数型を渡す場合
doc = await enrich_with_approval_history(ctx.db, doc, doc_id, ["receipt", "expense"])
```

---

## parse_oid

```python
from app.api.helpers import parse_oid

def parse_oid(doc_id: str, label: str = "document") -> ObjectId
```

**何をするか**: 文字列 → ObjectId 変換。失敗時は HTTP 400 を raise する。

**使いどころ**: `get_doc_or_404` を使えない場面（複数コレクションを自分でクエリするときなど）。

```python
oid = parse_oid(rule_id, "rule")
result = await ctx.db["approval_rules"].update_one(
    {"_id": oid, "corporate_id": ctx.corporate_id},
    {"$set": update_data},
)
```

---

## asyncio.gather での並列取得パターン

**用途**: 互いに依存しない複数クエリを並列実行してレスポンスを高速化する。

```python
import asyncio
from typing import Set

# ✅ Phase 1：独立クエリを並列取得
receipts_raw, invoices_raw, tx_count = await asyncio.gather(
    db["receipts"].find({
        "corporate_id": corporate_id,
        "approval_status": "pending_approval",
        "is_deleted": {"$ne": True},
    }).sort("created_at", 1).to_list(length=20),

    db["invoices"].find({
        "corporate_id": corporate_id,
        "approval_status": "pending_approval",
        "document_type": "received",
    }).sort("created_at", 1).to_list(length=20),

    db["transactions"].count_documents({
        "corporate_id": corporate_id,
        "status": "unmatched",
    }),
)

# ✅ Phase 2：Phase 1 の結果に依存するクエリ（順次実行）
all_docs = receipts_raw + invoices_raw
submitter_ids: Set[str] = {str(d["submitted_by"]) for d in all_docs if d.get("submitted_by")}
name_map = await build_name_map(db, submitter_ids)
```

**注意**: `asyncio.gather` に渡すのは **コルーチン（await 前）** または **awaitableオブジェクト**。
`cursor.to_list(length=N)` は `await` せずに渡す。

---

## aggregate pipeline のよく使うパターン

### カテゴリ別集計

```python
pipeline = [
    {"$match": {
        "corporate_id": corporate_id,
        "fiscal_period": "2025-04",
        "approval_status": {"$ne": "rejected"},
        "is_deleted": {"$ne": True},
    }},
    {"$group": {
        "_id": "$category",
        "total": {"$sum": "$amount"},
        "count": {"$sum": 1},
    }},
    {"$sort": {"total": -1}},
]
results = await db["receipts"].aggregate(pipeline).to_list(length=100)
# results: [{"_id": "交通費", "total": 50000, "count": 3}, ...]
```

### 月次サマリー

```python
pipeline = [
    {"$match": {"corporate_id": corporate_id}},
    {"$group": {
        "_id": "$fiscal_period",
        "total_amount": {"$sum": "$amount"},
        "doc_count": {"$sum": 1},
    }},
    {"$sort": {"_id": -1}},
]
```

### 複数コレクションを並列集計して合算

```python
receipt_agg, invoice_agg = await asyncio.gather(
    db["receipts"].aggregate(receipt_pipeline).to_list(length=100),
    db["invoices"].aggregate(invoice_pipeline).to_list(length=100),
)

# カテゴリ別に合算
totals: Dict[str, int] = {}
for item in receipt_agg + invoice_agg:
    cat = item["_id"] or "未分類"
    totals[cat] = totals.get(cat, 0) + int(item.get("total") or 0)
```

---

## Python 3.9 の型注意事項

```python
# ✅ Python 3.9 対応（必ずこの形式を使う）
from typing import Optional, List, Dict, Any, Set, Tuple

async def my_func(
    corporate_id: str,
    names: Optional[List[str]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ...

# ❌ Python 3.10+ の記法（このプロジェクトでは使えない）
def my_func(corporate_id: str, name: str | None = None) -> dict[str, Any]:  # NG
    ...

def my_func(names: list[str]) -> None:  # NG
    ...
```

**`tuple` の戻り値型も同様**:

```python
# ✅
async def resolve_corporate_id(firebase_uid: str) -> Tuple[str, str]:

# ❌
async def resolve_corporate_id(firebase_uid: str) -> tuple[str, str]:
```
