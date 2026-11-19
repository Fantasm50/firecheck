"""Tests for core/scoring.py: reference tests T1–T5, T7–T9 (project-spec.md, 8.2) and response checks."""

from decimal import Decimal

import pytest

from cases import CASE_A
from core.checklist import Checklist, build_checklist, default_answers
from core.loader import load_bases
from core.scoring import (ALL_NA, ALL_OK, HAS_VIOLATIONS, NA, NOT_RELEVANT, OK, VIOLATION,
                          ResponsesError, evaluate, group, make_violation, readiness_index, sort_key)


@pytest.fixture(scope="module")
def bases():
    return load_bases()


@pytest.fixture(scope="module")
def case_a(bases):
    return build_checklist(bases, {**default_answers(bases), **CASE_A})


def item(bases, item_id):
    return next(i for i in bases.items if i["id"] == item_id)


def checklist_of(bases, ids):
    return Checklist(items=[item(bases, i) for i in ids], hidden_count=0, flags=set())


def order(bases, ids):
    """Sorted ids of violations by rule 4.5."""
    vs = [make_violation(bases, item(bases, i), {"answer": VIOLATION}) for i in ids]
    return [v.id for v in sorted(vs, key=sort_key)]


def respond(checklist, answer=OK, **special):
    """All items get one answer; special maps id -> response dict."""
    out = {i["id"]: {"answer": answer} for i in checklist.items}
    for item_id, response in special.items():
        out[item_id.replace("_", "-")] = response
    return out


# ---------- T1: groups by the table ----------

@pytest.mark.parametrize("s, o, expected", [
    (5, 1, "H"), (4, 1, "M"), (4, 3, "H"), (3, 1, "L"), (3, 3, "M"),
    (3, 4, "H"), (2, 4, "M"), (2, 5, "M"), (1, 5, "L"),
])
def test_t1_group_cells(bases, s, o, expected):
    assert group(bases, s, o) == expected


# ---------- T2: groups of real items ----------

@pytest.mark.parametrize("item_id, sod, expected", [
    ("GEN-019", (5, 2, 1), "H"), ("GEN-022", (3, 5, 3), "H"), ("PROD-010", (3, 3, 1), "M"),
    ("GEN-002", (2, 2, 2), "L"), ("EXT-003", (2, 1, 1), "L"), ("DOC-005", (1, 1, 1), "L"),
])
def test_t2_real_items(bases, item_id, sod, expected):
    v = make_violation(bases, item(bases, item_id), {"answer": VIOLATION})
    assert (v.s, v.o, v.d) == sod
    assert v.group == expected


# ---------- T3, T4: order of violations ----------

def test_t3_order_inside_high_group(bases):
    given = ["GEN-012", "HOT-003", "GEN-021", "HOT-001", "GEN-019", "HOT-002", "PROD-005", "HOT-006", "GEN-037"]
    assert order(bases, given) == [
        "GEN-037", "GEN-019", "HOT-002", "HOT-001", "HOT-003", "PROD-005", "GEN-012", "GEN-021", "HOT-006",
    ]


def test_t4_order_across_groups(bases):
    assert order(bases, ["EXT-003", "PROD-010", "GEN-034", "PROD-008"]) == ["PROD-008", "GEN-034", "PROD-010", "EXT-003"]


# ---------- T5: readiness index ----------

def test_t5_index(bases):
    ids = ["GEN-001", "GEN-002", "GEN-006", "GEN-007", "GEN-009", "GEN-012", "GEN-013", "GEN-016", "GEN-017", "GEN-018"]
    items = [item(bases, i) for i in ids]
    answers = [OK] * 6 + [VIOLATION] * 2 + [NA] * 2
    responses = {i: {"answer": a} for i, a in zip(ids, answers)}
    assert readiness_index(items, responses) == Decimal("75.0")
    responses = {i: {"answer": a} for i, a in zip(ids[:3], [OK, VIOLATION, VIOLATION])}
    assert readiness_index(items[:3], responses) == Decimal("33.3")
    responses = {i: {"answer": NA} for i in ids[:3]}
    assert readiness_index(items[:3], responses) is None


# ---------- T7: top 5 ----------

def test_t7_top5_case_a(bases, case_a):
    result = evaluate(bases, case_a, respond(case_a, VIOLATION))
    assert [v.id for v in result.top5] == ["PROD-008", "GEN-018", "GEN-034", "SYS-001", "SYS-002"]
    assert result.violations[5].id == "GEN-024"
    groups = [v.group for v in result.violations]
    assert (groups.count("H"), groups.count("M"), groups.count("L")) == (19, 11, 9)
    assert result.index == Decimal("0.0")


def test_top5_shorter_and_empty(bases, case_a):
    two = evaluate(bases, case_a, respond(case_a, OK, GEN_022={"answer": VIOLATION}, PROD_010={"answer": VIOLATION}))
    assert len(two.top5) == 2
    none = evaluate(bases, case_a, respond(case_a, OK))
    assert none.top5 == [] and none.index == Decimal("100.0")


# ---------- T8: index and coverage, case A ----------

def test_t8_index_and_coverage(bases, case_a):
    na = {"answer": NA, "comment": "территория не принадлежит предприятию"}
    responses = respond(case_a, OK, GEN_022={"answer": VIOLATION}, PROD_010={"answer": VIOLATION},
                        TER_001=na, TER_002=na)
    result = evaluate(bases, case_a, responses)
    assert result.index == Decimal("94.6")
    assert [(v.id, v.group) for v in result.violations] == [("GEN-022", "H"), ("PROD-010", "M")]
    assert result.na_count == 2
    assert result.hidden_count == 24
    assert result.coverage == [
        ("Q525-01", 1, ALL_OK), ("Q525-02", 3, ALL_OK), ("Q525-03", 0, NOT_RELEVANT),
        ("Q525-04", 20, HAS_VIOLATIONS), ("Q525-05", 2, ALL_NA), ("Q525-06", 1, ALL_OK),
        ("Q525-12", 5, HAS_VIOLATIONS), ("Q525-19", 0, NOT_RELEVANT), ("Q525-21", 2, ALL_OK),
        ("Q525-22", 5, ALL_OK),
    ]
    assert result.cells == {(3, 5): 1, (3, 3): 1}
    assert result.critical == []
    assert result.group_counts == {"H": 1, "M": 1, "L": 0}
    assert result.na_unconditional == ["TER-001", "TER-002"]


# ---------- T11: critical violations next to the index, case A ----------

def test_t11_critical_violation_with_high_index(bases, case_a):
    # one locked exit gives a high index, but the status must show a threat to life
    result = evaluate(bases, case_a, respond(case_a, OK, GEN_019={"answer": VIOLATION}))
    assert result.index == Decimal("97.4")
    assert [v.id for v in result.critical] == ["GEN-019"]
    assert result.group_counts == {"H": 1, "M": 0, "L": 0}
    assert result.na_unconditional == []


def test_t11_critical_in_priority_order(bases, case_a):
    result = evaluate(bases, case_a, respond(case_a, VIOLATION))
    assert [v.id for v in result.critical] == ["PROD-008", "GEN-018", "GEN-034", "SYS-001", "SYS-002",
                                               "GEN-024", "GEN-037", "GEN-019", "GEN-020"]
    assert result.group_counts == {"H": 19, "M": 11, "L": 9}


def test_all_na_gives_no_index(bases):
    cl = checklist_of(bases, ["GEN-001", "GEN-002"])
    result = evaluate(bases, cl, respond(cl, NA, GEN_001={"answer": NA, "comment": "x"},
                                         GEN_002={"answer": NA, "comment": "y"}))
    assert result.index is None


# ---------- T9: raising O ----------

def test_t9_raise_o(bases):
    cl = checklist_of(bases, ["PROD-010", "EXT-003"])
    responses = {
        "PROD-010": {"answer": VIOLATION, "o_raise": 1, "o_reason": "стружка по всему цеху"},
        "EXT-003": {"answer": VIOLATION, "o_raise": 1, "o_reason": "на всех огнетушителях"},
    }
    result = evaluate(bases, cl, responses)
    v = {x.id: x for x in result.violations}
    assert (v["PROD-010"].o, v["PROD-010"].group) == (4, "H")
    assert (v["PROD-010"].rpn_base, v["PROD-010"].rpn_eff) == (9, 12)
    assert (v["EXT-003"].o, v["EXT-003"].group) == (2, "L")


def test_t9_cannot_raise_o_5(bases):
    cl = checklist_of(bases, ["GEN-022"])
    with pytest.raises(ResponsesError) as err:
        evaluate(bases, cl, {"GEN-022": {"answer": VIOLATION, "o_raise": 1, "o_reason": "везде"}})
    assert "O уже 5" in err.value.problems[0]


def test_t9_raise_needs_reason(bases):
    cl = checklist_of(bases, ["PROD-010"])
    with pytest.raises(ResponsesError):
        evaluate(bases, cl, {"PROD-010": {"answer": VIOLATION, "o_raise": 1, "o_reason": "   "}})


# ---------- response checks (4.7, 4.9.3) ----------

def test_unanswered_items_block_result(bases, case_a):
    responses = respond(case_a, OK)
    del responses["GEN-019"]
    with pytest.raises(ResponsesError) as err:
        evaluate(bases, case_a, responses)
    assert err.value.problems == ["GEN-019: нет ответа"]


def test_na_needs_comment(bases):
    cl = checklist_of(bases, ["GEN-034"])
    with pytest.raises(ResponsesError):
        evaluate(bases, cl, {"GEN-034": {"answer": NA, "comment": "  "}})
    ok = evaluate(bases, cl, {"GEN-034": {"answer": NA, "comment": "АПС на объекте нет"}})
    assert ok.na_count == 1


def test_raise_only_for_violation(bases):
    cl = checklist_of(bases, ["PROD-010"])
    with pytest.raises(ResponsesError):
        evaluate(bases, cl, {"PROD-010": {"answer": OK, "o_raise": 1, "o_reason": "x"}})
