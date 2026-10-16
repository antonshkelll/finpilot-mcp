"""MCP-сервер: инструменты анализа выписки для Claude Desktop, Cursor и других MCP-клиентов.

Данные не покидают компьютер: сервер читает файл локально и отдаёт модели только
агрегаты и найденные операции.

Запуск вручную:  finpilot-mcp            (stdio — так его запускает MCP-клиент)
Выписка по умолчанию: переменная окружения FINPILOT_STATEMENT=/путь/к/выписке.csv
"""
from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer

from . import open_statement
from .analytics import Statement

mcp = MCPServer(
    name="finpilot",
    instructions=(
        "Инструменты для анализа личной банковской выписки. Сначала вызови load_statement, "
        "если выписка ещё не загружена. Суммы в рублях, расходы считаются без переводов и снятия наличных. "
        "Месяц передавай в формате YYYY-MM."
    ),
)

_state: dict[str, Statement] = {}


def _statement() -> Statement:
    if "s" not in _state:
        default = os.getenv("FINPILOT_STATEMENT")
        if not default:
            raise ValueError("Выписка не загружена: вызови load_statement(path) или задай FINPILOT_STATEMENT.")
        _state["s"] = open_statement(default)
    return _state["s"]


@mcp.tool()
def load_statement(path: str) -> dict:
    """Загрузить выписку (CSV Т-Банка или CSV с колонками date, amount, description). Возвращает период и итоги."""
    _state["s"] = open_statement(path)
    return _state["s"].overview()


@mcp.tool()
def spending_by_category(month: str | None = None) -> dict:
    """Расходы по категориям за месяц (YYYY-MM, по умолчанию последний) и изменение к прошлому месяцу."""
    return _statement().spending_by_category(month)


@mcp.tool()
def top_merchants(month: str | None = None, n: int = 10) -> list[dict]:
    """Магазины и сервисы, на которые ушло больше всего денег за месяц."""
    return _statement().top_merchants(month, n)


@mcp.tool()
def find_subscriptions() -> list[dict]:
    """Регулярные списания (подписки): сумма, периодичность, дата следующего списания, стоимость в год."""
    return _statement().subscriptions()


@mcp.tool()
def find_unusual_transactions(month: str | None = None) -> list[dict]:
    """Операции крупнее обычного для своей категории и возможные двойные списания."""
    return _statement().unusual(month)


@mcp.tool()
def forecast_month() -> dict:
    """Прогноз расходов до конца последнего месяца выписки при текущем темпе трат."""
    return _statement().forecast_month()


@mcp.tool()
def search_transactions(query: str, month: str | None = None, limit: int = 20) -> list[dict]:
    """Найти операции по тексту описания или по названию категории."""
    return _statement().search(query, month, limit)


@mcp.prompt()
def monthly_review(month: str = "") -> str:
    """Шаблон запроса: разбор расходов за месяц с выводами."""
    m = month or "последний месяц выписки"
    return (f"Разбери мои расходы за {m}: что выросло относительно прошлого месяца, какие подписки можно "
            "отменить, были ли странные списания и сколько я потрачу до конца месяца. "
            "Используй инструменты finpilot, в конце дай 3 конкретных совета с суммами.")


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
