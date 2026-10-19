from typing import Protocol

from app.agent.memory import ConversationMessage, format_history
from app.llm.prompts import SQL_SYSTEM_PROMPT, SQL_USER_PROMPT


class Completer(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


class SQLGenerator:
    def __init__(self, llm: Completer) -> None:
        self._llm = llm

    def generate(
        self,
        question: str,
        schema: str,
        history: tuple[ConversationMessage, ...] = (),
    ) -> str:
        if not question.strip():
            raise ValueError("A pergunta nao pode estar vazia")
        return self._llm.complete(
            SQL_SYSTEM_PROMPT,
            SQL_USER_PROMPT.format(
                schema=schema,
                history=format_history(history),
                question=question.strip(),
            ),
        )
