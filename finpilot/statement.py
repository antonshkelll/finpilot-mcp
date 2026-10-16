"""Чтение банковской выписки в единый формат.

Поддерживаются:
  * CSV-выгрузка Т-Банка (разделитель «;», запятая в суммах, кодировка cp1251 или utf-8);
  * простой CSV с колонками date, amount, description и необязательными mcc, category.

На выходе DataFrame: date, amount (расход < 0, доход > 0), description, mcc, bank_category, merchant.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd

COLUMN_ALIASES = {
    "date": ["Дата операции", "date", "Дата"],
    # «Сумма платежа» — в валюте счёта; «Сумма операции» может быть в долларах при покупке за границей
    "amount": ["Сумма платежа", "Сумма операции", "amount", "Сумма"],
    "description": ["Описание", "description", "Назначение"],
    "mcc": ["MCC", "mcc"],
    "bank_category": ["Категория", "category"],
    "status": ["Статус", "status"],
}


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Не удалось определить кодировку файла {path}")


def _pick(columns: list[str], key: str) -> str | None:
    for name in COLUMN_ALIASES[key]:
        if name in columns:
            return name
    return None


def _to_number(s: pd.Series) -> pd.Series:
    if s.dtype.kind in "if":
        return s.astype(float)
    cleaned = s.astype(str).str.replace(" ", "", regex=False).str.replace(" ", "", regex=False)
    return pd.to_numeric(cleaned.str.replace(",", ".", regex=False), errors="coerce")


def parse_dates(s: pd.Series) -> pd.Series:
    """ISO (2026-09-12) читаем как ISO, остальное — день первым (12.09.2026 — так пишут банки)."""
    iso = pd.to_datetime(s, format="ISO8601", errors="coerce")
    rest = pd.to_datetime(s[iso.isna()], dayfirst=True, format="mixed", errors="coerce")
    return iso.fillna(rest)


def normalize_merchant(description: str) -> str:
    """«PYATEROCHKA 6123 MOSCOW RUS» → «pyaterochka moscow rus»: без цифр, номеров терминалов и лишних символов."""
    s = str(description).lower()
    s = re.sub(r"[*#№]+", " ", s)
    s = re.sub(r"\d+", " ", s)
    s = re.sub(r"[^\w\s.-]", " ", s)
    return " ".join(s.split())[:60]


def load_statement(path: str | Path) -> pd.DataFrame:
    path = Path(path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")
    text = _read_text(path)
    if not text.strip():
        raise ValueError(f"Файл пустой: {path}")
    sep = ";" if text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
    df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str)
    cols = list(df.columns)
    pick = {k: _pick(cols, k) for k in COLUMN_ALIASES}
    missing = [k for k in ("date", "amount", "description") if pick[k] is None]
    if missing:
        raise ValueError(f"В выписке нет обязательных колонок {missing}. Нашлись колонки: {cols}")

    if pick["status"]:
        df = df[df[pick["status"]].fillna("OK").str.upper().isin(["OK", "SUCCESS", "ВЫПОЛНЕНО"])]
    out = pd.DataFrame({
        "date": parse_dates(df[pick["date"]]),
        "amount": _to_number(df[pick["amount"]]),
        "description": df[pick["description"]].fillna("").str.strip(),
        "mcc": df[pick["mcc"]].fillna("").str.strip() if pick["mcc"] else "",
        "bank_category": df[pick["bank_category"]].fillna("").str.strip() if pick["bank_category"] else "",
    })
    out = out.dropna(subset=["date", "amount"]).sort_values("date").reset_index(drop=True)
    out["merchant"] = out.description.map(normalize_merchant)
    return out
