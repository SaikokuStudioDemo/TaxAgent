from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import uuid

from firebase_admin import auth as firebase_auth
from app.api.deps import get_current_user
from app.api.helpers import verify_tax_firm
from app.db.mongodb import get_database

router = APIRouter()


class InvitationCreate(BaseModel):
    invited_email: Optional[str] = None


class InvitationAccept(BaseModel):
    token: str


class LinkageRequest(BaseModel):
    tax_firm_email: str


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    payload: InvitationCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    税理士法人が招待トークンを発行する。
    呼び出し元が tax_firm タイプであることを確認する。
    """
    db = get_database()
    firebase_uid = current_user.get("uid")

    if not firebase_uid:
        raise HTTPException(status_code=400, detail="Invalid auth token")

    # 呼び出し元が tax_firm であることを確認
    corporate = await verify_tax_firm(firebase_uid, db)

    token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=7)

    await db["invitations"].insert_one({
        "token": token,
        "tax_firm_id": firebase_uid,
        "invited_email": payload.invited_email or None,
        "status": "pending",
        "expires_at": expires_at,
        "created_at": datetime.utcnow()
    })

    print(f">>> INVITATION CREATED: TAX_FIRM={firebase_uid}, TOKEN={token}")
    return {
        "token": token,
        "expires_at": expires_at.isoformat()
    }


@router.get("/verify", status_code=status.HTTP_200_OK)
async def verify_invitation(token: str):
    """
    招待トークンを検証する。認証不要（公開エンドポイント）。
    """
    db = get_database()

    invitation = await db["invitations"].find_one({"token": token})
    if not invitation:
        return {"valid": False, "reason": "not_found"}

    if invitation.get("status") != "pending":
        return {"valid": False, "reason": "already_used"}

    if invitation.get("expires_at") < datetime.utcnow():
        return {"valid": False, "reason": "expired"}

    return {
        "valid": True,
        "tax_firm_id": invitation.get("tax_firm_id"),
        "invited_email": invitation.get("invited_email")
    }


@router.post("/accept", status_code=status.HTTP_200_OK)
async def accept_invitation(payload: InvitationAccept):
    """
    招待トークンを使用済みにする。認証不要（トークン自体が証明）。
    """
    db = get_database()

    result = await db["invitations"].update_one(
        {"token": payload.token, "status": "pending"},
        {"$set": {"status": "accepted"}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="有効な招待トークンが見つかりません")

    print(f">>> INVITATION ACCEPTED: TOKEN={payload.token}")
    return {"success": True}


@router.post("/linkage-request", status_code=status.HTTP_200_OK)
async def create_linkage_request(
    payload: LinkageRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    法人が税理士法人への紐付けリクエストを送信する。
    呼び出し元が corporateType='corporate' で、
    まだ advising_tax_firm_id が未設定であることを確認する。
    """
    db = get_database()
    corporate_uid = current_user.get("uid")

    if not corporate_uid:
        raise HTTPException(status_code=400, detail="Invalid auth token")

    # 呼び出し元が一般法人であることを確認
    corporate = await db["corporates"].find_one({"firebase_uid": corporate_uid})
    if not corporate or corporate.get("corporateType") != "corporate":
        raise HTTPException(status_code=403, detail="このエンドポイントは一般法人のみ利用できます")

    # 既に紐付けられている場合は拒否
    if corporate.get("advising_tax_firm_id"):
        raise HTTPException(status_code=400, detail="既に税理士法人と紐付けられています")

    # Firebase Auth でメールアドレスから税理士法人のUIDを取得
    try:
        tax_firm_user = firebase_auth.get_user_by_email(payload.tax_firm_email)
        tax_firm_uid = tax_firm_user.uid
    except firebase_auth.UserNotFoundError:
        raise HTTPException(status_code=404, detail="該当する税理士法人が見つかりません")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"メールアドレスの検索に失敗しました: {str(e)}")

    # MongoDBで税理士法人として登録されているか確認
    tax_firm = await db["corporates"].find_one({
        "firebase_uid": tax_firm_uid,
        "corporateType": "tax_firm"
    })
    if not tax_firm:
        raise HTTPException(status_code=404, detail="該当する税理士法人が見つかりません")

    token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=7)

    await db["invitations"].insert_one({
        "token": token,
        "tax_firm_id": tax_firm_uid,
        "corporate_id": corporate_uid,
        "type": "linkage_request",
        "status": "pending",
        "expires_at": expires_at,
        "created_at": datetime.utcnow()
    })

    # 承認URLをコンソールに出力（メール送信の代替）
    approve_url = f"http://localhost:8000/api/v1/invitations/linkage-approve?token={token}"
    print(f">>> LINKAGE REQUEST: CORPORATE={corporate_uid} → TAX_FIRM={tax_firm_uid}")
    print(f">>> LINKAGE APPROVE URL: {approve_url}")

    return {"message": "承認リクエストを送信しました"}


@router.get("/linkage-approve", status_code=status.HTTP_200_OK)
async def approve_linkage(token: str):
    """
    税理士法人がメール内リンクをクリックして紐付けを承認する。
    認証不要（トークン自体が証明）。
    """
    db = get_database()

    invitation = await db["invitations"].find_one({"token": token})

    if not invitation:
        return HTMLResponse(content=_html_result("エラー", "このリンクは無効です。", success=False), status_code=400)

    if invitation.get("type") != "linkage_request":
        return HTMLResponse(content=_html_result("エラー", "このリンクは無効です。", success=False), status_code=400)

    if invitation.get("status") != "pending":
        return HTMLResponse(content=_html_result("承認済み", "この紐付けリクエストは既に処理済みです。", success=False), status_code=400)

    if invitation.get("expires_at") < datetime.utcnow():
        return HTMLResponse(content=_html_result("期限切れ", "このリンクの有効期限が切れています。法人に再送信を依頼してください。", success=False), status_code=400)

    corporate_uid = invitation.get("corporate_id")
    tax_firm_uid = invitation.get("tax_firm_id")

    # corporates の advising_tax_firm_id を更新
    await db["corporates"].update_one(
        {"firebase_uid": corporate_uid},
        {"$set": {"advising_tax_firm_id": tax_firm_uid}}
    )

    # invitations のステータスを accepted に更新
    await db["invitations"].update_one(
        {"token": token},
        {"$set": {"status": "accepted"}}
    )

    print(f">>> LINKAGE APPROVED: CORPORATE={corporate_uid} → TAX_FIRM={tax_firm_uid}")
    return HTMLResponse(content=_html_result("紐付け完了", "法人との連携が完了しました。Tax-Agentにログインして顧客一覧をご確認ください。", success=True))


def _html_result(title: str, message: str, success: bool) -> str:
    color = "#4f46e5" if success else "#dc2626"
    icon = "✓" if success else "✕"
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} - Tax Agent</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; background: #f9fafb; }}
    .card {{ background: white; border-radius: 16px; padding: 48px; text-align: center; max-width: 480px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }}
    .icon {{ width: 64px; height: 64px; border-radius: 50%; background: {color}; color: white; font-size: 32px; display: flex; align-items: center; justify-content: center; margin: 0 auto 24px; }}
    h1 {{ color: #111827; font-size: 24px; margin: 0 0 12px; }}
    p {{ color: #6b7280; line-height: 1.6; margin: 0; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h1>{title}</h1>
    <p>{message}</p>
  </div>
</body>
</html>"""
