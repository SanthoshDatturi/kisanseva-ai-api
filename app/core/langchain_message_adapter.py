from __future__ import annotations

from typing import Any, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.models.chat_session import Message, MessageContent, MessageFileData, MessagePart, Role


def coerce_message_content(
    value: Any, default_role: str | None = None
) -> MessageContent:
    if isinstance(value, MessageContent):
        if value.role is None and default_role is not None:
            value.role = default_role
        return value

    if not isinstance(value, dict):
        return MessageContent(role=default_role, parts=[])

    role = value.get("role") or default_role
    raw_parts = value.get("parts") or []
    parts: list[MessagePart] = []

    for raw_part in raw_parts:
        if not isinstance(raw_part, dict):
            continue

        text = raw_part.get("text")

        file_data_dict: dict[str, Any] | None = None
        if isinstance(raw_part.get("file_data"), dict):
            file_data_dict = raw_part["file_data"]
        elif isinstance(raw_part.get("fileData"), dict):
            legacy_data = raw_part["fileData"]
            file_data_dict = {
                "file_uri": legacy_data.get("file_uri") or legacy_data.get("fileUri"),
                "mime_type": legacy_data.get("mime_type") or legacy_data.get("mimeType"),
            }

        file_data = None
        if file_data_dict and file_data_dict.get("file_uri"):
            file_data = MessageFileData(
                file_uri=file_data_dict.get("file_uri"),
                mime_type=file_data_dict.get("mime_type") or "application/octet-stream",
            )

        parts.append(MessagePart(text=text, file_data=file_data))

    return MessageContent(role=role, parts=parts)


def message_content_to_langchain_content(content: MessageContent) -> str | list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    text_items: list[str] = []

    for part in content.parts:
        if part.text is not None:
            text_items.append(part.text)
            blocks.append({"type": "text", "text": part.text})

        if part.file_data is not None:
            blocks.append(
                {
                    "type": "media",
                    "file_uri": part.file_data.file_uri,
                    "mime_type": part.file_data.mime_type,
                }
            )

    if blocks:
        return blocks
    if text_items:
        return "\n".join(text_items)
    return ""


def message_content_to_langchain_message(
    content: MessageContent, fallback_role: str = Role.USER
) -> BaseMessage:
    role = content.role or fallback_role
    lc_content = message_content_to_langchain_content(content)

    if role == Role.MODEL:
        return AIMessage(content=lc_content)
    if role == Role.SYSTEM:
        return SystemMessage(content=lc_content)
    return HumanMessage(content=lc_content)


def chat_messages_to_langchain(messages: Sequence[Message]) -> list[BaseMessage]:
    result: list[BaseMessage] = []
    for message in messages:
        content = coerce_message_content(message.content)
        fallback_role = Role.USER if content.role is None else content.role
        result.append(
            message_content_to_langchain_message(content=content, fallback_role=fallback_role)
        )
    return result


def text_to_message_content(text: str, role: str = Role.MODEL) -> MessageContent:
    return MessageContent(role=role, parts=[MessagePart(text=text)])


def message_content_with_audio(
    text: str, audio_url: str | None = None, role: str = Role.MODEL
) -> MessageContent:
    parts = [MessagePart(text=text)]
    if audio_url:
        parts.append(
            MessagePart(
                file_data=MessageFileData(file_uri=audio_url, mime_type="audio/wav")
            )
        )
    return MessageContent(role=role, parts=parts)
