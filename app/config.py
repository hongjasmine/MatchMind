from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    google_api_key: str = ""
    football_data_api_key: str = ""
    mongodb_uri: str = "mongodb://localhost:27017"
    redis_url: str = "redis://localhost:6379"
    app_env: str = "development"
    log_level: str = "INFO"
    cache_ttl_seconds: int = 30

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
