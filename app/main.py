from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from app.api.rest_routes.auth import router as auth_router
from app.core.azure_cosmos_config import close_cosmos_client, init_cosmos_client

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_cosmos_client()
    yield
    await close_cosmos_client()


app = FastAPI(lifespan=lifespan)

app.include_router(auth_router)


@app.get("/")
async def root():
    return {"message": "Welcome to the Smart Farming Kisan Mithra!"}
