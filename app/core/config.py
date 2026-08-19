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

    # product-scrapper service (separate repo/process — see
    # core/product_scraper_client.py) — turns a product URL into
    # name/description/price/theme/images. Its own submit/poll HTTP API,
    # same shape as AIProvider, run separately: `uvicorn service:app --port
    # 8501` from that repo.
    PRODUCT_SCRAPER_URL: str = "http://localhost:8501"
    PRODUCT_IMPORT_POLL_INTERVAL_SECONDS: int = 2
    PRODUCT_IMPORT_TIMEOUT_SECONDS: int = 120  # extract_product() itself
    # tops out around 25s; this is a generous ceiling above that, not a
    # tuned value — mirrors GENERATION_TIMEOUT_SECONDS's role for jobs.

    # Read-through caches (core/cache.py) — namespaced by concern so one
    # can be cleared without touching another. Short TTLs, not "cache
    # forever": correctness matters more than hit rate here.
    LOGIN_CACHE_TTL_SECONDS: int = 60  # caches the User row lookup that
    # get_current_user (middleware/auth.py) otherwise runs on every single
    # authenticated request. Short on purpose — a deleted/suspended user
    # should stop working within this long, not indefinitely. Also
    # explicitly invalidated the moment a user's row actually changes
    # (auth_controller.upsert_user_from_firebase), so this TTL is a ceiling
    # on staleness, not the only thing keeping it correct.
    MEDIA_CACHE_TTL_SECONDS: int = 300  # caches Asset row lookups
    # (core/asset_lookup.py), used wherever a job/batch response resolves
    # source/output asset ids — GET /jobs and GET /batches/{id} get polled
    # repeatedly while a job is running, re-resolving the same asset rows
    # every time. Safe to cache longer than the login cache: assets are
    # effectively immutable once created (no update/delete endpoint exists),
    # so there's no write path that needs to invalidate this.

    # Outgoing email (Resend SMTP) — sends the magic-link and team-invite
    # emails ourselves; Firebase never sends mail in this project.
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM_NAME: str = "ShootPX"
    EMAIL_FROM_ADDRESS: str = ""

    # Razorpay (core/payment_provider.py) — the payment provider seam's one
    # concrete implementation today. RAZORPAY_WEBHOOK_SECRET is a value we
    # choose, not one Razorpay hands us, used to verify that an incoming
    # POST /billing/webhook/razorpay request's signature is genuine.
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # Billing / credits (core/pricing.py, core/credits.py) — how often the
    # refill cron checks for due grants. Daily is fine for an ongoing
    # monthly cadence; the FIRST grant for any team is always synchronous,
    # never waits on this (see create_personal_team / the subscribe flow).
    CREDIT_REFILL_CRON_HOUR: int = 3  # 03:00 server time, low-traffic default


settings = Settings()
