"""
Stripe連携サービス。
Customer作成・Subscription管理を担当。
APIキーは環境変数から取得する。

注意事項：
- Stripe Python SDK は同期 API のため asyncio.to_thread でラップする。
- STRIPE_SECRET_KEY が未設定の場合、各関数は None / False を返す（クラッシュしない）。
- StripeError は内部でキャッチしてログのみ（呼び出し元をロールバックしない）。
"""
import asyncio
import logging
from typing import Optional

import stripe

from app.core.config import settings

logger = logging.getLogger(__name__)

# pydantic-settings 経由で .env を読み込む（os.getenv() は .env を参照しないため）
stripe.api_key = settings.STRIPE_SECRET_KEY

# 起動時に STRIPE_WEBHOOK_SECRET が未設定の場合は警告ログ
if not settings.STRIPE_WEBHOOK_SECRET:
    logger.warning(
        "[Stripe] STRIPE_WEBHOOK_SECRET が未設定です。"
        "Webhook の署名検証が機能しません。"
    )


async def create_stripe_customer(
    firebase_uid: str,
    email: str,
    name: str,
) -> Optional[str]:
    """
    Stripe Customer を作成して stripe_customer_id を返す。
    失敗しても例外を外に漏らさない（ログのみ）。
    """
    try:
        # ② asyncio.to_thread で同期 SDK をラップ
        customer = await asyncio.to_thread(
            stripe.Customer.create,
            email=email,
            name=name,
            metadata={"firebase_uid": firebase_uid},
        )
        return customer.id
    except stripe.StripeError as e:
        logger.error(f"[Stripe] Customer作成失敗 uid={firebase_uid}: {e}")
        return None


async def create_subscription(
    stripe_customer_id: str,
    price_id: str,
) -> Optional[str]:
    """
    Stripe Subscription を作成して subscription_id を返す。
    price_id は Stripe ダッシュボードで作成した Price の ID。
    """
    try:
        subscription = await asyncio.to_thread(
            stripe.Subscription.create,
            customer=stripe_customer_id,
            items=[{"price": price_id}],
            payment_behavior="default_incomplete",
            expand=["latest_invoice.payment_intent"],
        )
        return subscription.id
    except stripe.StripeError as e:
        logger.error(
            f"[Stripe] Subscription作成失敗 customer={stripe_customer_id}: {e}"
        )
        return None


async def cancel_subscription(
    stripe_subscription_id: str,
) -> bool:
    """
    Stripe Subscription をキャンセルする。
    """
    try:
        await asyncio.to_thread(
            stripe.Subscription.cancel,
            stripe_subscription_id,
        )
        return True
    except stripe.StripeError as e:
        logger.error(
            f"[Stripe] Subscription解約失敗 sub={stripe_subscription_id}: {e}"
        )
        return False


def construct_webhook_event(payload: bytes, sig_header: str):
    """
    Webhook シグネチャを検証してイベントを返す。
    同期関数として定義（stripe.Webhook.construct_event は同期のみ対応）。
    """
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )
