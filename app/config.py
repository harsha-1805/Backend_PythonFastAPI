"""
Application configuration.

Centralizes all environment-driven settings so the rest of the app never
reads os.environ directly. Phase 2: the database has been migrated from
SQLite to PostgreSQL. `database_url` MUST be provided via the .env file
(no SQLite fallback is used anywhere in the app anymore).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Database -----------------------------------------------------
    # PostgreSQL only. Example:
    # postgresql+psycopg2://bugpilot_user:bugpilot_pass@localhost:5432/bugpilot_db
    database_url: str = (
        "postgresql+psycopg2://bugpilot_user:bugpilot_pass@localhost:5432/bugpilot_db"
    )

    # --- Auth / JWT -----------------------------------------------------
    secret_key: str = "change-this-to-a-long-random-secret-key"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # --- CORS -----------------------------------------------------------
    # Comma separated list of allowed origins for the frontend dev server.
    cors_origins: str = "http://localhost:5173"

    # --- App metadata -----------------------------------------------------
    app_name: str = "BugPilot AI"
    api_v1_prefix: str = "/api/v1"

    # --- AI / Gemini ------------------------------------------------------
    # Google Gemini API key (https://aistudio.google.com/app/apikey).
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # --- AI Bug Generator upload limits ------------------------------------
    max_image_size_mb: int = 8
    max_text_field_chars: int = 20000
    allowed_image_content_types: str = "image/png,image/jpeg,image/jpg,image/webp"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def allowed_image_content_type_list(self):
        return [t.strip() for t in self.allowed_image_content_types.split(",") if t.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


# Singleton settings instance used across the app.
settings = Settings()
