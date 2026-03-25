# DEPRECATED: このスクリプトは非推奨です。seed_mock_data.py を使用してください。
"""
run_integration_tests.py - シードデータを使った結合テストスクリプト

pytestのconftest.pyに依存せず、直接実行するスタンドアロンスクリプト。

実行方法:
    cd backend
    PYTHONPATH=. venv/bin/python run_integration_tests.py
"""
import asyncio
import os
import sys
from datetime import datetime
from bson import ObjectId

os.environ["MONGODB_DB_NAME"] = "tax_agent"  # 本番DBを使用

from httpx import AsyncClient, ASGITransport
from motor.motor_asyncio import AsyncIOMotorClient

# DB 初期化
from app.db.mongodb import connect_to_mongo, get_database
from app.api.deps import get_current_user
from app.main import app

CORP_A_UID = "seed_corp_a_uid"
CORP_B_UID = "seed_corp_b_uid"

passed = []
failed = []


def color(text, code):
    return f"\033[{code}m{text}\033[0m"


def ok(msg):
    print(color(f"  ✅ PASS: {msg}", "32"))
    passed.append(msg)


def fail(msg, err):
    print(color(f"  ❌ FAIL: {msg}", "31"))
    print(f"         {err}")
    failed.append(msg)


def override(uid):
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}


async def run_all():
    await connect_to_mongo()
    db = get_database()

    print("\n" + "=" * 60)
    print("🔍 統合テスト開始（シードデータ使用）")
    print("=" * 60)

    # ─────────── 1: データ分離 A社 ───────────
    print("\n[1] データ分離: A社ログインでA社のデータのみ取得")
    try:
        override(CORP_A_UID)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/receipts")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data, list) and len(data) >= 3, f"Expected >=3, got {len(data)}"
        payees = [r.get("payee") for r in data]
        assert "B社の取引先" not in payees, "B社のデータが混入"
        ok(f"A社に {len(data)} 件の領収書（B社なし）")
    except Exception as e:
        fail("データ分離 A社", e)

    # ─────────── 2: データ分離 B社 ───────────
    print("\n[2] データ分離: B社ログインでB社のデータのみ取得")
    try:
        override(CORP_B_UID)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/receipts")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data) == 1, f"B社は1件のはず。実際: {len(data)}"
        assert data[0]["payee"] == "B社の取引先"
        ok(f"B社に {len(data)} 件（自社データのみ）")
    except Exception as e:
        fail("データ分離 B社", e)

    # ─────────── 3: 高額ルール自動適用 ───────────
    print("\n[3] 承認ルール: 高額領収書にルールが自動設定される")
    try:
        override(CORP_A_UID)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/receipts")
        receipts = resp.json()
        high = next((r for r in receipts if r.get("amount") == 85000), None)
        assert high is not None, "¥85,000の領収書が見つかりません"
        assert high.get("approval_rule_id") is not None, "ルールが未設定"
        ok(f"高額(¥85,000)にrule_id={high['approval_rule_id'][:8]}...が設定")
    except Exception as e:
        fail("高額ルール自動適用", e)

    # ─────────── 4: 低額ルールなし ───────────
    print("\n[4] 承認ルール: 低額領収書にはルールが設定されない")
    try:
        override(CORP_A_UID)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/receipts")
        receipts = resp.json()
        low = next((r for r in receipts if r.get("amount") == 3500), None)
        assert low is not None, "¥3,500の領収書が見つかりません"
        assert low.get("approval_rule_id") is None, "低額にルールが誤設定"
        ok("低額(¥3,500)はrule_idなし")
    except Exception as e:
        fail("低額ルールなし", e)

    # ─────────── 5-7: アラート ───────────
    print("\n[5-7] アラート: 期限切れ / 3日前 / 高額")
    try:
        override(CORP_A_UID)
        corp = await db["corporates"].find_one({"firebase_uid": CORP_A_UID})
        corp_id = str(corp["_id"])
        await db["notifications"].delete_many({"corporate_id": corp_id})
        await db["receipts"].update_many({"corporate_id": corp_id}, {"$set": {"high_amount_alerted": False}})
        await db["invoices"].update_many({"corporate_id": corp_id}, {"$set": {"high_amount_alerted": False}})

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/admin/run-alerts")
        assert resp.status_code == 200, resp.text
        result = resp.json()["results"]

        notes = await db["notifications"].find({"corporate_id": corp_id}).to_list(50)
        types = [n["type"] for n in notes]

        assert result["overdue"] >= 1, f"期限切れアラートなし: {result}"
        assert result["due_soon"] >= 1, f"3日前アラートなし: {result}"
        assert result["high_amount_flagged"] >= 1, f"高額アラートなし: {result}"
        ok(f"overdue={result['overdue']}, due_soon={result['due_soon']}, high={result['high_amount_flagged']}")
        ok(f"通知種別: {types}")
    except Exception as e:
        fail("アラート生成", e)

    # ─────────── 8: 承認 step1 → step2 ───────────
    print("\n[8] 承認フロー: step1承認でcurrent_stepが2に進む")
    try:
        override(CORP_A_UID)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            cr = await ac.post("/api/v1/receipts", json={
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "amount": 45000, "tax_rate": 10,
                "payee": "Step進行テスト", "category": "消耗品費",
                "payment_method": "立替",
                "fiscal_period": datetime.utcnow().strftime("%Y-%m"),
            })
            rid = cr.json()["id"]
            assert cr.json().get("approval_rule_id"), "ルール未設定"
            await ac.post("/api/v1/approvals/actions", json={
                "document_type": "receipt", "document_id": rid,
                "step": 1, "approver_id": "tester", "action": "approved",
            })
        updated = await db["receipts"].find_one({"_id": ObjectId(rid)})
        assert updated["current_step"] == 2, f"step={updated['current_step']}"
        assert updated["approval_status"] == "pending_approval"
        ok(f"step1承認後: current_step={updated['current_step']}, approval_status={updated['approval_status']}")
    except Exception as e:
        fail("承認 step1→step2", e)

    # ─────────── 9: 完全承認 ───────────
    print("\n[9] 承認フロー: step1+step2で完全承認（approved）")
    try:
        override(CORP_A_UID)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            cr = await ac.post("/api/v1/receipts", json={
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "amount": 60000, "tax_rate": 10,
                "payee": "完全承認テスト", "category": "設備費",
                "payment_method": "法人カード",
                "fiscal_period": datetime.utcnow().strftime("%Y-%m"),
            })
            rid = cr.json()["id"]
            for step in [1, 2]:
                await ac.post("/api/v1/approvals/actions", json={
                    "document_type": "receipt", "document_id": rid,
                    "step": step, "approver_id": f"approver_{step}", "action": "approved",
                })
        final = await db["receipts"].find_one({"_id": ObjectId(rid)})
        assert final["approval_status"] == "approved"
        ok(f"完全承認: approval_status={final['approval_status']}")
    except Exception as e:
        fail("完全承認", e)

    # ─────────── 10: マッチング ───────────
    print("\n[10] マッチング: 銀行明細と領収書を消込")
    try:
        override(CORP_A_UID)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            await ac.post("/api/v1/bank-transactions", json={
                "source_type": "bank", "account_name": "三井住友銀行",
                "transactions": [{
                    "transaction_date": datetime.utcnow().strftime("%Y-%m-%d"),
                    "description": "マッチングテスト株式会社",
                    "amount": 33000, "transaction_type": "debit",
                }],
            })
            cr = await ac.post("/api/v1/receipts", json={
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "amount": 33000, "tax_rate": 10,
                "payee": "マッチングテスト株式会社", "category": "消耗品費",
                "payment_method": "銀行振込",
                "fiscal_period": datetime.utcnow().strftime("%Y-%m"),
            })
            rid = cr.json()["id"]
            await db["receipts"].update_one({"_id": ObjectId(rid)}, {"$set": {"status": "approved"}})

            txn_resp = await ac.get("/api/v1/bank-transactions?status=unmatched")
            tlist = txn_resp.json()
            tid = next((t["id"] for t in tlist if "マッチングテスト" in t.get("description", "")), None)
            assert tid

            mr = await ac.post("/api/v1/matches", json={
                "match_type": "receipt",
                "transaction_ids": [tid], "document_ids": [rid],
                "matched_by": "manual",
                "fiscal_period": datetime.utcnow().strftime("%Y-%m"),
            })
        assert mr.status_code == 200, mr.text
        match = mr.json()
        assert match["difference"] == 0
        txn = await db["bank_transactions"].find_one({"_id": ObjectId(tid)})
        rcpt = await db["receipts"].find_one({"_id": ObjectId(rid)})
        assert txn["status"] == "matched"
        assert rcpt["status"] == "matched"
        ok(f"マッチング成功: 差額=¥{match['difference']}, 明細={txn['status']}, 領収書={rcpt['status']}")
    except Exception as e:
        fail("マッチング", e)

    # ─────────── 結果サマリー ───────────
    print("\n" + "=" * 60)
    total = len(passed) + len(failed)
    print(color(f"📊 テスト結果: {len(passed)}/{total} PASSED", "32" if not failed else "33"))
    if failed:
        print(color(f"\n❌ 失敗したテスト:", "31"))
        for f in failed:
            print(f"   - {f}")
    else:
        print(color("🎉 全テスト合格！", "32"))
    print("=" * 60 + "\n")

    return len(failed) == 0


if __name__ == "__main__":
    success = asyncio.run(run_all())
    sys.exit(0 if success else 1)
