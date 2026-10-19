from app.agent.answer_generator import AnswerGenerator
from app.agent.memory import ConversationMessage
from app.agent.pipeline import ChatbotPipeline
from app.agent.sql_generator import SQLGenerator
from app.agent.sql_validator import SQLValidationError, SQLValidator
from app.config import Settings, get_settings
from app.db.connection import Database
from app.db.executor import QueryExecutor
from app.db.schema import SchemaReader
from app.llm.client import MaritacaClient


def build_pipeline(
    settings: Settings,
    database: Database,
    allowed_views: tuple[str, ...] | None = None,
) -> ChatbotPipeline:
    views = allowed_views or settings.allowed_view_names
    llm = MaritacaClient(settings)
    return ChatbotPipeline(
        schema_reader=SchemaReader(database, views),
        sql_generator=SQLGenerator(llm),
        sql_validator=SQLValidator(views, settings.max_rows),
        executor=QueryExecutor(database),
        answer_generator=AnswerGenerator(llm),
    )


def main() -> None:
    settings = get_settings()
    print(
        "Chatbot SQL iniciado. Digite 'sair' para encerrar, '/schema' para "
        "recarregar ou '/nova' para limpar a conversa."
    )

    with Database(settings) as database:
        pipeline = build_pipeline(settings, database)
        pipeline.refresh_schema()
        history: list[ConversationMessage] = []

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
            if question == "/nova":
                history.clear()
                print("Historico da conversa limpo.")
                continue
            if not question:
                continue

            try:
                result = pipeline.ask(question, tuple(history))
                if settings.show_sql:
                    print(f"\nSQL> {result.executed_sql}")
                print(f"\nAssistente> {result.answer}")
                history.extend(
                    [
                        ConversationMessage(role="user", content=question),
                        ConversationMessage(role="assistant", content=result.answer),
                    ]
                )
                history = history[-settings.conversation_window_messages :]
            except SQLValidationError as exc:
                print(f"\nConsulta rejeitada por seguranca: {exc}")
            except Exception as exc:
                print(f"\nNao foi possivel responder: {exc}")


if __name__ == "__main__":
    main()
