"""Генерирует examples/sample_statement.csv — выписку студента в формате CSV Т-Банка.

Данные выдуманы, но внутри есть то, что сервер должен найти: подписки,
двойное списание и одна крупная покупка.
"""
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(7)
OUT = Path(__file__).with_name("sample_statement.csv")
START, END = datetime(2026, 4, 1), datetime(2026, 9, 20, 22, 0)
rows = []


def add(ts, amount, category, mcc, desc):
    rows.append({
        "Дата операции": ts.strftime("%d.%m.%Y %H:%M:%S"), "Дата платежа": ts.strftime("%d.%m.%Y"),
        "Номер карты": "*4821", "Статус": "OK", "Сумма операции": f"{amount:.2f}".replace(".", ","),
        "Валюта операции": "RUB", "Сумма платежа": f"{amount:.2f}".replace(".", ","), "Валюта платежа": "RUB",
        "Кэшбэк": "", "Категория": category, "MCC": mcc, "Описание": desc,
        "Бонусы (включая кэшбэк)": "0,00", "Округление на инвесткопилку": "0,00",
        "Сумма операции с округлением": f"{abs(amount):.2f}".replace(".", ","),
    })


def at(day, h0=8, h1=23):
    return day + timedelta(hours=random.randint(h0, h1 - 1), minutes=random.randint(0, 59), seconds=random.randint(0, 59))


day = START
while day <= END:
    if random.random() < 0.55:
        add(at(day), -random.choice([389, 512, 640, 877, 1240, 1530]) - random.randint(0, 99), "Супермаркеты", "5411",
            random.choice(["Пятёрочка", "Перекрёсток", "ВкусВилл", "Самокат"]))
    if day.weekday() < 5 and random.random() < 0.8:
        add(at(day, 7, 10), -62, "Местный транспорт", "4111", "Метрополитен")
    if random.random() < 0.35:
        add(at(day, 9, 18), -random.choice([220, 260, 310, 340]), "Рестораны", "5812",
            random.choice(["Cofix", "Surf Coffee", "Шоколадница", "Даблби"]))
    if random.random() < 0.18:
        add(at(day, 12, 23), -random.randint(290, 690), "Фастфуд", "5814", random.choice(["Вкусно и точка", "Ростикс"]))
    if random.random() < 0.12:
        add(at(day, 7, 23), -random.randint(240, 780), "Такси", "4121", "Yandex.Go")
    if random.random() < 0.08:
        add(at(day), -random.randint(450, 4800), "Маркетплейсы", "5399", random.choice(["OZON", "Wildberries"]))
    if day.day == 5:
        add(at(day, 3, 5), -399, "Цифровые товары", "5815", "Яндекс Плюс")
    if day.day == 12:
        add(at(day, 9, 11), -650, "Мобильная связь", "4814", "МТС")
    if day.day == 18:
        add(at(day, 1, 3), -299, "Цифровые товары", "5816", "Telegram Premium")
    if day.day == 21 and day.month >= 6:
        add(at(day, 4, 6), -449, "Цифровые товары", "5815", "Okko")
    if day.day in (1, 15):
        add(at(day, 10, 12), 15000, "Пополнения", "", "Перевод от Шкель А.")
    if day.day == 25:
        add(at(day, 10, 12), 3200, "Пополнения", "", "Стипендия Финуниверситет")
    if random.random() < 0.05:
        add(at(day), -random.choice([500, 1000, 1500]), "Переводы", "", "Перевод по номеру телефона +7 9** ***-41-07")
    day += timedelta(days=1)

# крупная покупка и двойное списание
add(datetime(2026, 8, 14, 19, 12, 5), -24990, "Маркетплейсы", "5399", "OZON")
t = datetime(2026, 9, 3, 13, 40, 11)
add(t, -1890, "Рестораны", "5812", "Теремок")
add(t + timedelta(minutes=2), -1890, "Рестораны", "5812", "Теремок")

rows.sort(key=lambda r: datetime.strptime(r["Дата операции"], "%d.%m.%Y %H:%M:%S"), reverse=True)  # банк выгружает от новых к старым
with OUT.open("w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";", quoting=csv.QUOTE_ALL)
    w.writeheader()
    w.writerows(rows)
print(f"{OUT.name}: {len(rows)} операций")
