from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from app.api.rest_routes.admin import router as admin_router
from app.api.rest_routes.auth import router as auth_router
from app.api.rest_routes.chat import router as chat_router
from app.api.rest_routes.crop_recommendation import (
    router as crop_recommendation_router,
)
from app.api.rest_routes.cultivating_crop import (
    router as cultivating_crop_router,
)
from app.api.rest_routes.cultivation_calendar import (
    router as cultivation_calendar_router,
)
from app.api.rest_routes.farm_profile import (
    router as farm_profile_router,
)
from app.api.rest_routes.files import router as files_router
from app.api.rest_routes.investment_breakdown import (
    router as investment_breakdown_router,
)
from app.api.rest_routes.pesticide_recommendation import (
    router as pesticide_recommendation_router,
)
from app.api.rest_routes.soil_health_recommendations import (
    router as soil_health_recommendations_router,
)
from app.api.rest_routes.weather import router as weather_router
from app.api.websocket.endpoints import router as websocket_router
from app.core.mongodb import close_mongo_client, init_mongo_client

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_mongo_client()
    yield
    await close_mongo_client()


app = FastAPI(lifespan=lifespan)

app.include_router(websocket_router, tags=["websocket"])
app.include_router(auth_router)
app.include_router(crop_recommendation_router)
app.include_router(chat_router)
app.include_router(cultivating_crop_router)
app.include_router(cultivation_calendar_router)
app.include_router(farm_profile_router)
app.include_router(investment_breakdown_router)
app.include_router(pesticide_recommendation_router)
app.include_router(soil_health_recommendations_router)
app.include_router(files_router)
app.include_router(weather_router)
app.include_router(admin_router)


@app.get("/")
async def root():
    return {"message": "Welcome to the Smart Farming Kisan Seva AI!"}
