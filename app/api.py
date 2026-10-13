import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from openai import APIError
from psycopg import Error as PsycopgError
from pydantic import BaseModel, Field

from app.agent.pipeline import ChatbotPipeline
from app.agent.sql_validator import SQLValidationError
from app.config import get_settings
from app.db.connection import Database
from app.main import build_pipeline

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)


class ChatResponse(BaseModel):
    question: str
    answer: str
    generated_sql: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]


class HealthResponse(BaseModel):
    status: str
    database: str
    model: str


def create_app(pipeline_override: ChatbotPipeline | None = None) -> FastAPI:
    """Cria a API; o override permite testes sem banco nem chamadas externas."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if pipeline_override is not None:
            app.state.pipeline = pipeline_override
            app.state.database = None
            app.state.model = "test"
            yield
            return

        settings = get_settings()
        database = Database(settings)
        try:
            database.open()
            pipeline = build_pipeline(settings, database)
            pipeline.refresh_schema()
            app.state.pipeline = pipeline
            app.state.database = database
            app.state.model = settings.maritaca_model
            yield
        finally:
            database.close()

    app = FastAPI(
        title="Chatbot SQL",
        description="Perguntas em linguagem natural sobre views PostgreSQL read-only.",
        version="1.0.0",
        lifespan=lifespan,
    )

    async def get_pipeline(request: Request) -> ChatbotPipeline:
        return request.app.state.pipeline

    @app.get("/health", response_model=HealthResponse, tags=["monitoring"])
    async def health(request: Request) -> HealthResponse:
        database: Database | None = request.app.state.database
        if database is not None:
            try:
                def check_database() -> None:
                    with database.readonly_connection() as connection:
                        connection.execute("SELECT 1").fetchone()

                await asyncio.to_thread(check_database)
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
        )

    @app.post("/chat", response_model=ChatResponse, tags=["chat"])
    async def chat(
        payload: ChatRequest,
        pipeline: ChatbotPipeline = Depends(get_pipeline),
    ) -> ChatResponse:
        question = payload.question.strip()
        if not question:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A pergunta nao pode estar vazia",
            )

        try:
            result = await asyncio.to_thread(pipeline.ask, question)
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

        return ChatResponse(
            question=question,
            answer=result.answer,
            generated_sql=result.generated_sql,
            sql=result.executed_sql,
            columns=result.columns,
            rows=result.rows,
        )

    return app


app = create_app()
