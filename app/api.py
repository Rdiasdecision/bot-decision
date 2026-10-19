import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Path, Request, status
from openai import APIError
from psycopg import Error as PsycopgError
from pydantic import BaseModel, Field

from app.agent.memory import InMemoryConversationWindow
from app.agent.pipeline import ChatbotPipeline
from app.agent.sql_validator import SQLValidationError
from app.config import get_settings
from app.db.connection import Database
from app.main import build_pipeline

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    user_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    screen: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    question: str = Field(min_length=1, max_length=2_000)
    session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class ChatResponse(BaseModel):
    user_id: str
    screen: str
    session_id: str
    question: str
    answer: str
    generated_sql: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    history_messages: int


class HealthResponse(BaseModel):
    status: str
    database: str
    model: str
    screens: list[str]


class ClearSessionResponse(BaseModel):
    user_id: str
    screen: str
    session_id: str
    cleared: bool


def _memory_key(user_id: str, screen: str, session_id: str) -> str:
    return f"{user_id}\x1f{screen}\x1f{session_id}"


def create_app(
    pipeline_override: ChatbotPipeline | None = None,
    memory_override: InMemoryConversationWindow | None = None,
) -> FastAPI:
    """Cria a API; o override permite testes sem banco nem chamadas externas."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if pipeline_override is not None:
            app.state.pipelines = {"default": pipeline_override}
            app.state.database = None
            app.state.model = "test"
            app.state.memory = memory_override or InMemoryConversationWindow()
            yield
            return

        settings = get_settings()
        database = Database(settings)
        try:
            database.open()
            pipelines: dict[str, ChatbotPipeline] = {}
            for screen, views in settings.views_by_screen.items():
                pipeline = build_pipeline(settings, database, views)
                pipeline.refresh_schema()
                pipelines[screen] = pipeline
            app.state.pipelines = pipelines
            app.state.database = database
            app.state.model = settings.maritaca_model
            app.state.memory = memory_override or InMemoryConversationWindow(
                max_messages=settings.conversation_window_messages,
                max_sessions=settings.max_conversation_sessions,
            )
            yield
        finally:
            database.close()

    app = FastAPI(
        title="Chatbot SQL",
        description="Perguntas em linguagem natural sobre views PostgreSQL read-only.",
        version="1.0.0",
        lifespan=lifespan,
    )

    async def get_memory(request: Request) -> InMemoryConversationWindow:
        return request.app.state.memory

    @app.get("/health", response_model=HealthResponse, tags=["monitoring"])
    async def health(request: Request) -> HealthResponse:
        database: Database | None = request.app.state.database
        if database is not None:
            try:
                with database.readonly_connection() as connection:
                    connection.execute("SELECT 1").fetchone()
            except PsycopgError as exc:
                logger.exception("Falha no health check do PostgreSQL")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="PostgreSQL indisponivel",
                ) from exc

        return HealthResponse(
            status="ok",
            database="ok",
            model=request.app.state.model,
            screens=sorted(request.app.state.pipelines),
        )

    @app.post("/chat", response_model=ChatResponse, tags=["chat"])
    async def chat(
        payload: ChatRequest,
        request: Request,
        memory: InMemoryConversationWindow = Depends(get_memory),
    ) -> ChatResponse:
        question = payload.question.strip()
        screen = payload.screen.lower()
        session_id = payload.session_id or str(uuid4())
        pipeline: ChatbotPipeline | None = request.app.state.pipelines.get(screen)
        if pipeline is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tela nao autorizada ou inexistente",
            )
        if not question:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A pergunta nao pode estar vazia",
            )

        try:
            memory_key = _memory_key(payload.user_id, screen, session_id)
            history = memory.get(memory_key)
            result = pipeline.ask(question, history)
        except SQLValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Consulta rejeitada por seguranca: {exc}",
            ) from exc
        except PsycopgError as exc:
            logger.exception("Falha ao consultar o PostgreSQL")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="PostgreSQL indisponivel",
            ) from exc
        except APIError as exc:
            logger.exception("Falha ao consultar a Maritaca")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Modelo de linguagem indisponivel",
            ) from exc
        except Exception as exc:
            logger.exception("Falha inesperada no pipeline")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Nao foi possivel processar a pergunta",
            ) from exc

        memory.append_exchange(memory_key, question, result.answer)
        return ChatResponse(
            user_id=payload.user_id,
            screen=screen,
            session_id=session_id,
            question=question,
            answer=result.answer,
            generated_sql=result.generated_sql,
            sql=result.executed_sql,
            columns=result.columns,
            rows=result.rows,
            history_messages=len(memory.get(memory_key)),
        )

    @app.delete(
        "/users/{user_id}/screens/{screen}/sessions/{session_id}",
        response_model=ClearSessionResponse,
        tags=["chat"],
    )
    async def clear_session(
        user_id: str = Path(
            min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
        ),
        screen: str = Path(
            min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
        ),
        session_id: str = Path(
            min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
        ),
        memory: InMemoryConversationWindow = Depends(get_memory),
    ) -> ClearSessionResponse:
        normalized_screen = screen.lower()
        return ClearSessionResponse(
            user_id=user_id,
            screen=normalized_screen,
            session_id=session_id,
            cleared=memory.clear(_memory_key(user_id, normalized_screen, session_id)),
        )

    return app


app = create_app()
