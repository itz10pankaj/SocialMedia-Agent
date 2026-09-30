"""Settings: secrets/machine-specific values from .env, everything else from config.yaml."""
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_fallback_url: str = ""
    ollama_fallback_model: str = ""

    run_on_startup: bool = False
    # MySQL, e.g. mysql+pymysql://user:<password>@localhost:3306/social_agent?charset=utf8mb4
    database_url: str

    # Gmail SMTP
    gmail_address: str = ""
    gmail_app_password: str = ""
    notify_email: str = "pgarg9355@gmail.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
