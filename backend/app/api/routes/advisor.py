from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import get_current_user
from app.api.helpers import resolve_corporate_id
from app.services.chat_service import ChatService

router = APIRouter()

@router.post("/chat", summary="AIアドバイザーと対話する")
async def chat_with_advisor(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    AI Chat Advisor endpoint. 
    Accepts 'query' and returns AI generated response based on corporate context.
    """
    query = payload.get("query")
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")
    
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    
    try:
        response = await ChatService.process_query(corporate_id, query)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Advisor error: {str(e)}")
