import json
from typing import Any

from app.agent.sql_generator import Completer
from app.llm.prompts import ANSWER_SYSTEM_PROMPT, ANSWER_USER_PROMPT


class AnswerGenerator:
    def __init__(self, llm: Completer) -> None:
        self._llm = llm

    def generate(
        self,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[dict[str, Any]],
    ) -> str:
        rows_json = json.dumps(rows, ensure_ascii=False, default=str)
        return self._llm.complete(
            ANSWER_SYSTEM_PROMPT,
            ANSWER_USER_PROMPT.format(
                question=question,
                sql=sql,
                columns=", ".join(columns),
                rows_json=rows_json,
            ),
        )

