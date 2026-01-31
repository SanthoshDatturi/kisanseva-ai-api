from google.genai.client import Client

from .config import settings

_client: Client = None


def get_client():
    global _client
    if _client is None:
        _client = Client(api_key=settings.GEMINI_API_KEY)
    return _client
