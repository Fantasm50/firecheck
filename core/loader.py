"""Load the YAML bases and check that they are consistent (project-spec.md, 4.9.4).

The code holds no norms and no scores: everything is read from YAML files,
so the bases can be updated for new fire safety rules without changing the code.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).resolve().parent.parent

# Default file locations. Tests pass their own paths to load_bases().
DEFAULT_PATHS = {
    "requirements": PROJECT_DIR / "requirements_production.yaml",
    "scores": PROJECT_DIR / "scores_production_draft.yaml",
    "checklist": PROJECT_DIR / "checklist_525.yaml",
    "themes": PROJECT_DIR / "data" / "themes.yaml",
    "questionnaire": PROJECT_DIR / "data" / "questionnaire.yaml",
}

GROUPS = {"H", "M", "L"}


class DataError(Exception):
    """Raised when the YAML bases are broken. Holds the list of all problems found."""

    def __init__(self, problems):
        self.problems = problems
        super().__init__("Ошибки в файлах данных:\n- " + "\n- ".join(problems))


@dataclass
class Bases:
    """Everything the service needs, already checked."""

    items: list            # demo items in file order, each a dict from requirements YAML
    scores: dict           # id -> {"s": int, "o": int, "d": int}
    matrix: dict           # S (1..5) -> list of 5 groups for O = 1..5
    questions: dict        # q525 id -> question dict from checklist YAML
    scope: list            # q525 ids shown in the coverage table (prototype_scope.production)
    themes: list           # theme names in screen order
    topic_theme: dict      # topic -> theme name
    flags: set             # all flag ids allowed in applies_if (questions + derived)
    questionnaire: dict    # raw questionnaire YAML (labels for the user interface)
    edition: str           # edition of the norms, for the report title page
    validity: list         # acts behind the items with their last day in force (meta.validity)


def _read_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def covered_items(entry, items):
    """Items that rest on the act of a meta.validity entry: "ppr" or a text found in the item source."""
    selector = entry.get("items")
    if selector == "ppr":
        return [i for i in items if i.get("ppr")]
    if not selector:
        return []
    return [i for i in items if selector in (i.get("source") or "")]


def _is_score(value):
    # bool is a subclass of int in Python, so exclude it explicitly
    return type(value) is int and 1 <= value <= 5


def load_bases(paths=None):
    """Read all YAML files, check them and return Bases. Raise DataError on any problem."""
    paths = {**DEFAULT_PATHS, **(paths or {})}
    req = _read_yaml(paths["requirements"])
    sc = _read_yaml(paths["scores"])
    chk = _read_yaml(paths["checklist"])
    th = _read_yaml(paths["themes"])
    qn = _read_yaml(paths["questionnaire"])

    problems = []

    # (a) unique ids in the requirements base
    all_items = req["requirements"]
    seen = set()
    for item in all_items:
        if item["id"] in seen:
            problems.append(f"id повторяется: {item['id']}")
        seen.add(item["id"])
    items = [item for item in all_items if item.get("demo")]
    demo_ids = [item["id"] for item in items]

    # (b) every demo item has a score, and there are no extra scores
    scores = {}
    for row in sc["scores"]:
        if row["id"] in scores:
            problems.append(f"балл повторяется: {row['id']}")
        scores[row["id"]] = {"s": row.get("s"), "o": row.get("o"), "d": row.get("d")}
    missing = [i for i in demo_ids if i not in scores]
    extra = [i for i in scores if i not in demo_ids]
    if missing:
        problems.append("нет баллов для пунктов: " + ", ".join(missing))
    if extra:
        problems.append("баллы для пунктов, которых нет в демо: " + ", ".join(extra))

    # (c) S, O, D are integers from 1 to 5
    for item_id, s in scores.items():
        for key in ("s", "o", "d"):
            if not _is_score(s[key]):
                problems.append(f"{item_id}: {key.upper()} = {s[key]!r}, нужно целое от 1 до 5")

    # (d) priority matrix: rows S = 1..5, five values H / M / L each
    matrix = sc.get("priority_matrix") or {}
    if sorted(matrix) != [1, 2, 3, 4, 5]:
        problems.append(f"таблица групп: строки {sorted(matrix)}, нужны S = 1…5")
    for s_value, row in matrix.items():
        if not isinstance(row, list) or len(row) != 5 or not set(row) <= GROUPS:
            problems.append(f"таблица групп, строка S = {s_value}: {row}, нужно 5 значений H, M или L")

    # (e) flags in applies_if exist in the questionnaire; (f) conditional items have applies_if
    flags = {f["id"] for f in qn["flags"]} | {d["id"] for d in qn["derived"]}
    for item in items:
        applies_if = item.get("applies_if") or []
        for flag in applies_if:
            if flag not in flags:
                problems.append(f"{item['id']}: флага {flag} нет в анкете")
        if item.get("condition") is not None and not applies_if:
            problems.append(f"{item['id']}: есть condition, но пустой applies_if")

    # (g) q525 exists in the checklist of order No 525
    questions = {q["id"]: q for q in chk["questions"]}
    for item in items:
        if item.get("q525") not in questions:
            problems.append(f"{item['id']}: вопроса {item.get('q525')} нет в checklist_525.yaml")
    scope = chk["prototype_scope"]["production"]
    for q_id in scope:
        if q_id not in questions:
            problems.append(f"prototype_scope: вопроса {q_id} нет в checklist_525.yaml")

    # (h) topic exists in the themes table, each topic in one theme only
    topic_theme = {}
    for theme in th["themes"]:
        for topic in theme["topics"]:
            if topic in topic_theme:
                problems.append(f"topic {topic} указан в двух темах")
            topic_theme[topic] = theme["name"]
    for item in items:
        if item.get("topic") not in topic_theme:
            problems.append(f"{item['id']}: topic {item.get('topic')} нет в таблице тем")

    # (i) every act in meta.validity has a last day and covers at least one demo item
    validity = req["meta"].get("validity") or []
    for entry in validity:
        act = entry.get("act") or "?"
        if type(entry.get("last_day")) is not date:
            problems.append(f"validity, {act}: last_day {entry.get('last_day')!r}, нужна дата ГГГГ-ММ-ДД")
        if not covered_items(entry, items):
            problems.append(f"validity, {act}: ни один пункт демо не подходит под items = {entry.get('items')!r}")

    if problems:
        raise DataError(problems)

    return Bases(
        items=items,
        scores=scores,
        matrix=matrix,
        questions=questions,
        scope=scope,
        themes=[theme["name"] for theme in th["themes"]],
        topic_theme=topic_theme,
        flags=flags,
        questionnaire=qn,
        edition=req["meta"]["edition"],
        validity=validity,
    )
