from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str

    # Security
    secret_key: str
    token_encryption_key: str
    access_token_expire_hours: int = 8
    algorithm: str = "HS256"

    # Spotify
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://localhost:8000/auth/spotify/callback"

    # Apple Music
    apple_music_team_id: str = ""
    apple_music_key_id: str = ""
    apple_music_private_key: str = ""

    # Z.ai (GLM-5) — OpenAI-compatible endpoint
    zai_api_key: str = ""
    zai_base_url: str = "https://api.z.ai/api/paas/v4/"
    llm_model: str = "glm-5"

    # Paths
    users_config_path: str = "/app/users_config.json"
    password_reset_log_path: str = "/app/data/password_resets.log"

    # URLs
    frontend_url: str = "http://localhost:4200"

    # Apple Music storefront for catalog lookups
    apple_music_storefront: str = "us"


settings = Settings()
