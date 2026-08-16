from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.db import Base, engine
from app.core.firebase import init_firebase
from app.core.storage import storage  # noqa: F401  (import creates STORAGE_ROOT_DIR before we mount it below)
from app.middleware.setup import register_middleware
from app.models import asset as asset_models  # noqa: F401  (registers Asset on Base)
from app.models import generation_job as generation_job_models  # noqa: F401  (registers GenerationJob on Base)
from app.models import invite as invite_models  # noqa: F401  (registers TeamInvite on Base)
from app.models import team as team_models  # noqa: F401  (registers Team/TeamMembership on Base)
from app.models import user as user_models  # noqa: F401  (registers User on Base)
from app.routes.asset_routes import router as asset_router
from app.routes.auth_routes import router as auth_router
from app.routes.generation_routes import router as generation_router
from app.routes.health_routes import router as health_router
from app.routes.team_routes import router as teams_router

Base.metadata.create_all(bind=engine)
init_firebase()

app = FastAPI(title=settings.APP_NAME)
register_middleware(app)

# Serves whatever LocalStorage writes to disk — this is what makes
# Asset.url a real, fetchable link instead of just a file path.
app.mount("/files", StaticFiles(directory=settings.STORAGE_ROOT_DIR), name="files")

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(teams_router)
app.include_router(asset_router)
app.include_router(generation_router)


@app.get("/")
def root():
    return {"message": f"{settings.APP_NAME} API is running"}
