from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    supabase_key: str = ""          # alternate name; supabase_service_key takes priority

    # Auth
    secret_key: str = "municipality-secret-2025"
    jwt_secret: str = ""

    # AI
    anthropic_api_key: str = ""

    # Payments
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""

    # External APIs
    openweather_api_key: str = ""
    tomtom_api_key: str = ""
    here_api_key: str = ""
    google_places_key: str = ""

    # Email (Brevo)
    brevo_api_key: str = ""
    admin_email: str = ""
    smtp_user: str = "noreply@municipality.gr"

    # Firebase
    firebase_service_account: str = ""

    # App
    backend_url: str = "https://municipality-backend-production.up.railway.app"
    log_level: str = "INFO"
    environment: str = "production"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


settings = Settings()

# ── Backward-compatible uppercase exports ─────────────────────────────────────
# Existing files that do `from app.config import SUPABASE_URL` keep working.
SUPABASE_URL         = settings.supabase_url
SUPABASE_ANON_KEY    = settings.supabase_anon_key
SUPABASE_SERVICE_KEY = settings.supabase_service_key or settings.supabase_key
ANTHROPIC_API_KEY    = settings.anthropic_api_key
SECRET_KEY           = settings.secret_key
STRIPE_SECRET_KEY    = settings.stripe_secret_key
STRIPE_PUBLISHABLE_KEY = settings.stripe_publishable_key
OPENWEATHER_API_KEY  = settings.openweather_api_key
TOMTOM_API_KEY       = settings.tomtom_api_key
