import argparse
import json
from pathlib import Path
from typing import Any

from sqlglot import parse_one

from app.config import get_settings
from app.db.connection import Database
from app.main import build_pipeline


def normalized_sql(sql: str) -> str:
    return parse_one(sql, read="postgres").sql(dialect="postgres", pretty=False)


def load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa avaliacoes do chatbot SQL")
    parser.add_argument(
        "--file",
        type=Path,
        default=Path(__file__).with_name("questions.jsonl"),
    )
    args = parser.parse_args()
    cases = load_cases(args.file)
    settings = get_settings()
    passed = 0

    with Database(settings) as database:
        pipeline = build_pipeline(settings, database)
        pipeline.refresh_schema()
        for index, case in enumerate(cases, start=1):
            try:
                result = pipeline.ask(case["question"])
                checks: list[bool] = []
                if "expected_sql" in case:
                    checks.append(
                        normalized_sql(result.executed_sql)
                        == normalized_sql(case["expected_sql"])
                    )
                if "expected_result" in case:
                    checks.append(result.rows == case["expected_result"])
                if "expected_answer_contains" in case:
                    checks.append(
                        case["expected_answer_contains"].lower() in result.answer.lower()
                    )
                ok = all(checks) if checks else True
                passed += int(ok)
                print(f"[{index}] {'OK' if ok else 'FALHOU'}: {case['question']}")
                if not ok:
                    print(f"    SQL: {result.executed_sql}")
                    print(f"    Resultado: {result.rows}")
            except Exception as exc:
                print(f"[{index}] ERRO: {case['question']} -- {exc}")

    total = len(cases)
    accuracy = (passed / total * 100) if total else 0
    print(f"\nAcuracia: {passed}/{total} ({accuracy:.1f}%)")


if __name__ == "__main__":
    main()

