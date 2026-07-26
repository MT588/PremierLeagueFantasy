from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import verify_token
from app.config import settings
from app.routers import health, meta, players, predictions, stats, team

app = FastAPI(title="PL Fantasy Analytics", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in settings.cors_origins.split(",") if o],
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health stays public so uptime checks work without a token.
app.include_router(health.router, prefix="/api")

protected = {"prefix": "/api", "dependencies": [Depends(verify_token)]}
app.include_router(meta.router, **protected)
app.include_router(players.router, **protected)
app.include_router(predictions.router, **protected)
app.include_router(stats.router, **protected)
app.include_router(team.router, **protected)
