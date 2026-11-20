"""Build the checklist from the questionnaire answers (project-spec.md, 4.1, 4.2, 4.3, 4.9.1, 4.9.2).

Answers are a plain dict, for example:
    {"people_max": 8, "workplaces_per_floor": 8, "has_dust_collectors": True,
     "water_required": "unknown", ...}
Flags that are not given count as "no"; choices that are not given take their default.
"""

from dataclasses import dataclass, field


class AnswersError(Exception):
    """Raised when the questionnaire is not filled in correctly. Holds the list of problems."""

    def __init__(self, problems):
        self.problems = problems
        super().__init__("Анкета заполнена неверно:\n- " + "\n- ".join(problems))


@dataclass
class Checklist:
    items: list          # included demo items, in file order
    hidden_count: int    # demo items hidden by the questionnaire (shown in the report, 4.9.2)
    flags: set           # true flags, including derived ones
    hidden: list = field(default_factory=list)  # demo items hidden by the questionnaire, in file order
    object_type: str = "production"             # type chosen in the questionnaire (core.loader.OBJECT_TYPES)
    scope: list = None                          # q525 ids of the coverage table; None = the type's prototype_scope


def object_type(answers):
    """Object type of the answers; old answers without a type are a production object."""
    return answers.get("object_type") or "production"


def object_type_label(bases, kind):
    """Human name of the object type from the questionnaire ("склад (здание или помещение для хранения)")."""
    choice = next(c for c in bases.questionnaire["choices"] if c["id"] == "object_type")
    return choice["option_labels"][kind]


def gate_open(entry, kind, answers):
    """True if the item or question has no gate for this type, or its gate flag is ticked."""
    flag = (entry.get("gate") or {}).get(kind)
    return flag is None or answers.get(flag) is True


def asked_flags(bases, kind, answers=None):
    """Flag questions asked for this object type, in questionnaire order.
    With answers, gated questions are asked only when their gate flag is ticked."""
    return [f for f in bases.questionnaire["flags"] if kind in (f.get("object_types") or [kind])
            and (answers is None or gate_open(f, kind, answers))]


def default_answers(bases):
    """Empty questionnaire: numbers not filled, all flags "no", choices at their default."""
    qn = bases.questionnaire
    answers = {n["id"]: None for n in qn["numbers"]}
    answers.update({f["id"]: False for f in qn["flags"]})
    answers.update({c["id"]: c["default"] for c in qn["choices"]})
    return answers


def check_answers(bases, answers):
    """Return a list of problems in the answers (empty list if all is fine)."""
    qn = bases.questionnaire
    problems = []
    for number in qn["numbers"]:
        value = answers.get(number["id"])
        # bool is a subclass of int, so exclude it explicitly
        if type(value) is not int or value < 0:
            problems.append(f"«{number['label']}»: нужно целое число не меньше 0")
    for flag in qn["flags"]:
        if type(answers.get(flag["id"], False)) is not bool:
            problems.append(f"«{flag['label']}»: нужен ответ да или нет")
    for choice in qn["choices"]:
        value = answers.get(choice["id"], choice["default"])
        if value is not None and value not in choice["options"]:
            problems.append(f"«{choice['label']}»: нет варианта {value!r}")
    known = ({n["id"] for n in qn["numbers"]} | {f["id"] for f in qn["flags"]}
             | {c["id"] for c in qn["choices"]} | {"name", "area", "floors"})
    for key in answers:
        if key not in known:
            problems.append(f"неизвестный вопрос анкеты: {key}")
    return problems


def true_flags(bases, answers):
    """Set of flags that are true: the "yes" answers plus the derived flags (4.1)."""
    # flags not asked for this object type do not count (a box ticked before the type was changed)
    flags = {f["id"] for f in asked_flags(bases, object_type(answers), answers) if answers.get(f["id"]) is True}
    people = answers["people_max"]
    workplaces = answers["workplaces_per_floor"]
    water_required = answers.get("water_required", "unknown")
    if people >= 50 or workplaces >= 10:
        flags.add("many_people")
    if people >= 50:
        flags.add("mass_people")
    # item 410 of the Fire Regime Rules: no shield if the building does not need water supply or AUPT
    if "has_indoor_hydrants" not in flags and "has_aupt" not in flags and water_required != "no":
        flags.add("no_water_no_aupt")
    # system is absent, but it is required by the norms or the specialist does not know (SYS-001...003)
    for system in ("aps", "soue", "aupt"):
        if f"has_{system}" not in flags and answers.get(f"{system}_required", "unknown") != "no":
            flags.add(f"{system}_missing")
    return flags


def build_checklist(bases, answers):
    """Select demo items of the object type whose applies_if has at least one true flag;
    items without condition always. Items of other object types are not listed as hidden."""
    problems = check_answers(bases, answers)
    if problems:
        raise AnswersError(problems)
    kind = object_type(answers)
    flags = true_flags(bases, answers)
    pool = [item for item in bases.items if kind in item["object_types"] and gate_open(item, kind, answers)]
    items = [item for item in pool if not item.get("applies_if") or flags & set(item["applies_if"])]
    included = {item["id"] for item in items}
    hidden = [item for item in pool if item["id"] not in included]
    # coverage table: the type's questions plus those of gated items in the pool (storage rooms of a shop)
    extra = {item["q525"] for item in pool}
    scope = [q for q in bases.questions if q in bases.scopes[kind] or q in extra]
    return Checklist(items=items, hidden_count=len(hidden), flags=flags, hidden=hidden, object_type=kind,
                     scope=scope)


def by_theme(bases, items):
    """Group items for the filling screen: themes in table order, items in file order (4.3).

    Themes without items are skipped. Returns a list of (theme name, list of items).
    """
    groups = {theme: [] for theme in bases.themes}
    for item in items:
        groups[bases.topic_theme[item["topic"]]].append(item)
    return [(theme, group) for theme, group in groups.items() if group]
