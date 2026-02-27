# Kisan Seva AI API

FastAPI backend for AI-assisted farming workflows: onboarding via OTP, farm profiling, crop recommendation, pesticide guidance, chat (REST + WebSocket), weather utilities, and file/TTS handling via Azure Blob Storage.

## Tech Stack

- Python 3.12
- FastAPI
- MongoDB (Motor)
- Google Gemini (LangChain + google-genai)
- Azure Blob Storage
- OpenWeatherMap APIs
- JWT auth (PyJWT)

## Features

- OTP-based auth and JWT session flow
- Farm profile create/read/delete (including language-specific profile handling)
- Chat sessions and message history
- WebSocket AI actions:
  - farm survey agent
  - general chat
  - crop recommendation
  - crop selection deep-dive
  - pesticide recommendation
  - text-to-speech URL generation
- Crop lifecycle data APIs:
  - crop recommendations
  - cultivating crops
  - cultivation calendars
  - investment breakdowns
  - soil health recommendations
  - pesticide recommendation stage updates
- File upload/delete and AI TTS audio storage in Azure Blob
- Admin APIs/pages for crop image management + vector-search-backed crop image matching
- Weather and reverse-geocoding APIs

## Project Structure

```text
app/
  api/
    rest_routes/        # REST endpoints
    websocket/          # /ws endpoint + action handlers
  collections/          # MongoDB data access layer
  core/                 # config, security, mongo, Gemini clients
  models/               # Pydantic schemas
  prompts/              # System prompts for AI workflows
  services/             # AI/business/integration services
  templates/            # Admin HTML/CSS pages
```

## Requirements

- Python `>=3.12`
- MongoDB instance
- Azure Storage account + connection string
- Gemini API key
- OpenWeatherMap API key (for weather routes)

## Environment Variables

Create `.env` in project root.

```env
GEMINI_API_KEY=
AZURE_STORAGE_CONNECTION_STRING=
JWT_SECRET_KEY=
MONGO_URI=
MONGO_DIRECT_URI=
OPENWEATHERMAP_API_KEY=
```

Notes:
- App DB name is fixed to `main` in current config.
- If both Mongo URIs are set, `MONGO_DIRECT_URI` is preferred.

## Local Setup

```bash
# 1) Install uv (if not installed)
# https://docs.astral.sh/uv/getting-started/installation/

# 2) Install dependencies
uv sync

# 3) Run API
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Root: `http://localhost:8000/`

## Docker

```bash
docker build -t kisan-seva-ai-api .
docker run --env-file .env -p 8000:80 kisan-seva-ai-api
```

## Authentication Flow

1. `POST /auth/send-otp`
   - New user: send `phone`, `name`, `language`
   - Existing user: send `phone`
2. `POST /auth/verify-otp`
   - Current implementation validates OTP `123456` (mock behavior).
3. Use returned `access_token` as:
   - REST: `Authorization: Bearer <token>`
   - WebSocket: same header during `/ws` connection.

## API Overview

### Auth (`/auth`)

- `POST /send-otp`
- `POST /verify-otp`
- `GET /user`
- `DELETE /delete`

### Chats (`/chats`)

- `POST /` create chat session
- `GET /` list chat sessions (optional `timestamp`)
- `GET /{chat_id}`
- `GET /{chat_id}/messages` (optional `timestamp`, `limit`)
- `DELETE /{chat_id}`

### Farm Profiles (`/farm-profiles`)

- `POST /` upsert farm profile
- `GET /` list user profiles
- `GET /{farm_id}`
- `DELETE /{farm_id}`

### Crop Domain APIs

- `/crop-recommendations`
  - `GET /farm/{farm_id}`
  - `GET /{recommendation_id}`
- `/cultivating-crops`
  - `GET /farm/{farm_id}`
  - `GET /{cultivating_crop_id}`
  - `GET /intercropping/{intercropping_details_id}`
  - `DELETE /{cultivating_crop_id}`
- `/cultivation-calendars`
  - `GET /{cultivation_calendar_id}`
  - `GET /crop/{crop_id}`
  - `DELETE /{cultivation_calendar_id}`
- `/investment-breakdowns`
  - `GET /{investment_breakdown_id}`
  - `GET /crop/{crop_id}`
  - `DELETE /{investment_breakdown_id}`
- `/soil-health-recommendations`
  - `GET /{recommendation_id}`
  - `GET /crop/{crop_id}`
  - `DELETE /{recommendation_id}`
- `/pesticide-recommendations`
  - `GET /{recommendation_id}`
  - `GET /crop/{crop_id}`
  - `PATCH /{recommendation_id}/stage`
  - `DELETE /{recommendation_id}`

### Files (`/files`)

- `POST /` multipart upload (`file`, `blob_name`, `file_type`, `path_prefix`)
- `DELETE /` delete by blob reference URL/body
- `POST /text-to-speech` generate and store WAV

Important path rule for `ai-chat` and `user-content` uploads:
- `path_prefix` must be `<user_id>/<data_id>` (or deeper under it).

### Weather (`/weather`)

- `GET /current?lat=&lon=`
- `GET /forecast?lat=&lon=`
- `GET /air-pollution?lat=&lon=`
- `GET /reverse-geocoding?lat=&lon=`

### Admin (`/admin`)

- `GET /login` admin login page
- `GET /theme.css`
- `GET /handle-crop-images` upload page
- `POST /crop-images` (admin JWT required)
- `GET /crop-images?crop_name=` (admin JWT required)

## WebSocket API

Endpoint: `/ws` (requires `Authorization: Bearer <token>` header)

Message format:

```json
{
  "action": "general_chat",
  "data": {}
}
```

Supported actions:
- `farm_survey_agent`
- `general_chat`
- `crop_recommendation`
- `select_crop_from_recommendation`
- `pesticide_recommendation`
- `text_to_speech_url`

Response format:

```json
{
  "action": "general_chat",
  "data": { }
}
```

Or on error:

```json
{
  "action": "general_chat",
  "error": {
    "status_code": 400,
    "message": "..."
  }
}
```

## Data and Storage Notes

- Mongo collections include: `user`, `farm_profile`, `user_language_farm_profile`, `chat_session`, `messages`, `crop_recommendation_response`, `cultivating_crop`, `intercropping_details`, `cultivation_calendar`, `investment_breakdown`, `soil_health_recommendations`, `pesticide_recommendation`, `crop_images`.
- Azure containers used:
  - `user-content`
  - `ai-chat`
  - `system-data`
- File APIs return blob references in format `<container>/<path>/<file>`.

## Known Development Behaviors

- OTP send/validate is currently mocked (`123456`).
- Weather service caches some responses in `app/services/.cache`.
- No automated test suite is present in this repository currently.

## Recommended Next Steps

- Replace mocked OTP with real provider integration.
- Add test coverage for auth, file path validation, and websocket actions.
- Add DB indexes (especially for timestamp and vector search paths) and migration/bootstrap docs.
