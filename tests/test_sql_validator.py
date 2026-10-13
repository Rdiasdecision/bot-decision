import pytest

from app.agent.sql_validator import SQLValidationError, SQLValidator


@pytest.fixture
def validator() -> SQLValidator:
    return SQLValidator(("public.vw_vendas", "public.vw_clientes"), max_rows=100)


def test_accepts_select_and_adds_limit(validator: SQLValidator) -> None:
    sql = validator.validate_and_rewrite(
        "SELECT cliente_id, SUM(valor) FROM public.vw_vendas GROUP BY cliente_id"
    )
    assert "LIMIT 100" in sql
    assert "public.vw_vendas" in sql


def test_preserves_smaller_limit(validator: SQLValidator) -> None:
    sql = validator.validate_and_rewrite("SELECT * FROM public.vw_vendas LIMIT 10")
    assert "LIMIT 10" in sql


def test_clamps_larger_limit(validator: SQLValidator) -> None:
    sql = validator.validate_and_rewrite("SELECT * FROM public.vw_vendas LIMIT 9999")
    assert "LIMIT 100" in sql


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM public.vw_vendas",
        "UPDATE public.vw_vendas SET valor = 0",
        "DROP VIEW public.vw_vendas",
        "SELECT * INTO copia FROM public.vw_vendas",
        "SELECT * FROM public.vw_vendas; SELECT * FROM public.vw_clientes",
    ],
)
def test_rejects_unsafe_statements(validator: SQLValidator, sql: str) -> None:
    with pytest.raises(SQLValidationError):
        validator.validate_and_rewrite(sql)


def test_rejects_non_allowed_view(validator: SQLValidator) -> None:
    with pytest.raises(SQLValidationError, match="nao permitida"):
        validator.validate_and_rewrite("SELECT * FROM private.usuarios")


def test_accepts_cte_over_allowed_view(validator: SQLValidator) -> None:
    sql = validator.validate_and_rewrite(
        "WITH vendas AS (SELECT * FROM public.vw_vendas) SELECT * FROM vendas"
    )
    assert "LIMIT 100" in sql

