from openai import OpenAI

from app.config import Settings


class MaritacaClient:
    """Cliente minimo para o endpoint OpenAI-compatible da Maritaca."""

    def __init__(self, settings: Settings) -> None:
        self._model = settings.maritaca_model
        self._temperature = settings.llm_temperature
        self._client = OpenAI(
            api_key=settings.maritaca_api_key,
            base_url=settings.maritaca_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        if not content or not content.strip():
            raise RuntimeError("A Maritaca retornou uma resposta vazia")
        return content.strip()

