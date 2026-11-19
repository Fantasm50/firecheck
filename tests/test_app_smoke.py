"""Smoke test of the Streamlit interface without a browser: questionnaire -> demo -> result."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_demo_flow_through_the_interface():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert at.title[0].value == "Анкета объекта"
    assert "Не вводите реальные данные предприятия" in at.info[0].value  # prototype notice on every screen
    next(b for b in at.button if b.label.startswith("Демо")).click().run()
    assert not at.exception
    assert at.title[0].value == "Результат самопроверки: Механический цех (демо)"
    assert "Критических нарушений: 1" in at.error[0].value
    assert at.metric[0].value == "86.0 %"
    assert "Не вводите реальные данные предприятия" in at.info[0].value
