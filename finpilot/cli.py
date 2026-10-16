"""Отчёт по выписке в терминале — без всякого AI.

    finpilot report выписка.csv [--month 2026-09]
"""
from __future__ import annotations

import argparse
import sys

from . import open_statement
from .analytics import money


def report(path: str, month: str | None) -> str:
    s = open_statement(path)
    ov = s.overview()
    cat = s.spending_by_category(month)
    lines = [f"Выписка: {ov['operations']} операций, {ov['period']}", "",
             f"Расходы за {cat['month']}{'' if cat['complete'] else ' (по ' + cat['data_until'] + ')'}: {money(cat['total_spent'])}"
             + (f"  (в {cat['previous_month']}: {money(cat['previous_total'])})" if cat["previous_month"] else ""), ""]
    for c in cat["categories"]:
        delta = "" if c["vs_prev_month"] is None else f"{c['vs_prev_month']:+.0%}"
        lines.append(f"  {c['category']:<26}{money(c['spent']):>12}  {c['share']:>5.0%}  {delta:>6}")
    subs = s.subscriptions()
    if subs:
        lines += ["", f"Подписки: {len(subs)}, в год {money(sum(x['cost_per_year'] for x in subs))}"]
        lines += [f"  {x['merchant']:<34}{money(x['amount']):>10}  {x['period']}, следующее {x['next_expected']}" for x in subs]
    odd = s.unusual(cat["month"])
    if odd:
        lines += ["", "Необычные операции:"]
        lines += [f"  {x['date']}  {x['description']:<20}{money(x['amount']):>10}  {x['reason']}" for x in odd]
    f = s.forecast_month()
    lines += ["", f"Прогноз на {f['month']}: {money(f['forecast_total'])} "
                  f"(потрачено {money(f['spent_so_far'])}, осталось дней: {f['days_left']})"]
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(prog="finpilot")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report", help="текстовый отчёт по выписке")
    r.add_argument("path")
    r.add_argument("--month", help="YYYY-MM, по умолчанию последний месяц")
    a = p.parse_args()
    if hasattr(sys.stdout, "reconfigure"):          # консоль Windows по умолчанию не в UTF-8
        sys.stdout.reconfigure(encoding="utf-8")
    print(report(a.path, a.month))


if __name__ == "__main__":
    main()
