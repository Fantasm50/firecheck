"""Priority of violations, readiness index and coverage of order No 525 (project-spec.md, 4.4–4.7).

Responses are a dict: item id -> response, for example
    {"GEN-022": {"answer": "violation"},
     "TER-001": {"answer": "na", "comment": "территории нет, цех в арендуемом здании"},
     "PROD-010": {"answer": "violation", "o_raise": 1, "o_reason": "стружка по всему цеху"}}
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

OK = "ok"                # «соответствует»
VIOLATION = "violation"  # «не соответствует»
NA = "na"                # «не применимо»
ANSWERS = {OK, VIOLATION, NA}

GROUP_RANK = {"H": 0, "M": 1, "L": 2}
CRITICAL_S = 5  # S = 5 is "threat to life" (fmea-scales-draft.md); such violations are critical (4.6)

# Coverage statuses of order No 525 questions (4.6)
NO_ITEMS_IN_BASE = "нет пунктов в базе"
NOT_RELEVANT = "к объекту не относится (по анкете)"
HAS_VIOLATIONS = "есть нарушения"
ALL_NA = "все пункты не применимы"
ALL_OK = "все пункты соответствуют"


class ResponsesError(Exception):
    """Raised when answers to the checklist are missing or wrong. Holds the list of problems."""

    def __init__(self, problems):
        self.problems = problems
        super().__init__("Ответы заполнены неверно:\n- " + "\n- ".join(problems))


@dataclass
class Violation:
    id: str
    item: dict       # the item from requirements YAML
    s: int
    o_base: int
    o_raise: int     # 0 or 1
    o: int           # effective O = min(5, o_base + o_raise)
    d: int
    group: str       # H, M or L by the effective O
    rpn_base: int    # S * o_base * D, used for comparison with experts
    rpn_eff: int     # S * effective O * D
    o_reason: str


@dataclass
class Result:
    index: Decimal | None   # readiness index, % with one decimal; None if nothing was rated
    na_count: int
    violations: list        # sorted by rule 4.5
    top5: list
    critical: list          # violations with S = 5, in the order of rule 4.5
    group_counts: dict      # H, M, L -> number of violations
    na_unconditional: list  # ids of items for every object (no applies_if) answered "not applicable"
    coverage: list         # (question id, number of items in checklist, status) in scope order
    cells: dict             # (S, effective O) -> number of violations, for the 5 x 5 matrix in the report
    hidden_count: int


def group(bases, s, o):
    """Priority group from the table in the scores file: priority_matrix[S][O - 1] (4.5)."""
    return bases.matrix[s][o - 1]


def sort_key(v):
    """Rule 4.5: group, S = 5 first, S*O desc, S desc, D desc, id."""
    return (GROUP_RANK[v.group], 0 if v.s == 5 else 1, -v.s * v.o, -v.s, -v.d, v.id)


def _blank(text):
    return not (text or "").strip()


def check_responses(bases, items, responses):
    """Return a list of problems: unanswered items, wrong answers, missing comments and reasons."""
    problems = []
    for item in items:
        item_id = item["id"]
        r = responses.get(item_id)
        if r is None:
            problems.append(f"{item_id}: нет ответа")
            continue
        answer = r.get("answer")
        if answer not in ANSWERS:
            problems.append(f"{item_id}: неизвестный ответ {answer!r}")
            continue
        if answer == NA and _blank(r.get("comment")):
            problems.append(f"{item_id}: для «не применимо» нужен комментарий")
        o_raise = r.get("o_raise", 0)
        if o_raise not in (0, 1) or type(o_raise) is bool:
            problems.append(f"{item_id}: повышение O может быть только 0 или 1")
        elif o_raise == 1:
            if answer != VIOLATION:
                problems.append(f"{item_id}: O повышают только для нарушения")
            elif bases.scores[item_id]["o"] == 5:
                problems.append(f"{item_id}: O уже 5, повысить нельзя")
            elif _blank(r.get("o_reason")):
                problems.append(f"{item_id}: для повышения O нужна причина")
    return problems


def make_violation(bases, item, response):
    sc = bases.scores[item["id"]]
    s, o_base, d = sc["s"], sc["o"], sc["d"]
    o_raise = response.get("o_raise", 0)
    o = min(5, o_base + o_raise)
    return Violation(
        id=item["id"], item=item, s=s, o_base=o_base, o_raise=o_raise, o=o, d=d,
        group=group(bases, s, o), rpn_base=s * o_base * d, rpn_eff=s * o * d,
        o_reason=response.get("o_reason", ""),
    )


def readiness_index(items, responses):
    """ok / (ok + violation) * 100, one decimal, half up; None if there is nothing to rate (4.6)."""
    answers = [responses[i["id"]]["answer"] for i in items]
    ok, bad = answers.count(OK), answers.count(VIOLATION)
    if ok + bad == 0:
        return None
    return (Decimal(ok) * 100 / Decimal(ok + bad)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def coverage(bases, items, responses):
    """Status of each question of order No 525 in scope; statuses are checked strictly in this order (4.6)."""
    in_base = {item["q525"] for item in bases.items}
    rows = []
    for q_id in bases.scope:
        answers = [responses[i["id"]]["answer"] for i in items if i["q525"] == q_id]
        if q_id not in in_base:
            status = NO_ITEMS_IN_BASE
        elif not answers:  # checked before "all NA": all([]) would be True
            status = NOT_RELEVANT
        elif VIOLATION in answers:
            status = HAS_VIOLATIONS
        elif all(a == NA for a in answers):
            status = ALL_NA
        else:
            status = ALL_OK
        rows.append((q_id, len(answers), status))
    return rows


def evaluate(bases, checklist, responses):
    """Full result for the report. Raises ResponsesError while any item is unanswered or wrong (4.7)."""
    items = checklist.items
    problems = check_responses(bases, items, responses)
    if problems:
        raise ResponsesError(problems)
    violations = sorted(
        (make_violation(bases, i, responses[i["id"]]) for i in items
         if responses[i["id"]]["answer"] == VIOLATION),
        key=sort_key,
    )
    cells = {}
    for v in violations:
        cells[(v.s, v.o)] = cells.get((v.s, v.o), 0) + 1
    return Result(
        index=readiness_index(items, responses),
        na_count=sum(1 for i in items if responses[i["id"]]["answer"] == NA),
        violations=violations,
        top5=violations[:5],
        critical=[v for v in violations if v.s == CRITICAL_S],
        group_counts={g: sum(1 for v in violations if v.group == g) for g in GROUP_RANK},
        na_unconditional=[i["id"] for i in items
                          if not i.get("applies_if") and responses[i["id"]]["answer"] == NA],
        coverage=coverage(bases, items, responses),
        cells=cells,
        hidden_count=checklist.hidden_count,
    )
