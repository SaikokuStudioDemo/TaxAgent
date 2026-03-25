"""
test_integration_seed.py - シードデータを使った結合テスト

このファイルは conftest.py の autouse 系 fixture（clear_db等）の
影響を受けないように独立して動作します。

実行方法:
    cd backend
    PYTHONPATH=. venv/bin/pytest tests/test_integration_seed.py -v -p no:asyncio

または pytest.ini を参照して:
    PYTHONPATH=. venv/bin/pytest tests/test_integration_seed.py -v
"""
import os
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from bson import ObjectId
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient

from app.main import app
from app.api.deps import get_current_user

MONGO_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGODB_DB_NAME", "tax_agent_test")
CORP_A_UID = "seed_corp_a_uid"
CORP_B_UID = "seed_corp_b_uid"

# ─────────── ヘルパー ───────────

def get_test_db():
    client = AsyncIOMotorClient(MONGO_URI)
    return client[DB_NAME]


async def get_corp_id(uid: str) -> str:
    db = get_test_db()
    corp = await db["corporates"].find_one({"firebase_uid": uid})
    assert corp is not None, f"法人が見つかりません: {uid}。先に seed_data.py を実行してください。"
    return str(corp["_id"])


def override_auth(uid: str):
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}


# ─────────── 1: データ分離 - A社は3件のみ ───────────

def test_corp_a_receipts_count():
    override_auth(CORP_A_UID)

    async def run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/receipts")
            assert resp.status_code == 200, f"Error: {resp.text}"
            data = resp.json()
            payees = [r["payee"] for r in data]
            assert "B社の取引先" not in payees, "B社のデータが混入しています！"
            assert len(data) >= 3, f"A社の領収書が3件以上あるはず。実際: {len(data)}"
            print(f"\n✅ データ分離OK: A社 {len(data)} 件、B社なし")

    asyncio.run(run())


# ─────────── 2: データ分離 - B社は1件のみ ───────────

def test_corp_b_sees_only_own_receipts():
    override_auth(CORP_B_UID)

    async def run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/receipts")
            assert resp.status_code == 200, f"Error: {resp.text}"
            data = resp.json()
            assert len(data) == 1, f"B社は1件のみのはず。実際: {len(data)}"
            assert data[0]["payee"] == "B社の取引先"
            print(f"\n✅ データ分離OK: B社 {len(data)} 件のみ")

    asyncio.run(run())


# ─────────── 3: 高額領収書に承認ルールが設定されている ───────────

def test_high_amount_receipt_has_rule():
    override_auth(CORP_A_UID)

    async def run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/receipts")
            receipts = resp.json()
            high = next((r for r in receipts if r.get("amount") == 85000), None)
            assert high is not None, "高額領収書(85000円)が見つかりません"
            assert high["approval_rule_id"] is not None, "規則が設定されていません"
            print(f"\n✅ 高額ルール自動適用OK: rule_id={high['approval_rule_id']}")

    asyncio.run(run())


# ─────────── 4: 低額領収書にはルールなし ───────────

def test_low_amount_receipt_no_rule():
    override_auth(CORP_A_UID)

    async def run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/receipts")
            receipts = resp.json()
            low = next((r for r in receipts if r.get("amount") == 3500), None)
            assert low is not None, "低額領収書(3500円)が見つかりません"
            assert low["approval_rule_id"] is None, "低額にルールが誤って設定されています"
            print(f"\n✅ 低額ルールなしOK")

    asyncio.run(run())


# ─────────── 5-7: アラートテスト ───────────

def test_alert_generation():
    override_auth(CORP_A_UID)

    async def run():
        db = get_test_db()
        corp_id = await get_corp_id(CORP_A_UID)

        # 通知をリセット、高額アラートフラグをリセット
        await db["notifications"].delete_many({"corporate_id": corp_id})
        await db["receipts"].update_many(
            {"corporate_id": corp_id},
            {"$set": {"high_amount_alerted": False}}
        )
        await db["invoices"].update_many(
            {"corporate_id": corp_id},
            {"$set": {"high_amount_alerted": False}}
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/admin/run-alerts")
            assert resp.status_code == 200, f"Error: {resp.text}"
            result = resp.json()["results"]
            print(f"\n⚡ アラート結果: {result}")

        notifications = await db["notifications"].find({"corporate_id": corp_id}).to_list(50)
        types = [n["type"] for n in notifications]
        print(f"   生成された通知種別: {types}")

        assert result["overdue"] >= 1, "期限切れアラートが生成されていません"
        assert result["due_soon"] >= 1, "期限3日前アラートが生成されていません"
        assert result["high_amount_flagged"] >= 1, "高額アラートが生成されていません"
        assert "overdue_alert" in types
        assert "due_date_alert" in types
        assert "high_amount_alert" in types
        print(f"✅ アラートOK: overdue={result['overdue']}, due_soon={result['due_soon']}, high={result['high_amount_flagged']}")

    asyncio.run(run())


# ─────────── 8: 承認step1 → current_step が 2 に ───────────

def test_approval_step1_progression():
    override_auth(CORP_A_UID)

    async def run():
        db = get_test_db()
        corp_id = await get_corp_id(CORP_A_UID)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # 新しい高額領収書を作成（シードデータの汚染を防ぐため）
            create_resp = await ac.post("/api/v1/receipts", json={
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "amount": 45000,
                "tax_rate": 10,
                "payee": "ステップ進行テスト株式会社",
                "category": "消耗品費",
                "payment_method": "立替",
                "fiscal_period": datetime.utcnow().strftime("%Y-%m"),
            })
            receipt = create_resp.json()
            receipt_id = receipt["id"]
            assert receipt["approval_rule_id"] is not None, "ルールが適用されていません"

            # Step 1 承認
            await ac.post("/api/v1/approvals/actions", json={
                "document_type": "receipt",
                "document_id": receipt_id,
                "step": 1,
                "approver_id": "approver_test_1",
                "action": "approved",
            })

        updated = await db["receipts"].find_one({"_id": ObjectId(receipt_id)})
        assert updated["current_step"] == 2
        assert updated["approval_status"] == "pending_approval"
        print(f"\n✅ Step1承認OK: current_step={updated['current_step']}")

    asyncio.run(run())


# ─────────── 9: step1 + step2 → approval_status = approved ───────────

def test_approval_fully_approved():
    override_auth(CORP_A_UID)

    async def run():
        db = get_test_db()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            create_resp = await ac.post("/api/v1/receipts", json={
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "amount": 60000,
                "tax_rate": 10,
                "payee": "完全承認テスト株式会社",
                "category": "設備費",
                "payment_method": "法人カード",
                "fiscal_period": datetime.utcnow().strftime("%Y-%m"),
            })
            receipt_id = create_resp.json()["id"]

            await ac.post("/api/v1/approvals/actions", json={
                "document_type": "receipt", "document_id": receipt_id,
                "step": 1, "approver_id": "approver_1", "action": "approved",
            })
            await ac.post("/api/v1/approvals/actions", json={
                "document_type": "receipt", "document_id": receipt_id,
                "step": 2, "approver_id": "approver_2", "action": "approved",
            })

        final = await db["receipts"].find_one({"_id": ObjectId(receipt_id)})
        assert final["approval_status"] == "approved"
        print(f"\n✅ 完全承認OK: approval_status={final['approval_status']}")

    asyncio.run(run())


# ─────────── 10: マッチングフロー ───────────

def test_matching_flow():
    override_auth(CORP_A_UID)

    async def run():
        db = get_test_db()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # 銀行明細インポート
            import_resp = await ac.post("/api/v1/bank-transactions", json={
                "source_type": "bank",
                "account_name": "三井住友銀行 新宿支店",
                "transactions": [{
                    "transaction_date": datetime.utcnow().strftime("%Y-%m-%d"),
                    "description": "消込テスト株式会社",
                    "amount": 33000,
                    "direction": "debit",
                }],
            })
            assert import_resp.status_code == 200

            # 承認済み領収書を新規作成
            r_resp = await ac.post("/api/v1/receipts", json={
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "amount": 33000,
                "tax_rate": 10,
                "payee": "消込テスト株式会社",
                "category": "消耗品費",
                "payment_method": "銀行振込",
                "fiscal_period": datetime.utcnow().strftime("%Y-%m"),
            })
            rid = r_resp.json()["id"]

            # ステータスを手動で approved に更新してマッチング可能に
            await db["receipts"].update_one(
                {"_id": ObjectId(rid)},
                {"$set": {"status": "approved"}}
            )

            # 明細ID取得
            txn_resp = await ac.get("/api/v1/bank-transactions?status=unmatched")
            transactions = txn_resp.json()
            tid = next(
                (t["id"] for t in transactions if t.get("description") == "消込テスト株式会社"),
                transactions[0]["id"] if transactions else None,
            )
            assert tid is not None

            # マッチング
            match_resp = await ac.post("/api/v1/matches", json={
                "match_type": "receipt",
                "transaction_ids": [tid],
                "document_ids": [rid],
                "matched_by": "manual",
                "fiscal_period": datetime.utcnow().strftime("%Y-%m"),
            })
            assert match_resp.status_code == 200, match_resp.text
            match = match_resp.json()
            assert match["difference"] == 0
            print(f"\n✅ マッチングOK: 差額={match['difference']}円")

        txn = await db["bank_transactions"].find_one({"_id": ObjectId(tid)})
        rcpt = await db["receipts"].find_one({"_id": ObjectId(rid)})
        assert txn["status"] == "matched"
        assert rcpt["status"] == "matched"
        print(f"✅ ステータス更新OK: 明細={txn['status']}, 領収書={rcpt['status']}")

    asyncio.run(run())
