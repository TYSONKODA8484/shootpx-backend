from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App-wide settings, loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "ShootPX"
    ENV: str = "development"
    DEBUG: bool = True

    # Public URLs. TEST_CONSOLE_URL is the bare-bones local HTML page used to
    # exercise the API by hand before the real frontend is wired up.
    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"
    TEST_CONSOLE_URL: str = "http://localhost:5500"

    # Database
    DATABASE_URL: str = "sqlite:///./shootpx.db"

    # Signing key for our own session cookie (itsdangerous). This is separate
    # from Firebase — Firebase proves who the user is once, then we issue our
    # own short-lived proof so we don't re-verify a Firebase token every request.
    # MUST be overridden in .env with a long random value.
    SECRET_KEY: str = "change-me"
    SESSION_MAX_AGE_SECONDS: int = 60 * 60 * 24 * 7  # 7 days

    # Firebase Admin SDK — path to the service-account JSON key downloaded from
    # Firebase Console -> Project Settings -> Service Accounts -> Generate new
    # private key. Used only to verify tokens the frontend already obtained
    # from Firebase; never talks to Google directly.
    FIREBASE_SERVICE_ACCOUNT_PATH: str = "./firebase-service-account.json"

    # Local file storage for uploaded/generated assets (core/storage.py).
    # Swap LocalStorage for an R2/S3-backed implementation later.
    STORAGE_ROOT_DIR: str = "./storage"

    # Redis — backs the arq task queue (app/worker.py) and the per-team
    # generation lock. Get one running locally first; see DESIGN.md.
    REDIS_URL: str = "redis://localhost:6379/0"

    # Hard cap on how many generation jobs run at once, across every team
    # combined — protects whatever real AI API gets wired in later from
    # unlimited parallel requests. Independent of the per-team lock (that
    # one limits fairness *between* teams; this one limits total load).
    MAX_CONCURRENT_GENERATIONS: int = 10

    # Artificial delay (seconds) the worker sleeps before calling
    # MockAIProvider, since the mock itself returns instantly. Without this,
    # the per-team lock has nothing to serialize that's slow enough to
    # observe by polling. Set to 0 once a real (naturally slow) AI provider
    # replaces the mock.
    MOCK_GENERATION_DELAY_SECONDS: int = 3

    # Outgoing email (Resend SMTP) — sends the magic-link and team-invite
    # emails ourselves; Firebase never sends mail in this project.
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM_NAME: str = "ShootPX"
    EMAIL_FROM_ADDRESS: str = ""


settings = Settings()
