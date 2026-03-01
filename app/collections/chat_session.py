from typing import List, Optional

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.mongodb import (
    get_chat_session_collection,
    get_message_collection,
)
from app.models.chat_session import ChatSession, Message
from app.services.files import FileType, delete_multiple_files


async def get_chat_sessions_from_user_id(user_id: str) -> List[ChatSession]:
    chat_collection: AsyncIOMotorCollection = get_chat_session_collection()
    try:
        query = {"user_id": user_id}

        chats = chat_collection.find(query)
        return [ChatSession.model_validate(chat) async for chat in chats]
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=str(e) + " - get_chat_sessions_from_user_id"
        )


async def get_chat_session_from_id(chat_id: str) -> ChatSession:
    chat_collection: AsyncIOMotorCollection = get_chat_session_collection()
    try:
        response = await chat_collection.find_one({"_id": chat_id})
        if not response:
            raise HTTPException(
                status_code=404,
                detail=f"ChatSession {chat_id} not found - get_chat_session_from_id",
            )
        return ChatSession.model_validate(response)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def save_chat_session(chat: ChatSession) -> ChatSession:
    chat_collection: AsyncIOMotorCollection = get_chat_session_collection()
    try:
        payload = chat.model_dump(mode="json", exclude_none=True, by_alias=True)
        await chat_collection.replace_one({"_id": chat.id}, payload, upsert=True)
        response = await chat_collection.find_one({"_id": chat.id})
        return ChatSession.model_validate(response)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def get_message_from_id(message: Message) -> Message:
    message_collection: AsyncIOMotorCollection = get_message_collection()
    try:
        response = await message_collection.find_one({"_id": message.id})
        if not response:
            raise HTTPException(
                status_code=404,
                detail=f"Message {message.id} not found",
            )
        return Message.model_validate(response)
    except HTTPException:
        raise


async def get_messages_from_chat_session_id(
    chat_id: str, ts: Optional[float] = None, limit: Optional[int] = None
) -> List[Message]:
    message_collection: AsyncIOMotorCollection = get_message_collection()
    try:
        query = {"chat_id": chat_id}
        if ts:
            query["ts"] = {"$gt": ts}

        messages = message_collection.find(query).sort("ts", 1)
        if limit:
            messages = messages.limit(limit)

        return [Message.model_validate(message) async for message in messages]
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def save_message(
    message: Message,
) -> Message:
    message_collection: AsyncIOMotorCollection = get_message_collection()
    try:
        payload = message.model_dump(mode="json", exclude_none=True, by_alias=True)
        await message_collection.replace_one({"_id": message.id}, payload, upsert=True)
        response = await message_collection.find_one({"_id": message.id})
        return Message.model_validate(response)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def delete_chat_messages(chat_id: str) -> bool:
    message_collection: AsyncIOMotorCollection = get_message_collection()
    try:
        await message_collection.delete_many({"chat_id": chat_id})
        return True
    except Exception:
        return True


async def delete_chat_session(chat_id: str, user_id: str) -> bool:
    chat_collection: AsyncIOMotorCollection = get_chat_session_collection()
    try:
        chat_session = await chat_collection.find_one({"_id": chat_id})
        if not chat_session:
            raise HTTPException(
                status_code=404,
                detail=f"ChatSession {chat_id} not found.",
            )
        if chat_session.get("user_id") != user_id:
            raise HTTPException(
                status_code=403,
                detail=f"User {user_id} is not authorized to delete ChatSession {chat_id}.",
            )

        await delete_chat_messages(chat_id)
        await delete_multiple_files(
            file_type=FileType.AI_CHAT,
            user_id=user_id,
            data_id=chat_id,
        )
        await chat_collection.delete_one({"_id": chat_id})
        return True
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")
