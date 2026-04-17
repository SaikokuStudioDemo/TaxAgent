from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings


class MongoDB:
    client: AsyncIOMotorClient = None
    db = None


db_ctx = MongoDB()


async def connect_to_mongo():
    print("Connecting to MongoDB...")
    db_ctx.client = AsyncIOMotorClient(settings.MONGODB_URI)
    db_ctx.db = db_ctx.client[settings.MONGODB_DB_NAME]
    print("Connected to MongoDB!")
    # テスト環境（MONGODB_DB_NAME = "tax_agent_test"）では
    # Motor のイベントループバインドが session-scoped と function-scoped の
    # fixture 間で競合するため、インデックス作成をスキップする。
    # 本番・開発環境（tax_agent など）では通常どおり作成する。
    if settings.MONGODB_DB_NAME != "tax_agent_test":
        await create_indexes()


async def create_indexes():
    """各コレクションのインデックスを作成する。"""
    db = db_ctx.db

    # chat_histories：テナント×ユーザー別の時系列クエリ用
    await db["chat_histories"].create_index(
        [("corporate_id", 1), ("user_id", 1), ("created_at", -1)]
    )
    # chat_histories：テナント全体の時系列クエリ用（管理画面等）
    await db["chat_histories"].create_index(
        [("corporate_id", 1), ("created_at", -1)]
    )


async def close_mongo_connection():
    print("Closing MongoDB connection...")
    if db_ctx.client:
        db_ctx.client.close()
    print("MongoDB connection closed.")


def get_database():
    return db_ctx.db
