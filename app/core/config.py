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

    # How long MockAIProvider pretends a submitted job takes to finish
    # (checked by the worker's poll, not slept inline — see AIProvider.submit
    # / poll_result in core/ai_provider.py). Without this, the mock would
    # resolve on the very first poll and there'd be nothing slow enough for
    # the per-team lock to visibly serialize. Irrelevant once a real
    # (naturally slow) provider replaces the mock.
    MOCK_GENERATION_DELAY_SECONDS: int = 3

    # How often the worker re-checks a submitted job's status with the
    # provider (app/worker.py, via arq's Retry — never a blocking sleep, so
    # it costs nothing while waiting). Real providers bill/rate-limit polls,
    # so don't set this too low against a real (non-mock) provider.
    GENERATION_POLL_INTERVAL_SECONDS: int = 3

    # Ceiling on how long one job may stay unresolved after being submitted
    # to the provider before the worker gives up and marks it failed —
    # protects against a provider job that silently never completes/never
    # reports failure. Independent of arq's own job_timeout (WorkerSettings
    # in worker.py), which bounds a single submit/poll HTTP call, not the
    # job's total lifetime.
    GENERATION_TIMEOUT_SECONDS: int = 600

    # Outgoing email (Resend SMTP) — sends the magic-link and team-invite
    # emails ourselves; Firebase never sends mail in this project.
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM_NAME: str = "ShootPX"
    EMAIL_FROM_ADDRESS: str = ""


settings = Settings()
