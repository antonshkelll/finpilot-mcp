"""finpilot — локальная аналитика банковской выписки для людей и AI-агентов (MCP)."""
from .analytics import Statement
from .statement import load_statement

__all__ = ["Statement", "load_statement", "open_statement"]
__version__ = "0.1.0"


def open_statement(path) -> Statement:
    return Statement.from_frame(load_statement(path))
