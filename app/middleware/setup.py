"""App-level middleware registration — the equivalent of Express's
`app.use(...)` calls, kept out of main.py so that file stays a one-glance
summary of the app instead of a pile of add_middleware() calls."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL, settings.TEST_CONSOLE_URL],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
