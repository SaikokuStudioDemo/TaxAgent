"""
system_settings API
プラン・オプション・AI クレジット上限・手数料率などのシステム設定を管理する。
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, verify_admin
from app.db.mongodb import get_database

logger = logging.getLogger(__name__)
router = APIRouter()

DEFAULT_PLANS: List[Dict[str, Any]] = [
    {
        "id": "plan_basic",
        "name": "ベーシックプラン",
        "price": 30000,
        "max_client_corporates": 3,
        "max_users_per_corporate": 5,
        "features": [
            "基本機能一式",
            "AIチャット",
            "月間データ処理",
        ],
        "is_active": True,
    },
    {
        "id": "plan_standard",
        "name": "スタンダードプラン",
        "price": 50000,
        "max_client_corporates": 10,
        "max_users_per_corporate": 15,
        "features": [
            "基本機能一式",
            "AIチャット",
            "全銀データ出力",
            "高度なアラート・自動通知",
            "予算管理・対比レポート",
            "テンプレート機能",
        ],
        "is_active": True,
    },
    {
        "id": "plan_premium",
        "name": "プレミアムプラン",
        "price": 100000,
        "max_client_corporates": -1,
        "max_users_per_corporate": -1,
        "features": [
            "基本機能一式",
            "AIチャット",
            "全銀データ出力",
            "高度なアラート・自動通知",
            "予算管理・対比レポート",
            "テンプレート機能",
            "Law Agent（税務QA）",
            "税理士エスカレーション",
            "会計ソフト別CSV",
            "優先サポート",
        ],
        "is_active": True,
    },
]

DEFAULT_FEE_RATE: float = 0.20

DEFAULT_JOURNAL_MAP: Dict[str, Any] = {
    "旅費交通費": {
        "debit": "旅費交通費", "credit": "未払金", "tax_category": "課税仕入 10%",
        "keywords": ["タクシー", "電車", "バス", "交通", "出張", "新幹線", "飛行機", "高速", "駐車", "乗車", "定期"],
    },
    "会議費": {
        "debit": "会議費", "credit": "未払金", "tax_category": "課税仕入 10%",
        "keywords": ["会議", "打ち合わせ", "ミーティング", "会議室", "セミナー", "研修", "勉強会"],
    },
    "消耗品費": {
        "debit": "消耗品費", "credit": "未払金", "tax_category": "課税仕入 10%",
        "keywords": ["文具", "コピー用紙", "インク", "トナー", "事務用品", "消耗品", "備品"],
    },
    "交際費": {
        "debit": "交際費", "credit": "未払金", "tax_category": "課税仕入 10%",
        "keywords": ["接待", "飲食", "食事", "ランチ", "ディナー", "贈答", "お土産", "慶弔"],
    },
    "通信費": {
        "debit": "通信費", "credit": "未払金", "tax_category": "課税仕入 10%",
        "keywords": ["電話", "携帯", "スマホ", "インターネット", "回線", "郵便", "宅配", "配送", "切手"],
    },
    "水道光熱費": {
        "debit": "水道光熱費", "credit": "未払金", "tax_category": "課税仕入 10%",
        "keywords": ["電気", "ガス", "水道", "光熱", "電力"],
    },
    "地代家賃": {
        "debit": "地代家賃", "credit": "未払金", "tax_category": "課税仕入 10%",
        "keywords": ["家賃", "地代", "賃料", "テナント", "オフィス", "駐車場代"],
    },
    "広告宣伝費": {
        "debit": "広告宣伝費", "credit": "未払金", "tax_category": "課税仕入 10%",
        "keywords": ["広告", "宣伝", "PR", "チラシ", "パンフレット", "ウェブ", "SNS", "マーケティング"],
    },
    "支払手数料": {
        "debit": "支払手数料", "credit": "未払金", "tax_category": "課税仕入 10%",
        "keywords": ["手数料", "振込手数料", "決済手数料", "仲介手数料", "代行", "委託"],
    },
    "外注費": {
        "debit": "外注費", "credit": "未払金", "tax_category": "課税仕入 10%",
        "keywords": ["外注", "業務委託", "フリーランス", "委託", "制作", "開発", "デザイン", "ライティング"],
    },
    "福利厚生費": {
        "debit": "福利厚生費", "credit": "未払金", "tax_category": "課税仕入 10%",
        "keywords": ["福利厚生", "健康診断", "社員旅行", "忘年会", "懇親会", "慰安", "スポーツ"],
    },
    "新聞図書費": {
        "debit": "新聞図書費", "credit": "未払金", "tax_category": "課税仕入 10%",
        "keywords": ["書籍", "雑誌", "新聞", "電子書籍", "図書", "サブスクリプション"],
    },
    "車両費": {
        "debit": "車両費", "credit": "未払金", "tax_category": "課税仕入 10%",
        "keywords": ["ガソリン", "駐車場", "高速道路", "ETC", "自動車", "車検", "整備", "洗車"],
    },
    "保険料": {
        "debit": "保険料", "credit": "未払金", "tax_category": "非課税",
        "keywords": ["保険", "損害保険", "生命保険", "火災保険", "自動車保険"],
    },
    "修繕費": {
        "debit": "修繕費", "credit": "未払金", "tax_category": "課税仕入 10%",
        "keywords": ["修繕", "修理", "メンテナンス", "補修", "改修"],
    },
    "雑費": {
        "debit": "雑費", "credit": "未払金", "tax_category": "課税仕入 10%",
        "keywords": ["その他", "雑費", "雑"],
    },
}

_REQUIRED_ENTRY_KEYS = {"debit", "credit", "tax_category", "keywords"}


def _validate_journal_map_entry(subject_name: str, entry: Any) -> None:
    if not isinstance(entry, dict):
        raise HTTPException(status_code=400, detail=f'"{subject_name}" の値はオブジェクトである必要があります')
    missing = _REQUIRED_ENTRY_KEYS - set(entry.keys())
    if missing:
        raise HTTPException(status_code=400, detail=f'"{subject_name}" に必須フィールドが不足しています: {", ".join(missing)}')
    if not isinstance(entry.get("keywords"), list):
        raise HTTPException(status_code=400, detail=f'"{subject_name}".keywords は配列である必要があります')
    if len(entry["keywords"]) == 0:
        raise HTTPException(status_code=400, detail=f'"{subject_name}".keywords は1件以上必要です')


def _validate_plan(plan: Any, idx: int) -> None:
    if not isinstance(plan, dict):
        raise HTTPException(status_code=400, detail=f"plans[{idx}] はオブジェクトである必要があります")
    if not plan.get("id") or not isinstance(plan.get("id"), str):
        raise HTTPException(status_code=400, detail=f"plans[{idx}].id は必須の文字列です")
    if not plan.get("name") or not isinstance(plan.get("name"), str):
        raise HTTPException(status_code=400, detail=f"plans[{idx}].name は必須の文字列です")
    price = plan.get("price")
    if not isinstance(price, int) or isinstance(price, bool) or price < 0:
        raise HTTPException(status_code=400, detail=f"plans[{idx}].price は 0 以上の整数である必要があります")
    for field in ("max_client_corporates", "max_users_per_corporate"):
        val = plan.get(field)
        if val is None:
            continue
        if not isinstance(val, int) or isinstance(val, bool) or (val != -1 and val < 1):
            raise HTTPException(
                status_code=400,
                detail=f"plans[{idx}].{field} は -1（無制限）または 1 以上の整数である必要があります",
            )


# ─────────────────────────────────────────────────────────────────────────────
# 公開エンドポイント（認証不要）
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/plans", summary="プラン一覧を取得する（認証不要）")
async def get_plans():
    db = get_database()
    doc = await db["system_settings"].find_one({"key": "plans"})
    if doc and isinstance(doc.get("value"), list) and doc["value"]:
        return [p for p in doc["value"] if p.get("is_active", True) is not False]
    return DEFAULT_PLANS


@router.get("/options", summary="オプション一覧を取得する（認証不要）")
async def get_options():
    db = get_database()
    doc = await db["system_settings"].find_one({"key": "options"})
    if doc and isinstance(doc.get("value"), list):
        return doc["value"]
    return []


@router.get("/fee-rate", summary="手数料率を取得する（認証不要）")
async def get_fee_rate():
    db = get_database()
    doc = await db["system_settings"].find_one({"key": "platform_fee_rate"})
    if doc and isinstance(doc.get("value"), (int, float)):
        return {"platform_fee_rate": float(doc["value"])}
    return {"platform_fee_rate": DEFAULT_FEE_RATE}


# ─────────────────────────────────────────────────────────────────────────────
# Admin 専用エンドポイント
# ─────────────────────────────────────────────────────────────────────────────

@router.put("/plans", summary="プラン一覧を更新する（Admin のみ）")
async def update_plans(
    body: Dict[str, Any],
    current_user: dict = Depends(verify_admin),
):
    plans = body.get("plans")
    if not isinstance(plans, list) or len(plans) == 0:
        raise HTTPException(status_code=400, detail="plans は1件以上のリストである必要があります")
    for i, plan in enumerate(plans):
        _validate_plan(plan, i)

    db = get_database()
    await db["system_settings"].update_one(
        {"key": "plans"},
        {"$set": {
            "key": "plans",
            "value": plans,
            "updated_by": current_user.get("uid"),
            "updated_at": datetime.utcnow(),
        }},
        upsert=True,
    )
    return {"status": "updated", "plans": plans}


@router.put("/fee-rate", summary="手数料率を更新する（Admin のみ）")
async def update_fee_rate(
    body: Dict[str, Any],
    current_user: dict = Depends(verify_admin),
):
    rate = body.get("platform_fee_rate")
    if rate is None:
        raise HTTPException(status_code=400, detail="platform_fee_rate は必須です")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)):
        raise HTTPException(status_code=400, detail="platform_fee_rate は数値である必要があります")
    if isinstance(rate, int):
        # 整数は 0〜100 のパーセント表記として受け取りラシオに変換
        if not (0 <= rate <= 100):
            raise HTTPException(status_code=400, detail="整数で指定する場合は 0〜100 の範囲で指定してください")
        rate = rate / 100
    else:
        rate = float(rate)
        if not (0.0 <= rate <= 1.0):
            raise HTTPException(status_code=400, detail="platform_fee_rate は 0.0〜1.0 の範囲で指定してください")

    db = get_database()
    await db["system_settings"].update_one(
        {"key": "platform_fee_rate"},
        {"$set": {
            "key": "platform_fee_rate",
            "value": rate,
            "updated_by": current_user.get("uid"),
            "updated_at": datetime.utcnow(),
        }},
        upsert=True,
    )
    return {"platform_fee_rate": rate}


# ─────────────────────────────────────────────────────────────────────────────
# 認証必須エンドポイント（税理士法人 or Admin）
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/law-agent-url", summary="Law Agent URL を取得する（Admin のみ）")
async def get_law_agent_url_setting(
    current_user: dict = Depends(verify_admin),
):
    from app.core.config import settings as _settings

    db = get_database()
    doc = await db["system_settings"].find_one({"key": "law_agent_url"})
    if doc and doc.get("value"):
        return {"law_agent_url": doc["value"]}
    return {"law_agent_url": _settings.LAW_AGENT_URL}


@router.put("/law-agent-url", summary="Law Agent URL を更新する（Admin のみ）")
async def update_law_agent_url(
    body: Dict[str, Any],
    current_user: dict = Depends(verify_admin),
):
    url = body.get("law_agent_url")
    if not url or not isinstance(url, str) or not url.strip():
        raise HTTPException(status_code=400, detail="law_agent_url は必須です")
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(
            status_code=400,
            detail="law_agent_url は http:// または https:// で始まる必要があります",
        )

    db = get_database()
    await db["system_settings"].update_one(
        {"key": "law_agent_url"},
        {"$set": {
            "key": "law_agent_url",
            "value": url,
            "updated_by": current_user.get("uid"),
            "updated_at": datetime.utcnow(),
        }},
        upsert=True,
    )
    return {"law_agent_url": url}


@router.get("/ai-credit-limits", summary="AIクレジット上限設定を取得する（Admin のみ）")
async def get_ai_credit_limits(
    current_user: dict = Depends(get_current_user),
):
    from app.db.mongodb import get_database as _get_db

    firebase_uid = current_user.get("uid")
    db = _get_db()

    caller = await db["corporates"].find_one({"firebase_uid": firebase_uid})
    if not caller:
        employee = await db["employees"].find_one({"firebase_uid": firebase_uid})
        if not employee or employee.get("role") != "admin":
            raise HTTPException(status_code=403, detail="管理者権限が必要です")
    elif caller.get("corporateType") != "tax_firm":
        raise HTTPException(status_code=403, detail="管理者権限が必要です")

    doc = await db["system_settings"].find_one({"key": "ai_credit_limits"})
    if doc and isinstance(doc.get("value"), dict):
        return doc["value"]
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# 勘定科目マスター
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/journal-map", summary="勘定科目マスターを取得する（認証不要）")
async def get_journal_map():
    db = get_database()
    doc = await db["system_settings"].find_one({"key": "journal_map"})
    if doc and isinstance(doc.get("value"), dict) and doc["value"]:
        return doc["value"]
    return DEFAULT_JOURNAL_MAP


@router.get("/alert-settings", summary="プラットフォーム全体のアラート設定を取得する（Admin のみ）")
async def get_alert_settings(
    current_user: dict = Depends(verify_admin),
):
    from app.services.alert_service import DEFAULT_ALERT_SETTINGS

    db = get_database()
    doc = await db["system_settings"].find_one({"key": "alert_settings"})
    result = DEFAULT_ALERT_SETTINGS.copy()
    if doc and isinstance(doc.get("value"), dict):
        result.update({k: v for k, v in doc["value"].items() if k in DEFAULT_ALERT_SETTINGS})
    return result


@router.put("/alert-settings", summary="プラットフォーム全体のアラート設定を更新する（Admin のみ）")
async def update_alert_settings(
    body: Dict[str, Any],
    current_user: dict = Depends(verify_admin),
):
    from app.services.alert_service import DEFAULT_ALERT_SETTINGS

    update: Dict[str, Any] = {}
    for k, v in body.items():
        if k not in DEFAULT_ALERT_SETTINGS:
            raise HTTPException(status_code=400, detail=f"無効なキーです: {k}")
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise HTTPException(status_code=400, detail=f"{k} は1以上の整数である必要があります")
        update[k] = v

    if not update:
        raise HTTPException(status_code=400, detail="更新するデータがありません")

    db = get_database()
    await db["system_settings"].update_one(
        {"key": "alert_settings"},
        {"$set": {
            "key": "alert_settings",
            "value": update,
            "updated_by": current_user.get("uid"),
            "updated_at": datetime.utcnow(),
        }},
        upsert=True,
    )
    return {"status": "updated", **update}


@router.get("/tax-rates", summary="税率設定を取得する（認証不要）")
async def get_tax_rates():
    from app.services.alert_service import DEFAULT_TAX_RATES

    db = get_database()
    doc = await db["system_settings"].find_one({"key": "tax_rates"})
    result = DEFAULT_TAX_RATES.copy()
    if doc and isinstance(doc.get("value"), dict):
        result.update({k: v for k, v in doc["value"].items() if k in DEFAULT_TAX_RATES})
    return result


@router.put("/tax-rates", summary="税率設定を更新する（Admin のみ）")
async def update_tax_rates(
    body: Dict[str, Any],
    current_user: dict = Depends(verify_admin),
):
    from app.services.alert_service import DEFAULT_TAX_RATES

    update: Dict[str, int] = {}
    for key in ("standard", "reduced", "exempt"):
        if key not in body:
            continue
        v = body[key]
        if isinstance(v, bool):
            raise HTTPException(status_code=400, detail=f"{key} は整数である必要があります（bool は不可）")
        if not isinstance(v, int):
            raise HTTPException(status_code=400, detail=f"{key} は整数である必要があります")
        if not (0 <= v <= 100):
            raise HTTPException(status_code=400, detail=f"{key} は0以上100以下の整数である必要があります")
        update[key] = v

    if not update:
        raise HTTPException(status_code=400, detail="更新するデータがありません")

    # 既存の値とデフォルトをマージして全キーを保持する
    db = get_database()
    existing_doc = await db["system_settings"].find_one({"key": "tax_rates"})
    merged = DEFAULT_TAX_RATES.copy()
    if existing_doc and isinstance(existing_doc.get("value"), dict):
        merged.update({k: v for k, v in existing_doc["value"].items() if k in DEFAULT_TAX_RATES})
    merged.update(update)

    await db["system_settings"].update_one(
        {"key": "tax_rates"},
        {"$set": {
            "key": "tax_rates",
            "value": merged,
            "updated_by": current_user.get("uid"),
            "updated_at": datetime.utcnow(),
        }},
        upsert=True,
    )
    return merged


@router.put("/journal-map", summary="勘定科目マスターを更新する（Admin のみ）")
async def update_journal_map(
    body: Dict[str, Any],
    current_user: dict = Depends(verify_admin),
):
    journal_map = body.get("journal_map")
    if not isinstance(journal_map, dict) or len(journal_map) == 0:
        raise HTTPException(status_code=400, detail="journal_map は1件以上のオブジェクトである必要があります")
    for subject_name, entry in journal_map.items():
        _validate_journal_map_entry(subject_name, entry)

    db = get_database()
    await db["system_settings"].update_one(
        {"key": "journal_map"},
        {"$set": {
            "key": "journal_map",
            "value": journal_map,
            "updated_by": current_user.get("uid"),
            "updated_at": datetime.utcnow(),
        }},
        upsert=True,
    )
    return {"status": "updated", "journal_map": journal_map}
