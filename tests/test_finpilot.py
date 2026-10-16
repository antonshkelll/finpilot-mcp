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


# ---------- случаи из реальных выписок ----------
def write(tmp_path, name, text, enc="utf-8"):
    f = tmp_path / name
    f.write_bytes(text.encode(enc))
    return f


def test_iso_dates_are_not_swapped(tmp_path):
    f = write(tmp_path, "iso.csv", "date,amount,description\n2026-09-01,-100,A\n2026-09-12,-100,B\n2026-08-02,-100,C\n")
    st = open_statement(f)
    assert list(st.df.date.dt.strftime("%d.%m")) == ["02.08", "01.09", "12.09"]
    assert st.months() == ["2026-08", "2026-09"]


def test_tbank_foreign_currency_uses_account_amount(tmp_path):
    head = '"Дата операции";"Статус";"Сумма операции";"Валюта операции";"Сумма платежа";"Валюта платежа";"Категория";"MCC";"Описание"\n'
    row = '"03.09.2026 12:00:00";"OK";"-12,00";"USD";"-1 140,00";"RUB";"Цифровые товары";"5816";"Steam"\n'
    st = open_statement(write(tmp_path, "tb.csv", head + row, "cp1251"))
    assert st.df.amount.iloc[0] == -1140.0


def test_sbp_merchant_payment_counts_as_spending(tmp_path):
    f = write(tmp_path, "sbp.csv", "date,amount,description\n2026-09-01,-2500,Оплата СБП ООО «Кухня на районе»\n"
                                   "2026-09-02,-1000,Перевод по номеру телефона +7 9** ***-11-22\n")
    s = open_statement(f).spending_by_category("2026-09")
    assert s["total_spent"] == 2500          # перевод не трата, оплата по СБП — трата


def test_yo_in_merchant_names(tmp_path):
    f = write(tmp_path, "yo.csv", "date,amount,description\n2026-09-01,-500,Пятёрочка\n2026-09-02,-700,Перекрёсток\n")
    cats = {c["category"] for c in open_statement(f).spending_by_category()["categories"]}
    assert cats == {"Продукты"}


def test_forecast_on_short_statement(tmp_path):
    rows = "\n".join(f"2026-09-{d:02d},-{4000 / 15:.2f},Кафе" for d in range(1, 16))
    f = write(tmp_path, "short.csv", "date,amount,description\n" + rows + "\n")
    fc = open_statement(f).forecast_month()
    assert fc["days_left"] == 15
    assert fc["forecast_total"] == pytest.approx(8000, rel=0.01)


def test_cancelled_subscription_is_not_reported(tmp_path):
    rows = ["2026-02-05,-399,Яндекс Плюс", "2026-03-05,-399,Яндекс Плюс", "2026-04-05,-399,Яндекс Плюс",
            "2026-09-20,-100,Кафе"]
    st = open_statement(write(tmp_path, "subs.csv", "date,amount,description\n" + "\n".join(rows) + "\n"))
    assert st.subscriptions() == []


def test_empty_and_header_only_files(tmp_path):
    with pytest.raises(ValueError, match="пустой"):
        load_statement(write(tmp_path, "empty.csv", ""))
    with pytest.raises(ValueError, match="нет ни одной операции"):
        open_statement(write(tmp_path, "head.csv", "date,amount,description\n"))


def test_cli_prints_clear_error(tmp_path, capsys):
    import sys

    from finpilot import cli
    sys.argv = ["finpilot", "report", str(tmp_path / "missing.csv")]
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert "Файл не найден" in str(e.value)


def test_partial_month_compared_to_same_day(st):
    s = st.spending_by_category("2026-09")
    assert s["compared_to_same_day"] and s["previous_month"] == "2026-08"
    aug_to_20 = st.expenses[(st.expenses.month == "2026-08") & (st.expenses.date.dt.day <= 20)].spent.sum()
    assert s["previous_total"] == pytest.approx(aug_to_20, abs=0.01)


def test_plural():
    from finpilot.analytics import plural
    assert [plural(n, "операция", "операции", "операций") for n in (1, 2, 5, 11, 21, 392, 112)] == \
        ["операция", "операции", "операций", "операций", "операция", "операции", "операций"]
