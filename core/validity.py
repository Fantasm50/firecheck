"""Validity of the acts behind the norms base (project-spec.md, 4.11).

The base rests on acts with a known last day in force (meta.validity in requirements YAML),
for example PPR No 1479 until 31.12.2026. The app and the report warn the specialist
SOON_DAYS before that day and after it, so an outdated base is never used silently.
"""

from dataclasses import dataclass
from datetime import date

from core.loader import covered_items

SOON_DAYS = 30

EXPIRED = "expired"  # the last day has passed
SOON = "soon"        # the last day is within SOON_DAYS


@dataclass
class Alert:
    level: str        # EXPIRED or SOON
    act: str
    last_day: date
    item_count: int   # demo items that rest on the act
    text: str         # message for the screen and the report


def validity_alerts(bases, on_date=None, soon_days=SOON_DAYS):
    """Alerts for acts that expire within soon_days of on_date or have already expired."""
    on_date = on_date or date.today()
    alerts = []
    for entry in bases.validity:
        last_day = entry["last_day"]
        count = len(covered_items(entry, bases.items))
        days_left = (last_day - on_date).days
        if days_left < 0:
            text = (f"{entry['act']}: срок действия истёк {last_day:%d.%m.%Y}. Пунктов базы на этом акте: "
                    f"{count}. Они могут не соответствовать действующим нормам — нужна новая редакция базы.")
            alerts.append(Alert(EXPIRED, entry["act"], last_day, count, text))
        elif days_left <= soon_days:
            text = (f"{entry['act']}: последний день действия {last_day:%d.%m.%Y} (осталось дней: {days_left}). "
                    f"Пунктов базы на этом акте: {count}. Проверьте, принята ли новая редакция.")
            alerts.append(Alert(SOON, entry["act"], last_day, count, text))
    return alerts
