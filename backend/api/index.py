"""Vercel serverless entrypoint. The Python runtime serves the ASGI `app`."""

from app.main import app

__all__ = ["app"]
