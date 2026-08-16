"""Where uploaded and generated files actually live. Same pattern as
core/email.py and core/firebase.py: one small interface, one local
implementation for now, swap the implementation for R2/S3 later without
touching any caller — nothing outside this file should know which one is
in use.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import settings


class Storage(ABC):
    @abstractmethod
    def save(self, key: str, content: bytes) -> None: ...

    @abstractmethod
    def url_for(self, key: str) -> str: ...


class LocalStorage(Storage):
    """Writes to a folder on disk; main.py mounts that folder at /files so
    url_for() returns a URL that's actually fetchable, not just a path."""

    def __init__(self, root_dir: str, base_url: str):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url.rstrip("/")

    def save(self, key: str, content: bytes) -> None:
        path = self.root_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def url_for(self, key: str) -> str:
        return f"{self.base_url}/{key}"


# The one line every caller goes through. Swap this for an R2/S3-backed
# Storage implementation later; nothing else in the app changes.
storage: Storage = LocalStorage(
    root_dir=settings.STORAGE_ROOT_DIR,
    base_url=f"{settings.BACKEND_URL}/files",
)
