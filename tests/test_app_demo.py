"""Tests for the demo fill in app.py (the demo-scenario.md scenario)."""
import app
from core.checklist import build_checklist, default_answers
from core.loader import load_bases
from core.scoring import VIOLATION, evaluate

bases = load_bases()


def test_demo_fill_result():
    answers = default_answers(bases)
    answers.update(app.DEMO_OBJECT)
    checklist = build_checklist(bases, answers)
    responses = {}
    for item in checklist.items:
        answer = VIOLATION if item["check"].startswith(app.DEMO_VIOLATION_PREFIXES) else "ok"
        responses[item["id"]] = {"answer": answer}
    result = evaluate(bases, checklist, responses)
    # values from demo-scenario.md: 43 items, 6 violations, index 86.0
    assert len(checklist.items) == 43
    assert len(result.violations) == 6
    assert str(result.index) == "86.0"
    assert [v.id for v in result.violations] == ["GEN-018", "HOT-001", "GEN-012", "GEN-033", "GEN-013", "EXT-005"]
    # the index is 86 %, but one violation is a threat to life (S = 5)
    assert [v.id for v in result.critical] == ["GEN-018"]
