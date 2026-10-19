import pytest
from pydantic import ValidationError

from app.config import Settings


BASE = {
    "maritaca_api_key": "test-key",
    "allowed_views": "public.vw_vendas",
}


def test_accepts_separate_database_credentials() -> None:
    settings = Settings(
        **BASE,
        db_name="financeiro",
        db_user="chatbot_reader",
        db_password="segredo",
        _env_file=None,
    )

    assert settings.db_name == "financeiro"
    assert settings.db_user == "chatbot_reader"
    assert settings.db_password is not None
    assert settings.db_password.get_secret_value() == "segredo"


def test_database_url_can_replace_separate_credentials() -> None:
    settings = Settings(
        **BASE,
        database_url="postgresql://reader:secret@db:5432/financeiro",
        _env_file=None,
    )

    assert settings.database_url is not None


def test_rejects_incomplete_database_credentials() -> None:
    with pytest.raises(ValidationError, match="DB_NAME.*DB_PASSWORD"):
        Settings(**BASE, _env_file=None)


def test_maps_each_screen_to_its_views() -> None:
    settings = Settings(
        **{**BASE, "allowed_views": "public.vw_vendas,crm.vw_clientes"},
        screen_views={
            "vendas": ["public.vw_vendas"],
            "clientes": ["crm.vw_clientes"],
        },
        database_url="postgresql://reader:secret@db:5432/financeiro",
        _env_file=None,
    )

    assert settings.views_by_screen == {
        "vendas": ("public.vw_vendas",),
        "clientes": ("crm.vw_clientes",),
    }


def test_rejects_screen_view_outside_global_allowlist() -> None:
    with pytest.raises(ValidationError, match="ausentes de ALLOWED_VIEWS"):
        Settings(
            **BASE,
            screen_views={"admin": ["private.usuarios"]},
            database_url="postgresql://reader:secret@db:5432/financeiro",
            _env_file=None,
        )
