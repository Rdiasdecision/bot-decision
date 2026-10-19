import asyncio

import httpx

from app.agent.pipeline import PipelineResult
from app.api import create_app


class FakePipeline:
    def __init__(self) -> None:
        self.histories = []

    def ask(self, question: str, history=()) -> PipelineResult:
        self.histories.append(history)
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
        request(
            app,
            "POST",
            "/chat",
            json={
                "user_id": "usuario-1",
                "screen": "default",
                "question": "Quantos registros?",
            },
        )
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "user_id": "usuario-1",
        "screen": "default",
        "session_id": body["session_id"],
        "question": "Quantos registros?",
        "answer": "Existem 42 registros.",
        "generated_sql": "SELECT COUNT(*) FROM public.vw_dados",
        "sql": "SELECT COUNT(*) FROM public.vw_dados LIMIT 100",
        "columns": ["count"],
        "rows": [{"count": 42}],
        "history_messages": 2,
    }


def test_chat_rejects_empty_question() -> None:
    app = create_app(FakePipeline())  # type: ignore[arg-type]
    response = asyncio.run(
        request(
            app,
            "POST",
            "/chat",
            json={
                "user_id": "usuario-1",
                "screen": "default",
                "question": "   ",
            },
        )
    )

    assert response.status_code == 422


def test_health() -> None:
    app = create_app(FakePipeline())  # type: ignore[arg-type]
    response = asyncio.run(request(app, "GET", "/health"))

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "model": "test",
        "screens": ["default"],
    }


async def two_turns(app) -> tuple[httpx.Response, httpx.Response]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            first = await client.post(
                "/chat",
                json={
                    "user_id": "usuario-1",
                    "screen": "default",
                    "session_id": "sessao-1",
                    "question": "Quantos registros?",
                },
            )
            second = await client.post(
                "/chat",
                json={
                    "user_id": "usuario-1",
                    "screen": "default",
                    "session_id": "sessao-1",
                    "question": "E no mes passado?",
                },
            )
            return first, second


def test_chat_passes_previous_messages_to_pipeline() -> None:
    pipeline = FakePipeline()
    app = create_app(pipeline)  # type: ignore[arg-type]

    first, second = asyncio.run(two_turns(app))

    assert first.status_code == 200
    assert second.status_code == 200
    assert pipeline.histories[0] == ()
    assert [message.role for message in pipeline.histories[1]] == ["user", "assistant"]
    assert pipeline.histories[1][0].content == "Quantos registros?"
    assert second.json()["history_messages"] == 4


def test_clear_session() -> None:
    app = create_app(FakePipeline())  # type: ignore[arg-type]

    async def scenario() -> httpx.Response:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                await client.post(
                    "/chat",
                    json={
                        "user_id": "usuario-1",
                        "screen": "default",
                        "session_id": "sessao-1",
                        "question": "Teste",
                    },
                )
                return await client.delete(
                    "/users/usuario-1/screens/default/sessions/sessao-1"
                )

    response = asyncio.run(scenario())
    assert response.status_code == 200
    assert response.json() == {
        "user_id": "usuario-1",
        "screen": "default",
        "session_id": "sessao-1",
        "cleared": True,
    }


def test_unknown_screen_is_rejected() -> None:
    app = create_app(FakePipeline())  # type: ignore[arg-type]
    response = asyncio.run(
        request(
            app,
            "POST",
            "/chat",
            json={
                "user_id": "usuario-1",
                "screen": "admin",
                "question": "Quantos registros?",
            },
        )
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Tela nao autorizada ou inexistente"


async def isolated_users(app) -> None:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            for user_id in ("usuario-1", "usuario-2"):
                response = await client.post(
                    "/chat",
                    json={
                        "user_id": user_id,
                        "screen": "default",
                        "session_id": "mesma-sessao",
                        "question": "Teste",
                    },
                )
                assert response.status_code == 200


def test_history_is_isolated_by_user() -> None:
    pipeline = FakePipeline()
    app = create_app(pipeline)  # type: ignore[arg-type]

    asyncio.run(isolated_users(app))

    assert pipeline.histories == [(), ()]
