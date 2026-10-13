from dataclasses import dataclass
from typing import Any

from app.db.connection import Database


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]


class QueryExecutor:
    def __init__(self, database: Database) -> None:
        self._database = database

    def execute(self, sql: str) -> QueryResult:
        with self._database.readonly_connection() as connection:
            cursor = connection.execute(sql)
            columns = [column.name for column in cursor.description or []]
            rows = [dict(row) for row in cursor.fetchall()]
        return QueryResult(columns=columns, rows=rows)

