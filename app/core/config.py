from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql://dios:dios@db:5432/dios"
    APP_ENV: str = "development"
    SECRET_KEY: str = "changeme-secret-key"

    # Comma-separated allowed origins, or "*" to allow all.
    # Example: "https://myapp.com,https://api.myapp.com"
    CORS_ORIGINS: str = "*"

    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
