from dataclasses import dataclass
from typing import Any, Protocol

from app.agent.answer_generator import AnswerGenerator
from app.agent.memory import ConversationMessage
from app.agent.sql_generator import SQLGenerator
from app.agent.sql_validator import SQLValidator
from app.db.executor import QueryExecutor
from app.db.schema import SchemaReader


class SchemaProvider(Protocol):
    def describe(self) -> str: ...


@dataclass(frozen=True)
class PipelineResult:
    answer: str
    generated_sql: str
    executed_sql: str
    columns: list[str]
    rows: list[dict[str, Any]]


class ChatbotPipeline:
    def __init__(
        self,
        schema_reader: SchemaProvider,
        sql_generator: SQLGenerator,
        sql_validator: SQLValidator,
        executor: QueryExecutor,
        answer_generator: AnswerGenerator,
    ) -> None:
        self._schema_reader = schema_reader
        self._sql_generator = sql_generator
        self._sql_validator = sql_validator
        self._executor = executor
        self._answer_generator = answer_generator
        self._schema_cache: str | None = None

    def refresh_schema(self) -> str:
        self._schema_cache = self._schema_reader.describe()
        return self._schema_cache

    def ask(
        self,
        question: str,
        history: tuple[ConversationMessage, ...] = (),
    ) -> PipelineResult:
        schema = self._schema_cache or self.refresh_schema()
        generated_sql = self._sql_generator.generate(question, schema, history)
        executed_sql = self._sql_validator.validate_and_rewrite(generated_sql)
        query_result = self._executor.execute(executed_sql)
        answer = self._answer_generator.generate(
            question,
            executed_sql,
            query_result.columns,
            query_result.rows,
            history,
        )
        return PipelineResult(
            answer=answer,
            generated_sql=generated_sql,
            executed_sql=executed_sql,
            columns=query_result.columns,
            rows=query_result.rows,
        )
