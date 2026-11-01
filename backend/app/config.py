"""Runtime configuration, read from environment variables (and a local .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

_DEV_SECRET = "dev-only-secret-change-me-please-0123456789"


@dataclass(frozen=True)
class Settings:
    env: str
    database_path: str
    secret_key: str
    token_ttl_minutes: int
    cors_origins: list[str]
    anthropic_api_key: str
    ai_model: str
    ai_timeout_seconds: int
    seed_demo_data: bool

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


def load_settings() -> Settings:
    env = os.getenv("APP_ENV", "development")
    secret = os.getenv("SECRET_KEY", _DEV_SECRET)
    if env == "production":
        if secret == _DEV_SECRET or len(secret) < 32:
            raise RuntimeError("SECRET_KEY must be set to a random string of 32+ characters in production")
        if os.getenv("SEED_DEMO_DATA", "false").lower() in ("1", "true", "yes"):
            raise RuntimeError("SEED_DEMO_DATA must be false in production")
        if "*" in os.getenv("CORS_ORIGINS", ""):
            raise RuntimeError("Wildcard CORS origins are not allowed in production")
    return Settings(
        env=env,
        database_path=os.getenv("DATABASE_PATH", str(BASE_DIR / "gramsathi.db")),
        secret_key=secret,
        token_ttl_minutes=int(os.getenv("TOKEN_TTL_MINUTES", "720")),
        cors_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",") if o.strip()],
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        ai_model=os.getenv("AI_MODEL", "claude-sonnet-5-5"),
        ai_timeout_seconds=int(os.getenv("AI_TIMEOUT_SECONDS", "30")),
        seed_demo_data=os.getenv("SEED_DEMO_DATA", "true").lower() in ("1", "true", "yes"),
    )
