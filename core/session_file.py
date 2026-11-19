"""Save a self-check to a file and load it back (service-roadmap.md, task 1.1; project-spec.md, 4.12).

The file stays with the user: nothing is stored by the service. Format: UTF-8 JSON
    {"format": "firecheck-session", "version": 1, "saved": "2026-11-19",
     "base_edition": "...", "answers": {...questionnaire...}, "responses": {item id: response}}
Loading never trusts the file: answers are checked as if typed in the questionnaire, responses
for items that are no longer in the checklist or have unknown values are dropped with a warning.
"""

import json
from dataclasses import dataclass
from datetime import date

from core.checklist import AnswersError, build_checklist, default_answers
from core.scoring import ANSWERS, VIOLATION

FORMAT = "firecheck-session"
VERSION = 1


class SessionFileError(Exception):
    """Raised when a file cannot be used at all. Holds the list of problems."""

    def __init__(self, problems):
        self.problems = problems
        super().__init__("Файл проверки не загружен:\n- " + "\n- ".join(problems))


@dataclass
class Session:
    answers: dict      # questionnaire answers
    checklist: object  # checklist rebuilt from the answers with the current base
    responses: dict    # item id -> response, only for items of the checklist
    warnings: list     # what was dropped or may be out of date
    complete: bool     # every item of the checklist has an answer


def dump_session(bases, answers, responses, today=None):
    """Bytes of the session file."""
    data = {
        "format": FORMAT,
        "version": VERSION,
        "saved": (today or date.today()).isoformat(),
        "base_edition": bases.edition,
        "answers": answers,
        "responses": responses,
    }
    return json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")


def load_session(bases, raw):
    """Check the file and rebuild the checklist with the current base. Raise SessionFileError if unusable."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SessionFileError(["это не файл проверки (не читается как JSON)"])
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise SessionFileError(["это не файл проверки этого сервиса"])
    if data.get("version") != VERSION:
        raise SessionFileError([f"неизвестная версия файла: {data.get('version')!r}, нужна {VERSION}"])
    if not isinstance(data.get("answers"), dict) or not isinstance(data.get("responses"), dict):
        raise SessionFileError(["в файле нет анкеты или ответов"])

    warnings = []
    if data.get("base_edition") != bases.edition:
        warnings.append(f"Файл сохранён для другой редакции базы норм («{data.get('base_edition')}»), "
                        f"сейчас «{bases.edition}». Проверьте ответы.")

    # questionnaire: keep only questions that still exist, then check as if typed by hand
    answers = default_answers(bases)
    unknown = [k for k in data["answers"] if k not in answers and k != "name"]
    answers.update({k: v for k, v in data["answers"].items() if k in answers or k == "name"})
    if unknown:
        warnings.append("В анкете больше нет вопросов: " + ", ".join(sorted(unknown)) + " (пропущены).")
    try:
        checklist = build_checklist(bases, answers)
    except AnswersError as err:
        raise SessionFileError(err.problems)

    in_checklist = {i["id"] for i in checklist.items}
    responses, dropped = {}, []
    for item_id, r in data["responses"].items():
        if item_id not in in_checklist:
            dropped.append(item_id)
        elif not isinstance(r, dict) or r.get("answer") not in ANSWERS:
            dropped.append(item_id)
        else:
            clean = {"answer": r["answer"], "comment": str(r.get("comment") or "")}
            if r["answer"] == VIOLATION and r.get("o_raise") == 1:
                clean["o_raise"] = 1
                clean["o_reason"] = str(r.get("o_reason") or "")
            responses[item_id] = clean
    if dropped:
        warnings.append("Ответы на пункты, которых нет в чек-листе или с неверным значением, пропущены: "
                        + ", ".join(sorted(dropped)) + ".")
    missing = len(in_checklist) - len(responses)
    if missing:
        warnings.append(f"Без ответа осталось пунктов: {missing}.")
    return Session(answers=answers, checklist=checklist, responses=responses, warnings=warnings,
                   complete=missing == 0)
