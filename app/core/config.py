from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql://dios:dios@db:5432/dios"
    APP_ENV: str = "development"
    SECRET_KEY: str = "changeme-secret-key"


settings = Settings()
