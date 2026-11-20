import pytest
from pydantic import ValidationError

from app.core.config import Settings, clear_settings_cache, get_settings
from app.core.url_validation import require_http_origin

URL = "postgresql://blog_app@db:5432/blog"


def test_removed_env_fields_are_not_settings() -> None:
    assert "APP_ENV" not in Settings.model_fields
    assert "LOG_LEVEL" not in Settings.model_fields
    assert "ENABLE_DOCS" not in Settings.model_fields
    assert "CORS_ORIGINS" not in Settings.model_fields
    assert not [name for name in Settings.model_fields if "SUPABASE" in name]


def test_app_name_and_timeout_are_fixed() -> None:
    settings = Settings(DATABASE_URL=URL)

    assert settings.app_name == "Blog API"
    assert settings.DB_TIMEOUT_SECONDS == 5


@pytest.mark.parametrize("url", ["", "mysql://db/blog", "https://db.example.com"])
def test_database_url_must_be_postgres(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(DATABASE_URL=url)


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL")

    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_optional_secrets_default_to_none_and_blank_becomes_none() -> None:
    assert Settings(DATABASE_URL=URL).BLOG_API_KEY is None
    settings = Settings(DATABASE_URL=URL, BLOG_API_KEY="   ", VIEW_HASH_SALT=" ")

    assert settings.BLOG_API_KEY is None
    assert settings.VIEW_HASH_SALT is None
    assert settings.view_hash_secret() is None
    assert Settings(DATABASE_URL=URL, VIEW_HASH_SALT="s").view_hash_secret() == "s"


def test_cors_origins_are_fixed() -> None:
    settings = Settings(DATABASE_URL=URL)

    assert settings.CORS_ORIGINS == [
        "http://localhost:3000",
        "https://blog.idghst.co.kr",
    ]
    assert "*" not in settings.CORS_ORIGINS


def test_cors_rejects_wildcard() -> None:
    with pytest.raises(ValueError):
        require_http_origin("*", allow_root_path=False)


@pytest.mark.parametrize(
    "cors_origin",
    [
        "null",
        "ftp://localhost:3000",
        "http://user:password@localhost:3000",
        "http://localhost:3000/api",
        "http://localhost:3000/",
        "http://localhost:3000?preview=true",
        "http://localhost:3000#section",
        "http:///missing-host",
        "http://localhost\\evil.com",
        "http://localhost:",
        "http://.",
        " http://localhost:3000",
        "http://localhost:3000 ",
        "http://localhost:3000\n",
        "http://localhost:3000\x00",
        "",
    ],
)
def test_cors_rejects_non_origin_values(cors_origin: str) -> None:
    with pytest.raises(ValueError):
        require_http_origin(cors_origin, allow_root_path=False)


@pytest.mark.parametrize(
    "cors_origin",
    [
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        "http://[::1]:8000",
        "https://api.example.com:8443",
    ],
)
def test_cors_allows_concrete_origins(cors_origin: str) -> None:
    assert require_http_origin(cors_origin, allow_root_path=False) == cors_origin


def test_settings_cache_can_be_cleared(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_cache()
    monkeypatch.setenv("DATABASE_URL", URL)
    first = get_settings()
    monkeypatch.setenv("DATABASE_URL", "postgresql://other@db/blog")
    assert get_settings() is first

    clear_settings_cache()
    assert (
        get_settings().DATABASE_URL.get_secret_value() == "postgresql://other@db/blog"
    )
