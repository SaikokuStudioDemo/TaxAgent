"""
Stripe Webhook エンドポイント。
POST /webhook/stripe
署名検証必須。
/api/v1 プレフィックスなしで登録すること（main.py 参照）。
"""
import logging
from datetime import datetime

import stripe
from fastapi import APIRouter, HTTPException, Request

from app.db.mongodb import get_database
from app.services.stripe_service import construct_webhook_event

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/stripe", summary="Stripe Webhook を受信する")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    # ─── シグネチャ検証 ────────────────────────────────────────────────
    try:
        event = construct_webhook_event(payload, sig_header)
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"[Webhook] イベント構築失敗: {e}")
        raise HTTPException(status_code=400, detail="Webhook error")

    db = get_database()
    event_type = event["type"]
    data = event["data"]["object"]

    logger.info(f"[Webhook] received: {event_type}")

    try:
        if event_type == "invoice.payment_succeeded":
            # 決済成功 → is_active=True
            sub_id = data.get("subscription")
            if sub_id:
                await db["corporates"].update_one(
                    {"stripe_subscription_id": sub_id},
                    {"$set": {"is_active": True, "updated_at": datetime.utcnow()}},
                )
                logger.info(f"[Webhook] payment_succeeded sub={sub_id}")

        elif event_type == "invoice.payment_failed":
            # 決済失敗 → 通知（プレースホルダー）
            sub_id = data.get("subscription")
            customer_id = data.get("customer")
            logger.warning(
                f"[Webhook] payment_failed sub={sub_id} customer={customer_id}"
            )
            # TODO: Task#47 メール送信実装後に通知処理を追加

        elif event_type == "customer.subscription.updated":
            # プラン変更 → planId 更新（metadata に plan_id が含まれる場合のみ）
            sub_id = data.get("id")
            plan_id = data.get("metadata", {}).get("plan_id")
            if sub_id and plan_id:
                await db["corporates"].update_one(
                    {"stripe_subscription_id": sub_id},
                    {"$set": {"planId": plan_id, "updated_at": datetime.utcnow()}},
                )
                logger.info(
                    f"[Webhook] subscription.updated sub={sub_id} plan={plan_id}"
                )

        elif event_type == "customer.subscription.deleted":
            # 解約 → is_active=False・subscription_id をクリア
            sub_id = data.get("id")
            if sub_id:
                await db["corporates"].update_one(
                    {"stripe_subscription_id": sub_id},
                    {
                        "$set": {
                            "is_active": False,
                            "stripe_subscription_id": None,
                            "updated_at": datetime.utcnow(),
                        }
                    },
                )
                logger.info(f"[Webhook] subscription.deleted sub={sub_id}")

        elif event_type == "payment_intent.succeeded":
            # 銀行振込確認 → is_active=True
            customer_id = data.get("customer")
            if customer_id:
                await db["corporates"].update_one(
                    {"stripe_customer_id": customer_id},
                    {"$set": {"is_active": True, "updated_at": datetime.utcnow()}},
                )
                logger.info(
                    f"[Webhook] payment_intent.succeeded customer={customer_id}"
                )

    except Exception as e:
        # Webhook 処理エラーはログのみ・200 を返す（Stripe がリトライするため）
        logger.error(f"[Webhook] 処理エラー {event_type}: {e}")

    return {"status": "ok"}
