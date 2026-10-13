from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import Connection
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import Settings


class Database:
    """Pool PostgreSQL que entrega apenas transacoes explicitamente read-only."""

    def __init__(self, settings: Settings) -> None:
        self._statement_timeout_ms = settings.statement_timeout_ms
        if settings.database_url:
            conninfo = settings.database_url
        else:
            assert settings.db_name is not None
            assert settings.db_password is not None
            conninfo = make_conninfo(
                host=settings.db_host,
                port=settings.db_port,
                dbname=settings.db_name,
                user=settings.db_user,
                password=settings.db_password.get_secret_value(),
                sslmode=settings.db_sslmode,
            )
        self._pool = ConnectionPool(
            conninfo=conninfo,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            kwargs={"row_factory": dict_row},
            open=False,
        )

    def open(self) -> None:
        self._pool.open(wait=True)

    def close(self) -> None:
        self._pool.close()

    @contextmanager
    def readonly_connection(self) -> Iterator[Connection]:
        with self._pool.connection() as connection:
            with connection.transaction():
                connection.execute("SET TRANSACTION READ ONLY")
                connection.execute(
                    "SELECT set_config('statement_timeout', %s, true)",
                    (str(self._statement_timeout_ms),),
                )
                yield connection

    def __enter__(self) -> "Database":
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
