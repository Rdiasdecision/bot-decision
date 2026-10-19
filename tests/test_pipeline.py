from app.agent.pipeline import ChatbotPipeline
from app.db.executor import QueryResult


class FakeSchemaReader:
    def describe(self) -> str:
        return "VIEW public.vw_vendas\n  - total (numeric)"


class FakeSQLGenerator:
    def generate(self, question: str, schema: str, history=()) -> str:
        assert question == "Qual o total?"
        assert "vw_vendas" in schema
        assert history == ()
        return "SELECT SUM(total) AS total FROM public.vw_vendas"


class FakeValidator:
    def validate_and_rewrite(self, sql: str) -> str:
        assert sql.startswith("SELECT")
        return sql + " LIMIT 100"


class FakeExecutor:
    def execute(self, sql: str) -> QueryResult:
        assert sql.endswith("LIMIT 100")
        return QueryResult(columns=["total"], rows=[{"total": 123.45}])


class FakeAnswerGenerator:
    def generate(self, question, sql, columns, rows, history=()) -> str:
        assert rows == [{"total": 123.45}]
        assert history == ()
        return "O total e R$ 123,45."


def test_pipeline_orchestrates_all_steps() -> None:
    pipeline = ChatbotPipeline(
        schema_reader=FakeSchemaReader(),
        sql_generator=FakeSQLGenerator(),  # type: ignore[arg-type]
        sql_validator=FakeValidator(),  # type: ignore[arg-type]
        executor=FakeExecutor(),  # type: ignore[arg-type]
        answer_generator=FakeAnswerGenerator(),  # type: ignore[arg-type]
    )

    result = pipeline.ask("Qual o total?")

    assert result.answer == "O total e R$ 123,45."
    assert result.columns == ["total"]
    assert result.executed_sql.endswith("LIMIT 100")
