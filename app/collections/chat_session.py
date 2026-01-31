from typing import List, Optional

from azure.cosmos.container import ContainerProxy
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from fastapi import HTTPException

from app.core.azure_cosmos_config import (
    get_chat_session_container,
    get_message_container,
)
from app.models.chat_session import ChatSession, Message


async def get_chat_sessions_from_user_id(
    user_id: str, ts: Optional[float] = None
) -> List[ChatSession]:
    chat_container: ContainerProxy = get_chat_session_container()
    try:
        if ts:
            query = "SELECT * FROM c WHERE c.user_id = @user_id AND c.ts > @ts"
            parameters = [
                {"name": "@user_id", "value": user_id},
                {"name": "@ts", "value": ts},
            ]
        else:
            query = "SELECT * FROM c WHERE c.user_id = @user_id"
            parameters = [{"name": "@user_id", "value": user_id}]

        chats = chat_container.query_items(
            query=query,
            parameters=parameters,
        )
        # validate and return chat sessions
        return [ChatSession.model_validate(chat) async for chat in chats]
    except CosmosResourceNotFoundError:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=str(e) + " - get_chat_sessions_from_user_id"
        )


async def get_chat_session_from_id(chat_id: str) -> ChatSession:
    chat_container: ContainerProxy = get_chat_session_container()
    try:
        response = await chat_container.read_item(item=chat_id, partition_key=chat_id)
        return ChatSession.model_validate(response)
    except CosmosResourceNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"ChatSession {chat_id} not found - get_chat_session_from_id",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def save_chat_session(chat: ChatSession) -> ChatSession:
    chat_container: ContainerProxy = get_chat_session_container()
    try:
        response = await chat_container.upsert_item(
            body=chat.model_dump(exclude_none=True)
        )
        return ChatSession.model_validate(response)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def get_message_from_id(message: Message) -> Message:
    message_container: ContainerProxy = get_message_container()
    try:
        response = await message_container.read_item(
            item=message.id, partition_key=message.id
        )
        return Message.model_validate(response)
    except CosmosResourceNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Message {message.id} not found",
        )


async def get_messages_from_chat_session_id(
    chat_id: str, ts: Optional[float] = None, limit: Optional[int] = None
) -> List[Message]:
    message_container: ContainerProxy = get_message_container()
    try:
        query = "SELECT * FROM c WHERE c.chat_id = @chat_id"
        parameters = [{"name": "@chat_id", "value": chat_id}]

        if ts:
            query += " AND c.ts > @ts"
            parameters.append({"name": "@ts", "value": ts})

        query += " ORDER BY c.ts ASC"

        if limit:
            query += f" OFFSET 0 LIMIT {limit}"

        messages = message_container.query_items(
            query=query,
            parameters=parameters,
        )
        # validate and return messages
        return [Message.model_validate(message) async for message in messages]
    except CosmosResourceNotFoundError:
        raise HTTPException(status_code=404, detail=f"ChatSession {chat_id} not found")
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def save_message(
    message: Message,
) -> Message:
    message_container: ContainerProxy = get_message_container()
    try:
        response = await message_container.upsert_item(
            body=message.model_dump(exclude_none=True)
        )
        print(response)
        return Message.model_validate(response)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def delete_chat_session(chat_id: str) -> bool:
    chat_container: ContainerProxy = get_chat_session_container()
    message_container: ContainerProxy = get_message_container()
    # First, delete all messages associated with the chat session
    try:
        messages = message_container.query_items(
            query="SELECT * FROM c WHERE c.chat_id = @chat_id",
            parameters=[{"name": "@chat_id", "value": chat_id}],
        )
        async for message in messages:
            await message_container.delete_item(
                item=message["id"], partition_key=message["id"]
            )
        await chat_container.delete_item(item=chat_id, partition_key=chat_id)
        return True
    except CosmosResourceNotFoundError:
        return True
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")
