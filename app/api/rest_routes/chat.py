from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.collections.chat_session import (
    delete_chat_session,
    get_chat_session_from_id,
    get_chat_sessions_from_user_id,
    get_messages_from_chat_session_id,
)
from app.core.security import verify_jwt
from app.models.chat_session import ChatSession, Message

router = APIRouter(prefix="/chats", tags=["Chat"])


@router.get("/", response_model=List[ChatSession], response_model_exclude_none=True)
async def get_user_chat_sessions(
    timestamp: Optional[float] = Query(default=None, description="Filter sessions updated after this timestamp (Unix seconds)"),
    user_payload: dict = Depends(verify_jwt),
):
    """
    Get all chat sessions for the authenticated user.
    """
    user_id = user_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    chat_sessions = await get_chat_sessions_from_user_id(user_id, ts=timestamp)
    return chat_sessions


@router.get("/{chat_id}", response_model=ChatSession, response_model_exclude_none=True)
async def get_chat_session(chat_id: str, user_payload: dict = Depends(verify_jwt)):
    """
    Get a specific chat session by its ID.
    Ensures the chat session belongs to the authenticated user.
    """
    user_id = user_payload.get("sub")
    chat_session = await get_chat_session_from_id(chat_id)
    if chat_session.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to this chat session",
        )
    return chat_session


@router.get(
    "/{chat_id}/messages",
    response_model=List[Message],
    response_model_exclude_none=True,
)
async def get_chat_messages(
    chat_id: str,
    timestamp: Optional[float] = Query(default=None, description="Filter messages sent after this timestamp (Unix seconds)"),
    limit: Optional[int] = Query(default=None, description="Limit the number of messages returned", ge=1, le=100),
    user_payload: dict = Depends(verify_jwt),
):
    """
    Get all messages for a specific chat session.
    Ensures the chat session belongs to the authenticated user before fetching messages.
    """
    user_id = user_payload.get("sub")
    # First, verify the user has access to the chat session
    chat_session = await get_chat_session_from_id(chat_id)
    if chat_session.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to this chat session",
        )
    messages = await get_messages_from_chat_session_id(
        chat_id, ts=timestamp, limit=limit
    )
    return messages


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_chat_session(
    chat_id: str, user_payload: dict = Depends(verify_jwt)
):
    """
    Deletes a chat session and all its associated messages.
    Ensures the chat session belongs to the authenticated user.
    """
    user_id = user_payload.get("sub")
    chat_session = await get_chat_session_from_id(chat_id)
    if chat_session.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to this chat session",
        )
    await delete_chat_session(chat_id)
    return
