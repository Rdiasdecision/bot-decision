import azure.functions as func

import function_app


def test_azure_entrypoint_wraps_fastapi_as_asgi() -> None:
    assert isinstance(function_app.app, func.AsgiFunctionApp)
