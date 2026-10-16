import asyncio
from pathlib import Path

import pandas as pd
import pytest

from finpilot import open_statement
from finpilot.statement import load_statement, normalize_merchant

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_statement.csv"


@pytest.fixture(scope="module")
def st():
    return open_statement(SAMPLE)


def test_reads_tbank_csv(st):
    assert len(st.df) == 392
    assert st.df.date.min() == pd.Timestamp("2026-04-01").normalize() or st.df.date.min().month == 4
    assert (st.df.amount < 0).sum() > 300


def test_generic_csv_in_cp1251(tmp_path):
    f = tmp_path / "simple.csv"
    f.write_bytes("date,amount,description\n2026-09-01,-350,Пятёрочка 123\n2026-09-02,5000,Зарплата\n".encode("cp1251"))
    df = load_statement(f)
    assert list(df.amount) == [-350.0, 5000.0]
    assert df.merchant.iloc[0] == "пятёрочка"


def test_missing_columns_message(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="обязательных колонок"):
        load_statement(f)


def test_normalize_merchant():
    assert normalize_merchant("PYATEROCHKA 6123 MOSCOW RUS") == "pyaterochka moscow rus"
    assert normalize_merchant("YANDEX*GO 7781") == "yandex go"


def test_subscriptions(st):
    subs = {s["merchant"]: s for s in st.subscriptions()}
    assert set(subs) == {"МТС", "Яндекс Плюс", "Telegram Premium", "Okko"}
    assert subs["Яндекс Плюс"]["next_expected"] == "05.10.2026"
    assert subs["МТС"]["cost_per_year"] == 650 * 12


def test_unusual(st):
    sept = st.unusual("2026-09")
    assert any("повторное списание" in x["reason"] for x in sept)
    aug = st.unusual("2026-08")
    assert any(x["amount"] == 24990 for x in aug)


def test_spending_excludes_transfers(st):
    cats = {c["category"] for c in st.spending_by_category("2026-08")["categories"]}
    assert "Переводы" not in cats and "Поступления" not in cats


def test_partial_month_and_forecast(st):
    s = st.spending_by_category()
    assert s["month"] == "2026-09" and s["complete"] is False
    f = st.forecast_month()
    assert f["days_left"] == 10 and f["forecast_total"] > f["spent_so_far"]


def test_mcp_server_end_to_end():
    from mcp.client import Client

    from finpilot.server import mcp

    async def run():
        async with Client(mcp) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            assert {"load_statement", "spending_by_category", "find_subscriptions"} <= names
            res = await client.call_tool("load_statement", {"path": str(SAMPLE)})
            assert not res.is_error
            res = await client.call_tool("find_subscriptions", {})
            text = " ".join(c.text for c in res.content)
            assert "Яндекс Плюс" in text and "Telegram Premium" in text

    asyncio.run(run())
