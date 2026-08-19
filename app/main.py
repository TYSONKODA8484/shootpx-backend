from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.firebase import init_firebase
from app.core.storage import storage  # noqa: F401  (import creates STORAGE_ROOT_DIR before we mount it below)
from app.middleware.setup import register_middleware
from app.models import ai_model as ai_model_models  # noqa: F401  (registers AIModel on Base)
from app.models import asset as asset_models  # noqa: F401  (registers Asset on Base)
from app.models import credit as credit_models  # noqa: F401  (registers TeamCreditBalance/CreditTransaction/CreditPack on Base)
from app.models import generation_job as generation_job_models  # noqa: F401  (registers GenerationJob on Base)
from app.models import invite as invite_models  # noqa: F401  (registers TeamInvite on Base)
from app.models import payment as payment_models  # noqa: F401  (registers Payment on Base)
from app.models import plan as plan_models  # noqa: F401  (registers Plan on Base)
from app.models import product_import as product_import_models  # noqa: F401  (registers ProductImport on Base)
from app.models import subscription as subscription_models  # noqa: F401  (registers TeamSubscription on Base)
from app.models import team as team_models  # noqa: F401  (registers Team/TeamMembership on Base)
from app.models import template as template_models  # noqa: F401  (registers Template on Base)
from app.models import tool as tool_models  # noqa: F401  (registers Tool on Base)
from app.models import user as user_models  # noqa: F401  (registers User on Base)
# Every model above still needs importing here even though schema itself is
# now Alembic's job (alembic/ — run `alembic upgrade head` before starting
# the app, not something main.py does for you): SQLAlchemy needs every
# mapped class registered on Base before mapper configuration runs, since
# relationships reference each other by string (e.g. Team.invites ->
# "TeamInvite"), same reason app/worker.py imports a couple of these too.
from app.routes.admin_routes import router as admin_router
from app.routes.asset_routes import router as asset_router
from app.routes.auth_routes import router as auth_router
from app.routes.billing_routes import router as billing_router
from app.routes.generation_routes import router as generation_router
from app.routes.health_routes import router as health_router
from app.routes.product_import_routes import router as product_import_router
from app.routes.team_routes import router as teams_router
from app.tools.sync import sync_tools_to_db

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
app.include_router(product_import_router)
app.include_router(admin_router)
app.include_router(billing_router)

try:
    _sync_db = SessionLocal()
    sync_tools_to_db(_sync_db)
    _sync_db.close()
except Exception as exc:
    # Tolerates a DB that isn't reachable yet at import time, same
    # crash-tolerance philosophy as init_firebase() above — the tools table
    # just stays whatever it was until the next successful boot, rather
    # than taking the whole API down over a non-critical sync.
    print(f"[tools] sync_tools_to_db failed at startup: {exc}")


@app.get("/")
def root():
    return {"message": f"{settings.APP_NAME} API is running"}
