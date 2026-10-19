"""Entrada do Azure Functions (modelo Python v2) para a aplicacao FastAPI."""

import azure.functions as func

from app.api import app as fastapi_app


# O routePrefix vazio em host.json preserva as rotas FastAPI sem gerar uma
# barra dupla na rota curinga do adaptador ASGI. No Azure, elas exigem uma key.
app = func.AsgiFunctionApp(
    app=fastapi_app,
    http_auth_level=func.AuthLevel.FUNCTION,
    function_name="chatbot_sql_api",
)
