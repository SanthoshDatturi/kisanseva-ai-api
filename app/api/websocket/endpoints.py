# app/api/websocket/endpoints.py
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.security import verify_jwt

from .actions import actions
from .manager import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    user_id: str | None = None
    try:
        """Manually verify JWT from WebSocket headers."""
        token_header: str | None = websocket.headers.get("Authorization")
        if not token_header or not token_header.startswith("Bearer "):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        token = token_header.split(" ")[1]
        try:
            user_payload = await verify_jwt(token)
        except Exception:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        user_id = user_payload.get("sub")
        language: str = user_payload.get("language", "en")

        if not user_id:
            await websocket.close(code=1008)
            return

        await manager.connect(websocket, user_id)

        while True:
            print("Waiting for message")
            raw_data = await websocket.receive_text()
            try:
                message = json.loads(raw_data)
                action = message.get("action")
                data = message.get("data", {})
                if action in actions:
                    await actions[action](user_id, language, data)
                else:
                    await websocket.send_text(f"Unknown action: {action}")
            except json.JSONDecodeError:
                await websocket.send_text("Invalid JSON")
    except WebSocketDisconnect:
        if user_id:
            manager.disconnect(websocket, user_id)
    except Exception:
        if user_id:
            manager.disconnect(websocket, user_id)
