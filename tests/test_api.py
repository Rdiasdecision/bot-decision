import asyncio

import httpx

from app.agent.pipeline import PipelineResult
from app.api import create_app


class FakePipeline:
    def ask(self, question: str) -> PipelineResult:
        return PipelineResult(
            answer="Existem 42 registros.",
            generated_sql="SELECT COUNT(*) FROM public.vw_dados",
            executed_sql="SELECT COUNT(*) FROM public.vw_dados LIMIT 100",
            columns=["count"],
            rows=[{"count": 42}],
        )


async def request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)


def test_chat_returns_answer_and_executed_sql() -> None:
    app = create_app(FakePipeline())  # type: ignore[arg-type]
    response = asyncio.run(
        request(app, "POST", "/chat", json={"question": "Quantos registros?"})
    )

    assert response.status_code == 200
    assert response.json() == {
        "question": "Quantos registros?",
        "answer": "Existem 42 registros.",
        "generated_sql": "SELECT COUNT(*) FROM public.vw_dados",
        "sql": "SELECT COUNT(*) FROM public.vw_dados LIMIT 100",
        "columns": ["count"],
        "rows": [{"count": 42}],
    }


def test_chat_rejects_empty_question() -> None:
    app = create_app(FakePipeline())  # type: ignore[arg-type]
    response = asyncio.run(request(app, "POST", "/chat", json={"question": "   "}))

    assert response.status_code == 422


def test_health() -> None:
    app = create_app(FakePipeline())  # type: ignore[arg-type]
    response = asyncio.run(request(app, "GET", "/health"))

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "model": "test",
    }
