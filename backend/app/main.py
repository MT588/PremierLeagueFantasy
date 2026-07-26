from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import meta, players, predictions, team

app = FastAPI(title="PL Fantasy Analytics", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router, prefix="/api")
app.include_router(players.router, prefix="/api")
app.include_router(predictions.router, prefix="/api")
app.include_router(team.router, prefix="/api")
