"""
全銀協コードマスターをMongoDBに取り込むスクリプト。

データソース: https://github.com/zengin-code/source-data
  - data/banks.json          … 金融機関マスター（全件 1 ファイル）
  - data/branches/{code}.json … 支店マスター（銀行コードごとに 1 ファイル）

実行コマンド:
  cd backend
  PYTHONPATH=. venv/bin/python scripts/import_zengin.py
"""

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "tax_agent"

BANKS_URL = "https://raw.githubusercontent.com/zengin-code/source-data/master/data/banks.json"
BRANCH_URL = "https://raw.githubusercontent.com/zengin-code/source-data/master/data/branches/{code}.json"

CONCURRENCY = 20  # 並列ダウンロード数


# ---------------------------------------------------------------------------
# ダウンロードヘルパー
# ---------------------------------------------------------------------------
async def fetch_json(client: httpx.AsyncClient, url: str) -> dict | None:
    try:
        resp = await client.get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  WARN: {url} → {e}", file=sys.stderr)
        return None


async def download_branches(bank_codes: list[str]) -> dict[str, dict]:
    """全銀行の支店データを並列ダウンロードして {bank_code: {branch_code: {...}}} を返す"""
    results: dict[str, dict] = {}
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def fetch_one(client: httpx.AsyncClient, code: str):
        async with semaphore:
            data = await fetch_json(client, BRANCH_URL.format(code=code))
            if data:
                results[code] = data

    limits = httpx.Limits(max_connections=CONCURRENCY, max_keepalive_connections=CONCURRENCY)
    async with httpx.AsyncClient(timeout=30.0, limits=limits) as client:
        tasks = [fetch_one(client, code) for code in bank_codes]
        total = len(tasks)
        done = 0
        for coro in asyncio.as_completed(tasks):
            await coro
            done += 1
            if done % 100 == 0 or done == total:
                print(f"  支店データ取得中: {done}/{total}", flush=True)

    return results


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------
async def main():
    t0 = time.time()
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]

    # ------------------------------------------------------------------
    # 1. 金融機関マスターを取得
    # ------------------------------------------------------------------
    print("▶ 金融機関マスターを取得中...")
    async with httpx.AsyncClient(timeout=30.0) as http:
        banks_raw = await fetch_json(http, BANKS_URL)

    if not banks_raw:
        print("ERROR: banks.json の取得に失敗しました", file=sys.stderr)
        sys.exit(1)

    banks_docs = [
        {
            "code": v["code"],
            "name": v["name"],
            "kana": v.get("kana", ""),
            "hira": v.get("hira", ""),
            "roma": v.get("roma", ""),
        }
        for v in banks_raw.values()
    ]
    print(f"  取得件数: {len(banks_docs)} 件")

    # ------------------------------------------------------------------
    # 2. 支店マスターを取得（並列）
    # ------------------------------------------------------------------
    print("▶ 支店マスターを取得中（並列）...")
    bank_codes = [b["code"] for b in banks_docs]
    branches_by_bank = await download_branches(bank_codes)

    branch_docs = []
    for bank_code, branches in branches_by_bank.items():
        for v in branches.values():
            branch_docs.append(
                {
                    "bank_code": bank_code,
                    "code": v["code"],
                    "name": v["name"],
                    "kana": v.get("kana", ""),
                    "hira": v.get("hira", ""),
                    "roma": v.get("roma", ""),
                }
            )
    print(f"  取得件数: {len(branch_docs)} 件（{len(branches_by_bank)} 金融機関分）")

    # ------------------------------------------------------------------
    # 3. MongoDB に書き込み（既存データをクリアしてから）
    # ------------------------------------------------------------------
    print("▶ MongoDB に取り込み中...")

    # 金融機関
    await db["zengin_banks"].drop()
    if banks_docs:
        await db["zengin_banks"].insert_many(banks_docs)
    await db["zengin_banks"].create_index("code", unique=True)
    await db["zengin_banks"].create_index([("name", "text"), ("kana", "text"), ("hira", "text")])
    print(f"  zengin_banks: {len(banks_docs)} 件 挿入完了")

    # 支店
    await db["zengin_branches"].drop()
    if branch_docs:
        # 大量データなのでチャンク分割して挿入
        chunk_size = 5000
        for i in range(0, len(branch_docs), chunk_size):
            await db["zengin_branches"].insert_many(branch_docs[i:i + chunk_size])
    await db["zengin_branches"].create_index([("bank_code", 1), ("code", 1)], unique=True)
    await db["zengin_branches"].create_index([("bank_code", 1), ("name", "text"), ("kana", "text")])
    print(f"  zengin_branches: {len(branch_docs)} 件 挿入完了")

    elapsed = time.time() - t0
    print(f"\n✅ 完了 ({elapsed:.1f}秒)")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
