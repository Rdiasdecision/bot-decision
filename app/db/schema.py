from collections import defaultdict

from app.db.connection import Database


SCHEMA_QUERY = """
SELECT
    cols.table_schema,
    cols.table_name,
    cols.ordinal_position,
    cols.column_name,
    cols.data_type,
    pg_catalog.col_description(cls.oid, attrs.attnum) AS column_comment,
    pg_catalog.obj_description(cls.oid, 'pg_class') AS view_comment
FROM information_schema.columns AS cols
JOIN pg_catalog.pg_namespace AS ns
  ON ns.nspname = cols.table_schema
JOIN pg_catalog.pg_class AS cls
  ON cls.relnamespace = ns.oid
 AND cls.relname = cols.table_name
JOIN pg_catalog.pg_attribute AS attrs
  ON attrs.attrelid = cls.oid
 AND attrs.attname = cols.column_name
WHERE (cols.table_schema || '.' || cols.table_name) = ANY(%s)
  AND cls.relkind IN ('v', 'm')
ORDER BY cols.table_schema, cols.table_name, cols.ordinal_position
"""


class SchemaReader:
    def __init__(self, database: Database, allowed_views: tuple[str, ...]) -> None:
        self._database = database
        self._allowed_views = allowed_views

    def describe(self) -> str:
        with self._database.readonly_connection() as connection:
            rows = connection.execute(SCHEMA_QUERY, (list(self._allowed_views),)).fetchall()

        grouped: dict[str, list[dict]] = defaultdict(list)
        comments: dict[str, str | None] = {}
        for row in rows:
            name = f"{row['table_schema']}.{row['table_name']}"
            grouped[name].append(row)
            comments[name] = row["view_comment"]

        missing = set(self._allowed_views) - set(grouped)
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise RuntimeError(
                "Views nao encontradas ou sem permissao para inspecionar: " + missing_text
            )

        descriptions: list[str] = []
        for view_name in self._allowed_views:
            view_comment = comments.get(view_name)
            header = f"VIEW {view_name}"
            if view_comment:
                header += f" -- {view_comment}"
            descriptions.append(header)
            for column in grouped[view_name]:
                line = f"  - {column['column_name']} ({column['data_type']})"
                if column["column_comment"]:
                    line += f": {column['column_comment']}"
                descriptions.append(line)

        return "\n".join(descriptions)

