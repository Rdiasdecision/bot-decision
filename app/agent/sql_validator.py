import re

from sqlglot import exp, parse
from sqlglot.errors import ParseError


class SQLValidationError(ValueError):
    """SQL rejeitado antes de chegar ao PostgreSQL."""


FORBIDDEN_NODE_NAMES = {
    "alter",
    "analyze",
    "attach",
    "cache",
    "command",
    "copy",
    "create",
    "delete",
    "detach",
    "drop",
    "grant",
    "insert",
    "load",
    "lock",
    "merge",
    "pragma",
    "refresh",
    "revoke",
    "set",
    "transaction",
    "truncate",
    "uncache",
    "update",
    "use",
}


def _strip_markdown_fence(sql: str) -> str:
    value = sql.strip()
    match = re.fullmatch(r"```(?:sql)?\s*(.*?)\s*```", value, flags=re.I | re.S)
    return match.group(1).strip() if match else value


class SQLValidator:
    def __init__(self, allowed_views: tuple[str, ...], max_rows: int) -> None:
        if not allowed_views:
            raise ValueError("A allowlist de views nao pode estar vazia")
        self._allowed_views = {view.lower() for view in allowed_views}
        self._max_rows = max_rows

    def validate_and_rewrite(self, sql: str) -> str:
        candidate = _strip_markdown_fence(sql)
        try:
            statements = [item for item in parse(candidate, read="postgres") if item]
        except ParseError as exc:
            raise SQLValidationError(f"SQL invalido: {exc}") from exc

        if len(statements) != 1:
            raise SQLValidationError("A resposta deve conter exatamente uma instrucao SQL")

        statement = statements[0]
        if not isinstance(statement, exp.Query):
            raise SQLValidationError("Somente consultas SELECT sao permitidas")

        for node in statement.walk():
            if node.key.lower() in FORBIDDEN_NODE_NAMES:
                raise SQLValidationError(f"Operacao proibida encontrada: {node.key}")

        for select in statement.find_all(exp.Select):
            if select.args.get("into") is not None:
                raise SQLValidationError("SELECT INTO nao e permitido")

        cte_names = {
            cte.alias_or_name.lower()
            for cte in statement.find_all(exp.CTE)
            if cte.alias_or_name
        }
        referenced_views: set[str] = set()
        for table in statement.find_all(exp.Table):
            table_name = table.name.lower()
            if not table.db and table_name in cte_names:
                continue

            if table.db:
                qualified = f"{table.db}.{table.name}".lower()
                if qualified not in self._allowed_views:
                    raise SQLValidationError(f"View nao permitida: {qualified}")
                referenced_views.add(qualified)
                continue

            matches = {
                allowed
                for allowed in self._allowed_views
                if allowed.rsplit(".", 1)[-1] == table_name
            }
            if len(matches) != 1:
                raise SQLValidationError(
                    f"View nao qualificada, desconhecida ou ambigua: {table.name}"
                )
            referenced_views.update(matches)

        if not referenced_views:
            raise SQLValidationError("A consulta deve ler ao menos uma view permitida")

        limit = statement.args.get("limit")
        current_limit: int | None = None
        if limit is not None and isinstance(limit.expression, exp.Literal):
            try:
                current_limit = int(limit.expression.this)
            except (TypeError, ValueError):
                current_limit = None

        if current_limit is None or current_limit > self._max_rows or current_limit < 1:
            statement = statement.limit(self._max_rows, copy=False)

        return statement.sql(dialect="postgres")

