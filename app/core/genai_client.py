from google.genai.client import Client
from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    GoogleGenerativeAIEmbeddings,
    HarmBlockThreshold,
    HarmCategory,
)

from .config import settings

_raw_google_client: Client | None = None

DEFAULT_SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
}


def get_chat_model(model: str, **kwargs) -> ChatGoogleGenerativeAI:
    if "google_api_key" not in kwargs and "api_key" not in kwargs:
        kwargs["google_api_key"] = settings.GEMINI_API_KEY
    if "safety_settings" not in kwargs:
        kwargs["safety_settings"] = DEFAULT_SAFETY_SETTINGS
    return ChatGoogleGenerativeAI(model=model, **kwargs)


def get_embeddings_model(
    model: str = "gemini-embedding-001", **kwargs
) -> GoogleGenerativeAIEmbeddings:
    if "google_api_key" not in kwargs and "api_key" not in kwargs:
        kwargs["google_api_key"] = settings.GEMINI_API_KEY
    return GoogleGenerativeAIEmbeddings(model=model, **kwargs)


def get_raw_google_client() -> Client:
    global _raw_google_client
    if _raw_google_client is None:
        _raw_google_client = Client(api_key=settings.GEMINI_API_KEY)
    return _raw_google_client


def get_client() -> Client:
    """Backward-compatible alias for legacy imports."""
    return get_raw_google_client()
