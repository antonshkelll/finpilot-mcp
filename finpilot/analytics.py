"""Аналитика расходов: сводка по категориям, подписки, необычные операции, прогноз на месяц."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .categories import categorize

SKIP_IN_SPENDING = {"Переводы", "Наличные", "Пополнения", "Поступления"}


@dataclass
class Statement:
    df: pd.DataFrame

    @classmethod
    def from_frame(cls, df: pd.DataFrame) -> "Statement":
        df = df.copy()
        df["category"] = categorize(df)
        df["month"] = df.date.dt.to_period("M").astype(str)
        return cls(df)

    # ---------- базовые срезы ----------
    @property
    def expenses(self) -> pd.DataFrame:
        e = self.df[(self.df.amount < 0) & ~self.df.category.isin(SKIP_IN_SPENDING)].copy()
        e["spent"] = -e.amount
        return e

    def months(self) -> list[str]:
        return sorted(self.df.month.unique())

    def resolve_month(self, month: str | None) -> str:
        months = self.months()
        if not months:
            raise ValueError("Выписка пустая")
        if month is None:
            return months[-1]
        if month not in months:
            raise ValueError(f"Месяца {month} нет в выписке. Доступны: {', '.join(months)}")
        return month

    def overview(self) -> dict:
        d = self.df
        return dict(operations=len(d), period=f"{d.date.min():%d.%m.%Y} — {d.date.max():%d.%m.%Y}",
                    months=self.months(), income=round(float(d.loc[d.amount > 0, "amount"].sum()), 2),
                    spending=round(float(self.expenses.spent.sum()), 2))

    # ---------- сводка ----------
    def spending_by_category(self, month: str | None = None) -> dict:
        month = self.resolve_month(month)
        e = self.expenses
        cur = e[e.month == month].groupby("category").spent.agg(["sum", "count"])
        months = self.months()
        prev_m = months[months.index(month) - 1] if months.index(month) > 0 else None
        prev = e[e.month == prev_m].groupby("category").spent.sum() if prev_m else pd.Series(dtype=float)
        total = float(cur["sum"].sum())
        rows = []
        for cat, r in cur.sort_values("sum", ascending=False).iterrows():
            p = float(prev.get(cat, 0.0))
            rows.append(dict(category=cat, spent=round(float(r["sum"]), 2), operations=int(r["count"]),
                             share=round(float(r["sum"]) / total, 3) if total else 0.0,
                             vs_prev_month=round((float(r["sum"]) - p) / p, 3) if p else None))
        last = self.df.date.max()
        partial = month == str(last.to_period("M")) and last.day < last.days_in_month
        return dict(month=month, complete=not partial, data_until=f"{last:%d.%m.%Y}",
                    total_spent=round(total, 2), previous_month=prev_m,
                    previous_total=round(float(prev.sum()), 2) if prev_m else None, categories=rows)

    def top_merchants(self, month: str | None = None, n: int = 10) -> list[dict]:
        month = self.resolve_month(month)
        e = self.expenses[self.expenses.month == month]
        g = e.groupby("merchant").agg(spent=("spent", "sum"), operations=("spent", "size"),
                                      category=("category", "first"), example=("description", "first"))
        return [dict(merchant=r.example, category=r.category, spent=round(float(r.spent), 2), operations=int(r.operations))
                for r in g.sort_values("spent", ascending=False).head(n).itertuples()]

    # ---------- подписки ----------
    def subscriptions(self, min_charges: int = 3) -> list[dict]:
        """Повторяющиеся списания: один мерчант, похожая сумма (±15%), регулярный интервал."""
        e = self.df[self.df.amount < 0].assign(spent=lambda x: -x.amount)
        found = []
        for merchant, g in e.groupby("merchant"):
            if len(g) < min_charges or not merchant:
                continue
            g = g.sort_values("date")
            med = g.spent.median()
            regular = g[(g.spent - med).abs() <= 0.15 * med]
            if len(regular) < min_charges:
                continue
            gaps = regular.date.diff().dt.days.dropna()
            period = float(gaps.median())
            for name, lo, hi, per_year, step in (("ежемесячно", 26, 35, 12, pd.DateOffset(months=1)),
                                                 ("еженедельно", 6, 8, 52, pd.DateOffset(weeks=1)),
                                                 ("ежегодно", 350, 380, 1, pd.DateOffset(years=1))):
                if lo <= period <= hi and (gaps.between(lo - 3, hi + 3)).mean() >= 0.75:
                    last = regular.date.max()
                    found.append(dict(merchant=regular.description.iloc[-1], category=regular.category.iloc[-1],
                                      amount=round(float(regular.spent.iloc[-1]), 2), period=name,
                                      charges=len(regular), last_charge=f"{last:%d.%m.%Y}",
                                      next_expected=f"{last + step:%d.%m.%Y}",
                                      cost_per_year=round(float(regular.spent.iloc[-1]) * per_year, 2)))
                    break
        return sorted(found, key=lambda x: -x["cost_per_year"])

    # ---------- необычные операции ----------
    def unusual(self, month: str | None = None, min_amount: float = 1000.0) -> list[dict]:
        """Крупнее обычного для своей категории (медиана + 5·MAD) и возможные двойные списания."""
        e = self.expenses.sort_values("date")
        reasons: dict[int, list[str]] = {}
        for cat, g in e.groupby("category"):
            med = g.spent.median()
            mad = (g.spent - med).abs().median() or med * 0.5
            for i in g.index[g.spent > max(min_amount, med + 5 * mad)]:
                reasons.setdefault(i, []).append(f"обычно в категории ~{money(med)}")
        same = ((e.merchant == e.merchant.shift()) & (e.spent == e.spent.shift())
                & ((e.date - e.date.shift()).dt.total_seconds() <= 600))
        for i in e.index[same]:
            reasons.setdefault(i, []).append("повторное списание той же суммы в течение 10 минут")
        out = []
        for i, why in reasons.items():
            r = e.loc[i]
            out.append(dict(date=f"{r.date:%d.%m.%Y %H:%M}", description=r.description, category=r.category,
                            amount=round(float(r.spent), 2), reason="; ".join(why), month=r.month))
        if month:
            month = self.resolve_month(month)
            out = [o for o in out if o["month"] == month]
        return sorted(out, key=lambda x: (x["month"], x["date"]))

    # ---------- прогноз ----------
    def forecast_month(self) -> dict:
        """Сколько потратится до конца последнего месяца выписки при текущем темпе (по последним 60 дням)."""
        e = self.expenses
        last_day = self.df.date.max().normalize()
        month = last_day.to_period("M")
        so_far = float(e[e.month == str(month)].spent.sum())
        window = e[e.date > last_day - pd.Timedelta(days=60)]
        daily = float(window.spent.sum()) / 60
        days_left = int(month.days_in_month - last_day.day)
        return dict(month=str(month), spent_so_far=round(so_far, 2), days_left=days_left,
                    daily_pace=round(daily, 2), forecast_total=round(so_far + daily * days_left, 2))

    def search(self, query: str, month: str | None = None, limit: int = 20) -> list[dict]:
        d = self.df
        if month:
            d = d[d.month == self.resolve_month(month)]
        hit = d[d.description.str.lower().str.contains(query.lower(), regex=False) | (d.category.str.lower() == query.lower())]
        return [dict(date=f"{r.date:%d.%m.%Y}", description=r.description, category=r.category,
                     amount=round(float(r.amount), 2)) for r in hit.tail(limit).itertuples()]


def money(x: float) -> str:
    return f"{x:,.0f} ₽".replace(",", " ")
