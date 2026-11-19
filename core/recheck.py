"""Re-inspection of open violations (service-roadmap.md 1.4; project-spec.md, 4.14).

After a walk-round the specialist marks each open violation as fixed or not fixed.
Fixed ones become "compliant", leave the plan and go to the list of closed violations with the date;
the state before the re-inspection is kept in the history, so the result screen can compare.

    closed:  item id -> {"action", "owner", "verified_on", "note"}
    history: list of {"date", "index", "violations", "critical"}, oldest first
"""

from dataclasses import dataclass
from datetime import date

from core.action_plan import clean_plan
from core.scoring import OK, VIOLATION


@dataclass
class Recheck:
    responses: dict
    plan: dict
    closed: dict
    history: list


def snapshot(result, on_date):
    """History entry for a result: date, readiness index, number of violations and critical ones."""
    return {"date": on_date.isoformat(), "index": None if result.index is None else str(result.index),
            "violations": len(result.violations), "critical": len(result.critical)}


def apply_recheck(responses, plan, closed, history, decisions, before, on_date=None):
    """decisions: item id -> {"fixed": bool, "note": str} for open violations; before: result before."""
    on_date = on_date or date.today()
    responses = {k: dict(v) for k, v in responses.items()}
    plan = {k: dict(v) for k, v in plan.items()}
    closed = dict(closed)
    for item_id, d in decisions.items():
        if responses.get(item_id, {}).get("answer") != VIOLATION:
            continue
        note = (d.get("note") or "").strip()
        entry = plan.get(item_id, {})
        if d.get("fixed"):
            responses[item_id] = {"answer": OK, "comment": f"Устранено, подтверждено {on_date:%d.%m.%Y}"
                                  + (f": {note}" if note else "")}
            closed[item_id] = {"action": entry.get("action", ""), "owner": entry.get("owner", ""),
                               "verified_on": on_date.isoformat(), "note": note}
            plan.pop(item_id, None)
        else:
            entry["status"] = "in_work"  # still open after the re-inspection
            comment = responses[item_id].get("comment", "")
            mark = f"Не устранено на {on_date:%d.%m.%Y}" + (f": {note}" if note else "")
            responses[item_id]["comment"] = f"{comment}; {mark}" if comment else mark
            plan[item_id] = entry
    violations = [k for k, r in responses.items() if r["answer"] == VIOLATION]
    return Recheck(responses=responses, plan=clean_plan(plan, violations),
                   closed=clean_closed(closed, responses), history=list(history) + [snapshot(before, on_date)])


def clean_closed(closed, responses):
    """Closed entries for items that are not violations now; values normalised."""
    out = {}
    for item_id, e in (closed or {}).items():
        if not isinstance(e, dict) or responses.get(item_id, {}).get("answer") == VIOLATION:
            continue
        out[item_id] = {k: str(e.get(k) or "") for k in ("action", "owner", "verified_on", "note")}
    return out


def clean_history(history):
    """Keep well-formed history entries only."""
    out = []
    for h in history or []:
        if isinstance(h, dict) and isinstance(h.get("violations"), int) and h.get("date"):
            out.append({"date": str(h["date"])[:10], "index": None if h.get("index") is None else str(h["index"]),
                        "violations": h["violations"], "critical": int(h.get("critical") or 0)})
    return out
