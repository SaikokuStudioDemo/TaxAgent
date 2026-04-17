# 承認フロー実装パターン

既存実装: `app/api/routes/approvals.py`, `app/services/rule_evaluation_service.py`
関連モデル: `app/models/approval.py`

---

## 全体フロー概要

```
書類提出（receipt / invoice）
  ↓
approval_rule の評価 → approval_rule_id + steps をドキュメントに保存
  ↓
承認者が /approvals/events POST
  ↓
  ├── approved かつ next_step <= total_steps → current_step++ + 次の承認者へ通知
  ├── approved かつ全ステップ完了          → approval_status = "approved"
  └── rejected                             → approval_status = "rejected" + 申請者へ通知
```

---

## 1. ドキュメント提出時の承認ルール解決

```python
from app.services.rule_evaluation_service import evaluate_approval_rules

# 書類提出エンドポイント内で呼ぶ
rule_id, steps = await evaluate_approval_rules(
    corporate_id=ctx.corporate_id,
    document_type="receipt",   # "receipt" | "invoice"
    doc=doc_data,              # amount 等のフィールドを含む dict
)

# 書類ドキュメントに保存
new_doc = {
    **payload.model_dump(),
    "corporate_id": ctx.corporate_id,
    "approval_rule_id": rule_id,      # None の場合もある（ルールなし）
    "approval_status": "pending_approval",
    "current_step": 1,
    "created_at": datetime.utcnow(),
}
```

---

## 2. 承認イベントの記録（audit_logs）

**承認・差戻しの操作は必ず audit_logs に記録する**。

```python
from datetime import datetime

event_doc = {
    "document_id": payload.document_id,
    "document_type": payload.document_type,   # "receipt" | "invoice"
    "action": payload.action,                  # "approved" | "rejected"
    "comment": payload.comment,
    "corporate_id": ctx.corporate_id,
    "approver_id": ctx.user_id,
    "timestamp": datetime.utcnow(),
}
await ctx.db["audit_logs"].insert_one(event_doc)
```

---

## 3. 承認処理（multi-step）

```python
from bson import ObjectId
from app.api.helpers import parse_oid

collection = "receipts" if document_type == "receipt" else "invoices"
doc_oid = parse_oid(document_id, "document")

doc = await ctx.db[collection].find_one({"_id": doc_oid})
current_step = doc.get("current_step", 1)
rule_id = doc.get("approval_rule_id")
next_step = current_step + 1

# ── ステップ数の計算（優先順位あり） ──────────────────────────────────────
total_steps = 1  # 最低 1 ステップ

custom_approvers = doc.get("custom_approvers")
if custom_approvers:
    # 優先 1: custom_approvers（直接設定）
    total_steps = max(total_steps, len(custom_approvers))
elif rule_id:
    # 優先 2: approval_rules コレクション
    try:
        rule = await ctx.db["approval_rules"].find_one({"_id": ObjectId(rule_id)})
        if rule:
            required = [s["step"] for s in rule.get("steps", []) if s.get("required")]
            if required:
                total_steps = max(total_steps, max(required))
    except Exception as e:
        logger.error(f"Rule fetch error: {e}")

# 追加ステップ（動的に追加された extra_approval_steps）
extra_steps = doc.get("extra_approval_steps", [])
total_steps += len(extra_steps)

# ── 承認結果の分岐 ──────────────────────────────────────────────────────────
if next_step <= total_steps:
    # まだ次のステップがある → current_step を進める
    await ctx.db[collection].update_one(
        {"_id": doc_oid, "current_step": current_step},  # 楽観ロック
        {"$set": {"current_step": next_step}},
    )
else:
    # 全ステップ完了 → 承認済みに更新
    await ctx.db[collection].update_one(
        {"_id": doc_oid},
        {"$set": {
            "approval_status": "approved",
            "approved_at": datetime.utcnow(),
        }},
    )
```

---

## 4. 差戻し処理（rejection）

```python
if action == "rejected":
    if not comment:
        raise HTTPException(status_code=400, detail="差戻しの場合はコメントが必要です。")

    await ctx.db[collection].update_one(
        {"_id": doc_oid},
        {"$set": {
            "approval_status": "rejected",
            "rejected_at": datetime.utcnow(),
            "rejection_comment": comment,
        }},
    )

    # 申請者への通知（notification_service 経由）
    from app.services.notification_service import notify_submitter
    await notify_submitter(
        db=ctx.db,
        corporate_id=ctx.corporate_id,
        document_id=document_id,
        document_type=document_type,
        action="rejected",
        comment=comment,
        submitter_id=doc.get("submitted_by", doc.get("created_by", "")),
    )
```

---

## 5. pending_approver の名前解決

```python
from app.api.helpers import enrich_with_approval_history

# 詳細取得エンドポイントで承認履歴と次の承認者を付加する
doc = await get_doc_or_404(ctx.db, collection, document_id, ctx.corporate_id)
doc = await enrich_with_approval_history(ctx.db, doc, document_id, document_type)

# pending_approver の解決
pending_approver = None
rule_id = doc.get("approval_rule_id")
current_step = doc.get("current_step")

if rule_id and current_step is not None:
    try:
        rule = await ctx.db["approval_rules"].find_one({"_id": ObjectId(rule_id)})
        if rule:
            matching_step = next(
                (s for s in rule.get("steps", []) if s.get("step") == current_step),
                None,
            )
            if matching_step:
                approver_role = matching_step.get("role")
                emp = await ctx.db["employees"].find_one({
                    "corporate_id": ctx.corporate_id,
                    "role": approver_role,
                })
                pending_approver = emp.get("name", approver_role) if emp else approver_role
    except Exception as e:
        logger.warning(f"pending_approver lookup failed: {e}")

doc["pending_approver"] = pending_approver
```

---

## 6. 承認履歴の取得（audit_logs）

```python
# 単一ドキュメントの承認履歴
events = await ctx.db["audit_logs"].find(
    {"document_id": document_id, "corporate_id": ctx.corporate_id}
).sort("timestamp", 1).to_list(length=200)

# enrich_with_approval_history を使えば上記を自動でやってくれる
doc = await enrich_with_approval_history(ctx.db, doc, document_id, "receipt")
# → doc["approval_history"] に [{"action": "approved", "approver_id": ..., "timestamp": ...}, ...] が付く
```

---

## 7. approval_status の値と遷移

| 値 | 意味 |
|---|---|
| `pending_approval` | 承認待ち（提出直後） |
| `approved` | 全ステップ承認済み |
| `rejected` | 差戻し |

```python
# フィルタ例
pending_docs = await db["receipts"].find({
    "corporate_id": corporate_id,
    "approval_status": "pending_approval",
    "is_deleted": {"$ne": True},
}).to_list(length=100)
```

---

## 8. よくあるミス

- `current_step` を 1 以外から開始しない（初期値は必ず `1`）
- `audit_logs` への記録を忘れると承認履歴が空になる
- rejection 時にコメント必須チェックを忘れる
- multi-step で `next_step <= total_steps` の判定を逆にする
- `approval_rule_id` が `None` のケース（ルールなし → 1ステップで即承認）を考慮し忘れる
