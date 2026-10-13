from app.agent.answer_generator import AnswerGenerator
from app.agent.pipeline import ChatbotPipeline
from app.agent.sql_generator import SQLGenerator
from app.agent.sql_validator import SQLValidationError, SQLValidator
from app.config import Settings, get_settings
from app.db.connection import Database
from app.db.executor import QueryExecutor
from app.db.schema import SchemaReader
from app.llm.client import MaritacaClient


def build_pipeline(settings: Settings, database: Database) -> ChatbotPipeline:
    llm = MaritacaClient(settings)
    return ChatbotPipeline(
        schema_reader=SchemaReader(database, settings.allowed_view_names),
        sql_generator=SQLGenerator(llm),
        sql_validator=SQLValidator(settings.allowed_view_names, settings.max_rows),
        executor=QueryExecutor(database),
        answer_generator=AnswerGenerator(llm),
    )


def main() -> None:
    settings = get_settings()
    print("Chatbot SQL iniciado. Digite 'sair' para encerrar ou '/schema' para recarregar.")

    with Database(settings) as database:
        pipeline = build_pipeline(settings, database)
        pipeline.refresh_schema()

        while True:
            try:
                question = input("\nVoce> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nAte logo!")
                break

            if question.lower() in {"sair", "exit", "quit"}:
                print("Ate logo!")
                break
            if question == "/schema":
                pipeline.refresh_schema()
                print("Esquema recarregado.")
                continue
            if not question:
                continue

            try:
                result = pipeline.ask(question)
                if settings.show_sql:
                    print(f"\nSQL> {result.executed_sql}")
                print(f"\nAssistente> {result.answer}")
            except SQLValidationError as exc:
                print(f"\nConsulta rejeitada por seguranca: {exc}")
            except Exception as exc:
                print(f"\nNao foi possivel responder: {exc}")


if __name__ == "__main__":
    main()

