"""Vercel serverless function entrypoint."""

from app.main import app

# Export app for Vercel
__all__ = ["app"]
