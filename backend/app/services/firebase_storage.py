"""
Firebase Storage のファイル操作サービス。
アップロード・署名付きURL生成・削除を提供する。
"""
import asyncio
import logging
from typing import Optional
from datetime import timedelta
from firebase_admin import storage
from app.core.config import settings

logger = logging.getLogger(__name__)


def get_bucket():
    return storage.bucket(settings.FIREBASE_STORAGE_BUCKET)


async def generate_signed_url(
    file_path: str,
    expiration_minutes: int = 60,
) -> Optional[str]:
    """
    ファイルの署名付きURLを生成する。有効期限はデフォルト60分。
    Storage 操作は同期ライブラリのため run_in_executor でラップする。
    """
    try:
        bucket = get_bucket()
        loop = asyncio.get_event_loop()
        blob = bucket.blob(file_path)

        exists = await loop.run_in_executor(None, blob.exists)
        if not exists:
            return None

        url = await loop.run_in_executor(
            None,
            lambda: blob.generate_signed_url(
                expiration=timedelta(minutes=expiration_minutes),
                method="GET",
            ),
        )
        return url
    except Exception as e:
        logger.error(
            f"[firebase_storage] 署名付きURL生成失敗: {file_path} error={e}",
            exc_info=True,
        )
        return None


async def delete_file(file_path: str) -> bool:
    """
    ファイルを削除する。
    電子帳簿保存法の観点から承認済みファイルは削除しない。
    呼び出し元で approval_status を確認してから呼ぶこと。
    """
    try:
        bucket = get_bucket()
        loop = asyncio.get_event_loop()
        blob = bucket.blob(file_path)

        exists = await loop.run_in_executor(None, blob.exists)
        if exists:
            await loop.run_in_executor(None, blob.delete)
            logger.info(f"[firebase_storage] 削除成功: {file_path}")
        return True
    except Exception as e:
        logger.error(
            f"[firebase_storage] 削除失敗: {file_path} error={e}",
            exc_info=True,
        )
        return False
