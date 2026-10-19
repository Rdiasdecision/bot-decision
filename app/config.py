import re
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracoes carregadas do ambiente ou do arquivo .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    maritaca_api_key: str = Field(min_length=1)
    maritaca_model: str = "sabiazinho-4"
    maritaca_base_url: str = "https://chat.maritaca.ai/api"

    database_url: str | None = None
    db_host: str = "localhost"
    db_port: int = Field(default=5432, ge=1, le=65_535)
    db_name: str | None = None
    db_user: str = "chatbot_reader"
    db_password: SecretStr | None = None
    db_sslmode: str = "prefer"
    allowed_views: str = Field(
        min_length=1,
        description="Views no formato schema.view, separadas por virgula.",
    )
    screen_views: dict[str, list[str]] = Field(default_factory=dict)
    max_rows: int = Field(default=100, ge=1, le=10_000)
    statement_timeout_ms: int = Field(default=10_000, ge=100, le=300_000)
    db_pool_min_size: int = Field(default=1, ge=1, le=20)
    db_pool_max_size: int = Field(default=5, ge=1, le=50)

    llm_timeout_seconds: float = Field(default=60, gt=0, le=300)
    llm_temperature: float = Field(default=0, ge=0, le=2)
    show_sql: bool = True
    conversation_window_messages: int = Field(default=8, ge=2, le=50)
    max_conversation_sessions: int = Field(default=1_000, ge=1, le=100_000)

    @field_validator("maritaca_base_url")
    @classmethod
    def remove_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("database_url", "db_name", mode="before")
    @classmethod
    def empty_string_is_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("allowed_views")
    @classmethod
    def validate_allowed_views(cls, value: str) -> str:
        views = [item.strip() for item in value.split(",") if item.strip()]
        if not views:
            raise ValueError("ALLOWED_VIEWS deve conter ao menos uma view")
        for view in views:
            parts = view.split(".")
            if len(parts) != 2 or not all(parts):
                raise ValueError(
                    f"View invalida: {view!r}. Use o formato schema.view."
                )
        return ",".join(views)

    @field_validator("screen_views")
    @classmethod
    def validate_screen_views(
        cls, value: dict[str, list[str]]
    ) -> dict[str, list[str]]:
        normalized: dict[str, list[str]] = {}
        for raw_screen, raw_views in value.items():
            screen = raw_screen.strip().lower()
            if not re.fullmatch(r"[a-z0-9_-]+", screen):
                raise ValueError(
                    f"Tela invalida: {raw_screen!r}. Use letras, numeros, _ ou -."
                )
            views = [view.strip().lower() for view in raw_views if view.strip()]
            if not views:
                raise ValueError(f"A tela {screen!r} deve possuir ao menos uma view")
            for view in views:
                parts = view.split(".")
                if len(parts) != 2 or not all(parts):
                    raise ValueError(
                        f"View invalida na tela {screen!r}: {view!r}. "
                        "Use schema.view."
                    )
            normalized[screen] = list(dict.fromkeys(views))
        return normalized

    @property
    def allowed_view_names(self) -> tuple[str, ...]:
        return tuple(view.strip() for view in self.allowed_views.split(","))

    @property
    def views_by_screen(self) -> dict[str, tuple[str, ...]]:
        if not self.screen_views:
            return {"default": self.allowed_view_names}
        return {
            screen: tuple(views) for screen, views in self.screen_views.items()
        }

    @field_validator("db_pool_max_size")
    @classmethod
    def pool_max_must_be_valid(cls, value: int, info) -> int:
        minimum = info.data.get("db_pool_min_size", 1)
        if value < minimum:
            raise ValueError("DB_POOL_MAX_SIZE deve ser >= DB_POOL_MIN_SIZE")
        return value

    @model_validator(mode="after")
    def database_credentials_are_complete(self) -> "Settings":
        if not self.database_url:
            missing: list[str] = []
            if not self.db_name:
                missing.append("DB_NAME")
            if not self.db_user.strip():
                missing.append("DB_USER")
            if self.db_password is None or not self.db_password.get_secret_value():
                missing.append("DB_PASSWORD")
            if missing:
                raise ValueError(
                    "Defina DATABASE_URL ou informe as credenciais: "
                    + ", ".join(missing)
                )

        allowed = {view.lower() for view in self.allowed_view_names}
        outside_allowlist = {
            view
            for views in self.screen_views.values()
            for view in views
            if view.lower() not in allowed
        }
        if outside_allowlist:
            raise ValueError(
                "SCREEN_VIEWS contem views ausentes de ALLOWED_VIEWS: "
                + ", ".join(sorted(outside_allowlist))
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
