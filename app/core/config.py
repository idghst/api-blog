from functools import lru_cache
from typing import ClassVar

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.url_validation import require_http_origin


class Settings(BaseSettings):
    """Validated runtime configuration loaded from the environment."""

    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

    DATABASE_URL: SecretStr
    BLOG_API_KEY: SecretStr | None = None
    VIEW_HASH_SALT: SecretStr | None = None

    app_name: ClassVar[str] = "Blog API"
    CORS_ORIGINS: ClassVar[list[str]] = [
        require_http_origin("http://localhost:3000", allow_root_path=False),
        require_http_origin("https://blog.idghst.co.kr", allow_root_path=False),
    ]
    DB_TIMEOUT_SECONDS: ClassVar[int] = 5

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def require_postgres_url(cls, value: object) -> object:
        raw_value = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not isinstance(raw_value, str) or not raw_value.startswith(
            ("postgresql://", "postgres://")
        ):
            raise ValueError("DATABASE_URL must be a postgresql:// URL")
        return value

    @field_validator("BLOG_API_KEY", "VIEW_HASH_SALT", mode="before")
    @classmethod
    def normalize_blank_optional_secret(cls, value: object) -> object:
        raw_value = value.get_secret_value() if isinstance(value, SecretStr) else value
        if isinstance(raw_value, str) and not raw_value.strip():
            return None
        return value

    def view_hash_secret(self) -> str | None:
        """조회수 방문자 해싱 키. 없으면 방문자를 식별하지 않는다."""

        return (
            None
            if self.VIEW_HASH_SALT is None
            else self.VIEW_HASH_SALT.get_secret_value()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # Loaded from the environment.


def clear_settings_cache() -> None:
    get_settings.cache_clear()
