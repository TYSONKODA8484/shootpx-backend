"""Where uploaded and generated files actually live. Same pattern as
core/email.py and core/firebase.py: one small interface, one local
implementation for now, swap the implementation for R2/S3 later without
touching any caller — nothing outside this file should know which one is
in use.
"""

import mimetypes
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from app.core.config import settings


class Storage(ABC):
    @abstractmethod
    def save(self, key: str, content: bytes) -> None: ...

    @abstractmethod
    def url_for(self, key: str) -> str: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def read(self, key: str) -> bytes: ...


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

    def delete(self, key: str) -> None:
        path = self.root_dir / key
        try:
            path.unlink()
        except FileNotFoundError:
            pass  # already gone — deleting a missing file isn't an error here

    def read(self, key: str) -> bytes:
        return (self.root_dir / key).read_bytes()


class SupabaseStorage(Storage):
    """Talks to Supabase's own Storage REST API directly over httpx, rather
    than pulling in the supabase-py SDK for four methods — same "small
    interface, thin HTTP client" shape as core/fal_provider.py. Needs the
    bucket to already exist and be set Public in the Supabase dashboard:
    url_for() builds the public-object URL pattern directly instead of
    requesting a signed one, so it stays a synchronous, no-extra-round-trip
    string build like LocalStorage.url_for() is.

    Picked over the S3-compatible endpoint Supabase Storage also exposes:
    that needs separate S3 access keys and a boto3/aiobotocore dependency
    for the same four operations this REST API already does with the one
    HTTP client (httpx) already in requirements.txt.
    """

    def __init__(self, project_url: str, service_role_key: str, bucket: str):
        self.base_url = project_url.rstrip("/")
        self.bucket = bucket
        # apikey identifies the project; Authorization is what Storage
        # actually authorizes the request against (service_role bypasses
        # bucket RLS policies) — Supabase's REST APIs generally expect both.
        self._headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
        }

    def save(self, key: str, content: bytes) -> None:
        content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
        resp = httpx.post(
            f"{self.base_url}/storage/v1/object/{self.bucket}/{key}",
            headers={
                **self._headers,
                "Content-Type": content_type,
                "x-upsert": "true",  # LocalStorage.save() overwrites
                # unconditionally (Path.write_bytes) — match that instead of
                # erroring on a key that already exists.
            },
            content=content,
            timeout=30.0,
        )
        resp.raise_for_status()

    def url_for(self, key: str) -> str:
        return f"{self.base_url}/storage/v1/object/public/{self.bucket}/{key}"

    def delete(self, key: str) -> None:
        # Supabase's single-object delete is really "bulk delete by prefix
        # list" (POST/DELETE .../object/{bucket} with a JSON body) — there's
        # no plain DELETE .../object/{bucket}/{key} endpoint.
        resp = httpx.request(
            "DELETE",
            f"{self.base_url}/storage/v1/object/{self.bucket}",
            headers={**self._headers, "Content-Type": "application/json"},
            json={"prefixes": [key]},
            timeout=30.0,
        )
        # Same "deleting a missing file isn't an error" contract as
        # LocalStorage.delete() — a 404 here means the object (or bucket
        # path) was already gone, not a real failure.
        if resp.status_code == 404:
            return
        resp.raise_for_status()

    def read(self, key: str) -> bytes:
        resp = httpx.get(
            f"{self.base_url}/storage/v1/object/{self.bucket}/{key}",
            headers=self._headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.content


def _build_storage() -> Storage:
    if settings.STORAGE_BACKEND == "supabase":
        return SupabaseStorage(
            project_url=settings.SUPABASE_URL,
            service_role_key=settings.SUPABASE_SERVICE_ROLE_KEY,
            bucket=settings.SUPABASE_STORAGE_BUCKET,
        )
    return LocalStorage(
        root_dir=settings.STORAGE_ROOT_DIR,
        base_url=f"{settings.BACKEND_URL}/files",
    )


# The one line every caller goes through. STORAGE_BACKEND (.env) picks which
# implementation; nothing else in the app changes either way.
storage: Storage = _build_storage()
