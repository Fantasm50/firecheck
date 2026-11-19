"""Corrective action plan for the violations of a self-check (service-roadmap.md 1.2; project-spec.md, 4.13).

The plan is a dict: item id -> entry, for example
    {"GEN-019": {"action": "Снять навесной замок", "owner": "Иванов И. И.", "due": "2026-12-01", "status": "in_work"}}
Only violations of the current result have a plan entry; "due" is an ISO date or "".
"""

from datetime import date, datetime

STATUSES = {
    "new": "новое",
    "in_work": "в работе",
    "done": "устранено",
    "verified": "подтверждено",
}
CLOSED = {"done", "verified"}  # a closed entry is never overdue


def empty_entry():
    return {"action": "", "owner": "", "due": "", "status": "new"}


def parse_due(value):
    """ISO date string (or date) -> date; anything else -> None."""
    if value is None or value != value:  # empty cell; pandas NaT is not equal to itself
        return None
    if isinstance(value, datetime):  # pandas Timestamp from the table editor is a datetime
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def clean_plan(plan, violation_ids):
    """Keep entries only for current violations, fill missing ones, normalise values."""
    out = {}
    for item_id in violation_ids:
        raw = plan.get(item_id) if isinstance(plan, dict) else None
        entry = empty_entry()
        if isinstance(raw, dict):
            entry["action"] = str(raw.get("action") or "").strip()
            entry["owner"] = str(raw.get("owner") or "").strip()
            due = parse_due(raw.get("due"))
            entry["due"] = due.isoformat() if due else ""
            entry["status"] = raw.get("status") if raw.get("status") in STATUSES else "new"
        out[item_id] = entry
    return out


def is_overdue(entry, today=None):
    due = parse_due(entry.get("due"))
    return due is not None and due < (today or date.today()) and entry.get("status") not in CLOSED


def overdue_ids(plan, today=None):
    return [item_id for item_id, entry in plan.items() if is_overdue(entry, today)]


def due_text(entry):
    """Deadline and status for the report: '01.12.2026 (в работе)'."""
    due = parse_due(entry.get("due"))
    parts = [due.strftime("%d.%m.%Y")] if due else []
    if entry.get("status", "new") != "new":
        parts.append(f"({STATUSES[entry['status']]})")
    return " ".join(parts)
