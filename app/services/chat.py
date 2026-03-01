import asyncio

from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate

from app.collections.chat_session import (
    get_messages_from_chat_session_id,
    save_message,
)
from app.core.langchain_message_adapter import (
    coerce_message_content,
    message_content_to_langchain_message,
    message_content_with_audio,
)
from app.models.chat_session import (
    Message,
    MessageContent,
    MessagePart,
    Role,
)
from app.services.files import convert_file_uri, text_to_speech_url


def build_system_messages(system_prompt: str, language: str) -> list[BaseMessage]:
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "{system_prompt}\n\nUser specified language: {language}",
            )
        ]
    )
    return prompt.format_messages(
        system_prompt=system_prompt,
        language=language,
    )


async def convert_content_for_model(
    content: MessageContent, skip_audio_when_text_exists: bool = False
) -> MessageContent:
    normalized = coerce_message_content(content, default_role=Role.USER)
    has_text = any(part.text is not None for part in normalized.parts)

    converted_parts: list[MessagePart] = []
    conversion_tasks = []
    task_indexes: list[int] = []

    for part in normalized.parts:
        if part.file_data:
            if (
                skip_audio_when_text_exists
                and has_text
                and part.file_data.mime_type.startswith("audio/")
            ):
                continue

            task_indexes.append(len(converted_parts))
            conversion_tasks.append(convert_file_uri(part.file_data.file_uri))
            converted_parts.append(MessagePart())
        elif part.text is not None:
            converted_parts.append(MessagePart(text=part.text))

    if conversion_tasks:
        converted_results = await asyncio.gather(*conversion_tasks)
        for idx, (uri, mime) in zip(task_indexes, converted_results):
            converted_parts[idx] = MessagePart.model_validate(
                {"file_data": {"file_uri": uri, "mime_type": mime}}
            )

    return MessageContent(role=normalized.role, parts=converted_parts)


async def prepare_model_input_messages(
    chat_id: str,
    content: MessageContent,
    system_prompt: str,
    language: str,
) -> list[BaseMessage]:
    messages = await get_messages_from_chat_session_id(chat_id=chat_id)

    converted_history_contents = await asyncio.gather(
        *[
            convert_content_for_model(m.content, skip_audio_when_text_exists=True)
            for m in messages
        ]
    )
    chat_history = [
        message_content_to_langchain_message(
            converted_content,
            fallback_role=converted_content.role or Role.USER,
        )
        for converted_content in converted_history_contents
    ]

    converted_current_content = await convert_content_for_model(
        content=content,
        skip_audio_when_text_exists=True,
    )
    user_message_for_model = message_content_to_langchain_message(
        converted_current_content,
        fallback_role=Role.USER,
    )

    return (
        build_system_messages(system_prompt=system_prompt, language=language)
        + chat_history
        + [user_message_for_model]
    )


async def save_user_message_with_fallback(
    chat_id: str,
    content: MessageContent,
    request_id: str,
    fallback_text: str = "",
) -> Message:
    user_content = coerce_message_content(content, default_role=Role.USER)
    if not any(part.text is not None for part in user_content.parts):
        user_content.parts.append(MessagePart(text=fallback_text))

    return await save_message(
        message=Message(
            content=user_content,
            chat_id=chat_id,
            request_id=request_id,
        )
    )


async def save_model_response_message(
    chat_id: str,
    text: str,
    request_id: str,
    language: str,
    audio_response: bool = False,
    blob_name: str | None = None,
    path_prefix: str | None = None,
) -> Message:
    audio_url = None
    if audio_response and blob_name:
        audio_url = await text_to_speech_url(
            text_or_data=text,
            blob_name=blob_name,
            path_prefix=path_prefix,
            language=language,
        )

    model_content = message_content_with_audio(
        text=text,
        audio_url=audio_url,
        role=Role.MODEL,
    )
    return await save_message(
        Message(
            content=model_content,
            chat_id=chat_id,
            request_id=request_id,
        )
    )
