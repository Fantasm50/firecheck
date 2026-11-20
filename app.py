"""Streamlit interface: questionnaire -> checklist -> result (project-spec.md, 4.1–4.8).

Run from the project folder:  .venv/bin/streamlit run app.py
Answers are processed by the server that runs the app (the user's computer for a local run, the hosting
provider in the cloud) and kept only in memory for the current session; nothing is written to disk.
The same file also runs inside the browser (stlite, index.html of the public repository): then nothing
leaves the user's device.
"""

import base64
import sys
from datetime import date

import streamlit as st

from core.action_plan import STATUSES, clean_plan, overdue_ids, parse_due
from core.checklist import (AnswersError, asked_flags, build_checklist, by_theme, default_answers, object_type,
                            object_type_label)
from core.loader import DataError, load_bases
from core.plan_export import build_plan_xlsx
from core.recheck import apply_recheck
from core.report import build_report
from core.scoring import NA, OK, UNKNOWN, VIOLATION, ResponsesError, check_responses, evaluate
from core.session_file import SessionFileError, dump_session, load_session
from core.validity import EXPIRED, validity_alerts

ANSWER_LABELS = {OK: "соответствует", VIOLATION: "не соответствует", NA: "не применимо", UNKNOWN: "не знаю, уточнить"}
GROUP_LABELS = {"H": "высокий", "M": "средний", "L": "низкий"}
CHOICE_LABELS = {"yes": "да", "no": "нет", "unknown": "не знаю"}

WARNINGS = [
    "Самопроверка не заменяет проверку органа надзора; проверка МЧС не ограничивается "
    "вопросами проверочного листа (п. 2 приказа МЧС № 525).",
    "Версия базы норм: ППР № 1479 в редакции от 03.02.2025, действуют до 31.12.2026.",
    "Баллы S, O, D — черновые, до экспертной проверки.",
]

st.set_page_config(page_title="Цифровой сервис управления пожарной безопасностью", layout="wide")

# shown on every screen: honest note on the prototype status and on where the answers go
REPORT_NAME = "otchet-samoproverka.docx"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# stlite runs Python in the browser (Pyodide reports sys.platform == "emscripten")
IN_BROWSER = sys.platform == "emscripten"
if IN_BROWSER:
    PROTOTYPE_NOTICE = ("Прототип для демонстрации на вымышленных данных. Сервис работает прямо в вашем "
                        "браузере: ответы никуда не отправляются и пропадают после закрытия вкладки.")
else:
    PROTOTYPE_NOTICE = ("Прототип для демонстрации на вымышленных данных. Ответы обрабатываются на сервере, "
                        "где запущен сервис, и не сохраняются после закрытия вкладки. "
                        "Не вводите реальные данные предприятия.")


@st.cache_resource
def get_bases():
    return load_bases()


def norm_ref(item):
    """Reference for the user: PPR item, or the source field for DOC items (4.7)."""
    return f"ППР № 1479, п. {item['ppr']}" if item.get("ppr") else item.get("source", "")


def keep(key, value):
    """Restore a widget value saved earlier (Streamlit forgets widgets that were not shown)."""
    if key not in st.session_state and value is not None:
        st.session_state[key] = value


def unset(key, **default):
    """Pass a default only for a new widget: a restored widget takes its value from session state."""
    return {} if key in st.session_state else default


def go(step):
    st.session_state.step = step
    if step == "result":
        # the plan table starts from the saved plan each time the result screen is opened
        st.session_state.plan_snapshot = st.session_state.get("plan", {})
        st.session_state.plan_rev = st.session_state.get("plan_rev", 0) + 1
    st.rerun()


def offer_download(label, data, file_name, mime, primary=False):
    """Download button; in stlite the button cannot fetch the file, so a data: link is used instead."""
    if IN_BROWSER:
        encoded = base64.b64encode(data).decode("ascii")
        st.markdown(f'<a download="{file_name}" href="data:{mime};base64,{encoded}"><b>⬇ {label}</b></a>',
                    unsafe_allow_html=True)
    else:
        st.download_button(label, data, file_name=file_name, mime=mime, type="primary" if primary else "secondary")


def offer_session_file(bases, responses):
    """Save the questionnaire and the answers given so far to a file kept by the user (4.12)."""
    data = dump_session(bases, st.session_state.answers, responses, st.session_state.get("plan", {}),
                        closed=st.session_state.get("closed", {}), history=st.session_state.get("history", []))
    offer_download("Сохранить проверку в файл", data, f"proverka-{date.today().isoformat()}.json",
                   "application/json")
    st.caption("Файл остаётся у вас. Чтобы продолжить или пройти повторную проверку, загрузите его на экране анкеты.")


def session_widgets(responses):
    """Widget values of the checklist screen for saved responses (keys a_, c_, r_, w_ as in item_card)."""
    widgets = {}
    for item_id, r in responses.items():
        widgets[f"a_{item_id}"] = r["answer"]
        widgets[f"c_{item_id}"] = r.get("comment", "")
        if r.get("o_raise") == 1:
            widgets[f"r_{item_id}"] = True
            widgets[f"w_{item_id}"] = r.get("o_reason", "")
    return widgets


def apply_session(session):
    """Put a loaded session into the screens' state: questionnaire, checklist and answer widgets."""
    for key in [k for k in st.session_state if isinstance(k, str) and k[:2] in ("q_", "a_", "c_", "r_", "w_")]:
        del st.session_state[key]
    widgets = session_widgets(session.responses)
    st.session_state.answers = session.answers
    st.session_state.checklist = session.checklist
    st.session_state.responses = session.responses
    st.session_state.plan = session.plan
    st.session_state.closed = session.closed
    st.session_state.history = session.history
    st.session_state.widgets = widgets
    st.session_state.load_warnings = session.warnings
    go("result" if session.complete else "fill")


def load_session_widget(bases):
    """Questionnaire screen: continue a self-check saved earlier."""
    uploaded = st.file_uploader("Продолжить сохранённую проверку (файл .json)", type=["json"])
    if uploaded is None or st.session_state.get("loaded_file") == uploaded.file_id:
        return
    st.session_state.loaded_file = uploaded.file_id  # load each file once, not on every rerun
    try:
        session = load_session(bases, uploaded.getvalue())
    except SessionFileError as err:
        for problem in err.problems:
            st.error(problem)
        return
    apply_session(session)


# ---------- screen 1: questionnaire (4.1) ----------

# Demo scenarios (demo-scenario.md). Answer texts match the first words of the item "check" field.
# Production: fictional mechanical shop, 43 items, 6 violations, readiness index 86.0.
DEMO_OBJECT = {
    "object_type": "production",
    "name": "Механический цех (демо)",
    "category": "В3",
    "people_max": 60,
    "workplaces_per_floor": 20,
    "has_aps": True,
    "has_soue": True,
    "has_indoor_hydrants": True,
    "has_outdoor_water": True,
    "uses_oils_paints": True,
    "does_hot_work": True,
    "aupt_required": "no",  # fictional: rooms of category В3 are smaller than 1000 m² (res. No 1464, app. 3)
}
DEMO_VIOLATION_PREFIXES = (
    "Эвакуационные пути и выходы", "Нет изменений планировки", "При монтаже, ремонте",
    "Оборудованы пожарные щиты", "Место огневых работ", "Чердаки",
)
# Warehouse (2026-11-21): fictional storage of non-food goods with a ramp and aerosol packages.
DEMO_WAREHOUSE = {
    "object_type": "warehouse",
    "name": "Склад непродовольственных товаров (демо)",
    "category": "В3",
    "people_max": 12,
    "workplaces_per_floor": 6,
    "has_aps": True,
    "has_soue": True,
    "has_outdoor_water": True,
    "water_required": "no",  # fictional: the design documents do not require them
    "aupt_required": "no",
    "has_ramp": True,
    "stores_flammable_packages": True,
}
DEMO_WAREHOUSE_VIOLATIONS = (
    "В лестничных клетках нет кладовых", "В помещениях склада нет дежурного освещения",
    "Баллоны с горючими газами, тара", "Грузы и материалы, разгруженные на рампу", "Каждый огнетушитель имеет",
)
DEMOS = {"production": (DEMO_OBJECT, DEMO_VIOLATION_PREFIXES), "warehouse": (DEMO_WAREHOUSE, DEMO_WAREHOUSE_VIOLATIONS)}


def demo_fill(bases, kind="production"):
    """Fill the questionnaire and the checklist with a demo scenario and show the result."""
    demo, violations = DEMOS[kind]
    answers = default_answers(bases)
    answers.update(demo)
    checklist = build_checklist(bases, answers)
    responses = {}
    for item in checklist.items:
        answer = VIOLATION if item["check"].startswith(violations) else OK
        responses[item["id"]] = {"answer": answer}
    st.session_state.answers = answers
    st.session_state.checklist = checklist
    st.session_state.responses = responses
    st.session_state.widgets = {f"a_{i['id']}": responses[i["id"]]["answer"] for i in checklist.items}
    go("result")


def show_validity_alerts(bases):
    """Warn when an act behind the norms base expires soon or has expired (4.11)."""
    for alert in validity_alerts(bases):
        (st.error if alert.level == EXPIRED else st.warning)("⚠️ " + alert.text)


def questionnaire_screen(bases):
    qn = bases.questionnaire
    saved = st.session_state.get("answers", {})
    st.title("Анкета объекта")
    show_validity_alerts(bases)

    left, middle, right = st.columns([2, 1, 2])
    if left.button("Демо: типовой механический цех", help="Заполнить анкету и чек-лист данными демо-сценария "
                   "(вымышленный объект, 43 пункта, 6 нарушений) и сразу показать результат"):
        demo_fill(bases, "production")
    if middle.button("Демо: склад", help="Вымышленный склад непродовольственных товаров: анкета, чек-лист "
                     "и результат с нарушениями"):
        demo_fill(bases, "warehouse")
    load_session_widget(bases)

    for key in ("name", *(n["id"] for n in qn["numbers"]), *(f["id"] for f in qn["flags"]),
                *(c["id"] for c in qn["choices"])):
        keep(f"q_{key}", saved.get(key))

    type_choice = next(c for c in qn["choices"] if c["id"] == "object_type")
    keep("q_object_type", type_choice["default"])
    kind = st.radio(type_choice["label"], type_choice["options"], horizontal=True, key="q_object_type",
                    format_func=lambda v: type_choice["option_labels"][v],
                    help="От типа зависят вопросы анкеты и пункты чек-листа")
    st.text_input("Название объекта (необязательно)", key="q_name")
    cols = st.columns(2)
    for col, number in zip(cols, qn["numbers"]):
        key = f"q_{number['id']}"
        col.number_input(number["label"], min_value=0, step=1, key=key, **unset(key, value=None))

    for choice in qn["choices"]:
        options = choice["options"]
        if choice["id"] == "object_type":
            continue
        if choice["id"] == "category":
            key = f"q_{choice['id']}"
            st.selectbox(choice["label"], options, placeholder="не выбрано", key=key,
                         **unset(key, index=None))
        else:
            keep(f"q_{choice['id']}", choice["default"])
            st.radio(choice["label"], options, horizontal=True, help=choice.get("hint"),
                     format_func=lambda v: CHOICE_LABELS.get(v, v), key=f"q_{choice['id']}")

    # gated questions (storage rooms of a shop) appear right after their gate box is ticked
    ticked = {f["id"]: st.session_state.get(f"q_{f['id']}") for f in qn["flags"]}
    sections = {}
    for flag in asked_flags(bases, kind, ticked):
        sections.setdefault(flag["section"], []).append(flag)
    for section, flags in sections.items():
        st.subheader(section)
        for flag in flags:
            st.checkbox(flag["label"], help=flag.get("hint"), key=f"q_{flag['id']}")

    if st.button("Сформировать чек-лист", type="primary"):
        answers = default_answers(bases)
        other_type_flags = {f["id"] for f in qn["flags"]} - {f["id"] for f in asked_flags(bases, kind, ticked)}
        for key in list(answers) + ["name"]:
            value = st.session_state.get(f"q_{key}")
            if key in other_type_flags:
                continue  # a box of another type, or behind an unticked gate, stays "no"
            if value is not None and value != "":
                answers[key] = value
        try:
            checklist = build_checklist(bases, answers)
        except AnswersError as err:
            for problem in err.problems:
                st.error(problem)
            return
        st.session_state.answers = answers
        st.session_state.checklist = checklist
        go("fill")


# ---------- screen 2: filling the checklist (4.3, 4.4) ----------

def show_hidden(checklist):
    """Items hidden by the questionnaire with the condition that would include them (4.9.2)."""
    if not checklist.hidden:
        return
    with st.expander(f"По анкете скрыто пунктов: {len(checklist.hidden)} — почему"):
        st.caption("Пункт включается, если на объекте выполняется условие. Если оно выполняется, исправьте анкету.")
        st.dataframe([{"Пункт": i["id"], "Требование": i["check"], "Когда включается": i.get("condition") or ""}
                      for i in checklist.hidden], hide_index=True)


def read_responses(items):
    """Collect responses from widgets; items without an answer are left out."""
    responses = {}
    for item in items:
        answer = st.session_state.get(f"a_{item['id']}")
        if answer is None:
            continue
        r = {"answer": answer, "comment": st.session_state.get(f"c_{item['id']}", "")}
        if answer == VIOLATION and st.session_state.get(f"r_{item['id']}"):
            r["o_raise"] = 1
            r["o_reason"] = st.session_state.get(f"w_{item['id']}", "")
        responses[item["id"]] = r
    return responses


def fill_screen(bases):
    checklist = st.session_state.checklist
    items = checklist.items
    saved = st.session_state.get("widgets", {})
    for key, value in saved.items():
        keep(key, value)

    name = st.session_state.answers.get("name") or "Объект без названия"
    st.title(f"Чек-лист: {name}")
    st.caption("Тип объекта: " + object_type_label(bases, checklist.object_type))
    answered = sum(1 for i in items if st.session_state.get(f"a_{i['id']}") is not None)
    st.progress(answered / len(items), text=f"Отвечено {answered} из {len(items)}")
    show_hidden(checklist)

    for theme, group in by_theme(bases, items):
        with st.expander(f"{theme} ({len(group)})", expanded=True):
            for item in group:
                item_card(bases, item)

    # remember widget values to restore them after visiting other screens
    st.session_state.widgets = {k: v for k, v in st.session_state.items()
                                if isinstance(k, str) and k[:2] in ("a_", "c_", "r_", "w_")}

    responses = read_responses(items)
    problems = check_responses(bases, items, responses)
    unanswered = [p for p in problems if p.endswith("нет ответа")]
    other = [p for p in problems if not p.endswith("нет ответа")]
    for problem in other:
        st.warning(problem)
    offer_session_file(bases, responses)
    left, right = st.columns(2)
    if left.button("← Изменить анкету"):
        go("form")
    if right.button("Показать результат", type="primary", disabled=bool(problems),
                    help=f"Осталось без ответа: {len(unanswered)}" if unanswered else None):
        st.session_state.responses = responses
        go("result")


def item_card(bases, item):
    item_id = item["id"]
    with st.container(border=True):
        st.markdown(f"**{item['check']}**")
        st.caption(f"{norm_ref(item)} · вопрос листа {item['q525'].replace('Q525-', '№ ')} · {item_id}")
        if item.get("note"):
            st.info(item["note"])
        key = f"a_{item_id}"
        answer = st.radio("Ответ", list(ANSWER_LABELS), horizontal=True, format_func=ANSWER_LABELS.get,
                          key=key, label_visibility="collapsed", **unset(key, index=None))
        if answer == NA:
            st.text_input("Почему не применимо (обязательно)", key=f"c_{item_id}")
        elif answer == UNKNOWN:
            st.text_input("Что нужно уточнить (необязательно)", key=f"c_{item_id}")
        elif answer == VIOLATION:
            st.text_input("Комментарий (необязательно)", key=f"c_{item_id}")
            if bases.scores[item_id]["o"] < 5:
                if st.checkbox("Нарушение массовое или постоянное (повысить вероятность O на 1)", key=f"r_{item_id}"):
                    st.text_input("Причина повышения (обязательно)", key=f"w_{item_id}")


# ---------- screen 3: result (4.6–4.8) ----------

def result_screen(bases):
    checklist = st.session_state.checklist
    try:
        result = evaluate(bases, checklist, st.session_state.responses)
    except ResponsesError as err:
        for problem in err.problems:
            st.error(problem)
        if st.button("← К ответам"):
            go("fill")
        return

    name = st.session_state.answers.get("name") or "Объект без названия"
    st.title(f"Результат самопроверки: {name}")
    st.caption("Тип объекта: " + object_type_label(bases, checklist.object_type))
    show_validity_alerts(bases)
    show_progress(result)
    left, right = st.columns([1, 2])
    with left:
        # critical status goes first: the index alone hides a threat to life (4.6, 4.8)
        if result.critical:
            st.error(f"### Критических нарушений: {len(result.critical)}\n"
                     "Угроза жизни людей (S = 5). Устранить в первую очередь.")
        else:
            st.success("Критических нарушений (угроза жизни, S = 5) нет.")
        index = "—" if result.index is None else f"{result.index} %"
        st.metric("Индекс готовности", index)
        if result.index is None:
            st.caption("Нет пунктов с оценкой: индекс не считается.")
        counts = result.group_counts
        st.caption(f"Нарушений: {len(result.violations)} (приоритет высокий {counts['H']} · "
                   f"средний {counts['M']} · низкий {counts['L']}) · «не применимо»: {result.na_count} · "
                   f"скрыто по анкете: {result.hidden_count}")
        covered = sum(1 for _, n, _ in result.coverage if n > 0)
        st.caption(f"**Проверочный лист МЧС (приказ № 525): по этому объекту проверено вопросов — {covered} "
                   f"из {len(bases.questions)}.** Проверка МЧС шире листа; подробности — в блоке «Покрытие» ниже.")
        if result.unknown:
            st.warning(f"Требуют уточнения: {len(result.unknown)} пунктов ("
                       f"{', '.join(i['id'] for i in result.unknown)}). Они не входят в индекс: "
                       "уточните и вернитесь к ответам.")
        if result.na_unconditional:
            st.warning(f"«Не применимо» у пунктов, обязательных для всех объектов: "
                       f"{', '.join(result.na_unconditional)}. Проверьте комментарии: "
                       "эти пункты не входят ни в индекс, ни в реестр нарушений.")
    with right:
        st.subheader("Топ-5 нарушений по приоритету")
        if not result.top5:
            st.success("Нарушений не выявлено.")
        for n, v in enumerate(result.top5, 1):
            st.markdown(f"{n}. **{v.item['check']}**  \n"
                        f"{norm_ref(v.item)} · приоритет: {GROUP_LABELS[v.group]}")

    plan_section(result)
    show_hidden(checklist)

    with st.expander("Реестр всех нарушений по приоритету (с баллами S, O, D)"):
        st.dataframe([{
            "№": n, "Требование": v.item["check"], "Норма": norm_ref(v.item),
            "S": v.s, "O": v.o, "D": v.d, "Приоритет": GROUP_LABELS[v.group],
            "Срок устранения": "", "Ответственный": "",
        } for n, v in enumerate(result.violations, 1)], hide_index=True)

    with st.expander("Матрица 5 × 5: число нарушений по тяжести S и вероятности O"):
        rows = []
        for s in range(5, 0, -1):
            row = {"S \\ O": s}
            for o in range(1, 6):
                count = result.cells.get((s, o), 0)
                row[str(o)] = f"{count} ({bases.matrix[s][o - 1]})" if count else bases.matrix[s][o - 1]
            rows.append(row)
        st.dataframe(rows, hide_index=True)
        st.caption("В клетке: число нарушений и группа приоритета (H — высокий, M — средний, L — низкий).")

    with st.expander("Покрытие вопросов проверочного листа (приказ МЧС № 525)"):
        st.dataframe([{"Вопрос": bases.questions[q]["id"].replace("Q525-", "№ "), "Пунктов в чек-листе": n,
                       "Статус": status} for q, n, status in result.coverage], hide_index=True)
        st.caption(f"Остальные {len(bases.questions) - len(result.coverage)} вопросов листа в прототипе не проверяются.")

    for warning in WARNINGS:
        st.caption("⚠️ " + warning)

    report = build_report(bases, st.session_state.answers, checklist, result, st.session_state.responses,
                          plan=st.session_state.get("plan", {}))
    offer_download("Скачать отчёт (Word, DOCX)", report, REPORT_NAME, DOCX_MIME, primary=True)
    offer_session_file(bases, st.session_state.responses)

    left, middle, right = st.columns(3)
    if left.button("← К ответам"):
        go("fill")
    if result.violations and middle.button("Повторная проверка открытых нарушений",
                                           help="Пройти только открытые нарушения и отметить, устранены ли они"):
        go("recheck")
    if right.button("Новая проверка"):
        st.session_state.clear()
        st.rerun()


def plan_section(result):
    """Editable corrective action plan: action, owner, deadline, status for each violation (4.13)."""
    st.subheader("План устранения нарушений")
    if not result.violations:
        st.session_state.plan = {}
        st.caption("Нарушений нет — план не нужен.")
        return
    ids = [v.id for v in result.violations]
    base = clean_plan(st.session_state.get("plan_snapshot", {}), ids)
    label_to_status = {label: key for key, label in STATUSES.items()}
    rows = [{
        "№": n, "Нарушение": v.item["check"], "Приоритет": GROUP_LABELS[v.group],
        "Мероприятие": base[v.id]["action"], "Ответственный": base[v.id]["owner"],
        "Срок": parse_due(base[v.id]["due"]), "Статус": STATUSES[base[v.id]["status"]],
    } for n, v in enumerate(result.violations, 1)]
    edited = st.data_editor(
        rows, key=f"plan_{st.session_state.get('plan_rev', 0)}", hide_index=True, num_rows="fixed",
        disabled=["№", "Нарушение", "Приоритет"],
        column_config={
            "№": st.column_config.NumberColumn(width=40),
            "Нарушение": st.column_config.TextColumn(width="medium"),
            "Мероприятие": st.column_config.TextColumn(width="medium", help="Что сделать, чтобы устранить нарушение"),
            "Ответственный": st.column_config.TextColumn(help="Должность или ФИО"),
            "Срок": st.column_config.DateColumn(format="DD.MM.YYYY"),
            "Статус": st.column_config.SelectboxColumn(options=list(STATUSES.values()), required=True),
        })
    plan = {}
    for v, row in zip(result.violations, edited):
        due = parse_due(row["Срок"])
        plan[v.id] = {"action": row["Мероприятие"] or "", "owner": row["Ответственный"] or "",
                      "due": due.isoformat() if due else "", "status": label_to_status.get(row["Статус"], "new")}
    st.session_state.plan = clean_plan(plan, ids)
    late = overdue_ids(st.session_state.plan)
    if late:
        numbers = ", ".join(str(ids.index(i) + 1) for i in late)
        st.warning(f"Просрочено мероприятий: {len(late)} (№ {numbers}). Срок прошёл, а статус не «устранено».")
    xlsx = build_plan_xlsx(result, st.session_state.plan, st.session_state.answers.get("name") or "",
                           closed=st.session_state.get("closed", {}),
                           items={i["id"]: i for i in st.session_state.checklist.items})
    offer_download("Скачать план (Excel, XLSX)", xlsx, f"plan-ustraneniya-{date.today().isoformat()}.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.caption("План попадает в отчёт Word, в таблицу Excel и в файл проверки. Фамилии ответственных — "
               "персональные данные: в демо указывайте должности или вымышленные имена.")


def show_progress(result):
    """After a re-inspection: what changed since the previous state, and what was fixed (4.14)."""
    history = st.session_state.get("history", [])
    if history:
        last = history[-1]
        was = "—" if last["index"] is None else f"{last['index']} %"
        now = "—" if result.index is None else f"{result.index} %"
        day = ".".join(reversed(last["date"].split("-")))
        st.success(f"Повторная проверка {day}: индекс было {was} → стало {now}; нарушений {last['violations']} → "
                   f"{len(result.violations)}; критических {last['critical']} → {len(result.critical)}.")
    closed = st.session_state.get("closed", {})
    if closed:
        items = {i["id"]: i for i in st.session_state.checklist.items}
        with st.expander(f"Устранено и подтверждено: {len(closed)}"):
            st.dataframe([{
                "Нарушение": items.get(k, {}).get("check", k), "Мероприятие": e["action"],
                "Ответственный": e["owner"], "Подтверждено": ".".join(reversed(e["verified_on"].split("-"))),
                "Комментарий": e["note"],
            } for k, e in closed.items()], hide_index=True)


# ---------- screen 4: re-inspection of open violations (4.14) ----------

RECHECK_LABELS = {"fixed": "устранено", "open": "не устранено"}


def recheck_screen(bases):
    checklist = st.session_state.checklist
    result = evaluate(bases, checklist, st.session_state.responses)
    plan = st.session_state.get("plan", {})
    name = st.session_state.answers.get("name") or "Объект без названия"
    st.title(f"Повторная проверка: {name}")
    st.caption("Пройдите только открытые нарушения. Отметьте, устранено ли каждое, и при необходимости "
               "добавьте комментарий. Устранённые перейдут в «соответствует», план и индекс пересчитаются.")
    decisions = {}
    for n, v in enumerate(result.violations, 1):
        entry = plan.get(v.id, {})
        with st.container(border=True):
            st.markdown(f"**{n}. {v.item['check']}**")
            details = [norm_ref(v.item), f"приоритет: {GROUP_LABELS[v.group]}"]
            if entry.get("action"):
                details.append(f"мероприятие: {entry['action']}")
            if entry.get("owner"):
                details.append(f"ответственный: {entry['owner']}")
            st.caption(" · ".join(details))
            choice = st.radio("Итог", list(RECHECK_LABELS), format_func=RECHECK_LABELS.get, horizontal=True,
                              index=None, key=f"k_{v.id}", label_visibility="collapsed")
            note = st.text_input("Комментарий (необязательно)", key=f"n_{v.id}")
            if choice:
                decisions[v.id] = {"fixed": choice == "fixed", "note": note}
    left, right = st.columns(2)
    if left.button("← Отмена"):
        go("result")
    left_open = len(result.violations) - len(decisions)
    if right.button("Сохранить итоги повторной проверки", type="primary", disabled=left_open > 0,
                    help=f"Без отметки: {left_open}" if left_open else None):
        r = apply_recheck(st.session_state.responses, plan, st.session_state.get("closed", {}),
                          st.session_state.get("history", []), decisions, result)
        for key in [k for k in st.session_state if isinstance(k, str) and k[:2] in ("a_", "c_", "r_", "w_", "k_", "n_")]:
            del st.session_state[key]
        st.session_state.responses = r.responses
        st.session_state.plan = r.plan
        st.session_state.closed = r.closed
        st.session_state.history = r.history
        st.session_state.widgets = session_widgets(r.responses)
        go("result")


# ---------- main ----------

def main():
    try:
        bases = get_bases()
    except DataError as err:
        st.error("Не удалось загрузить базы норм.")
        for problem in err.problems:
            st.write("- " + problem)
        return
    st.info(PROTOTYPE_NOTICE, icon="ℹ️")
    for warning in st.session_state.pop("load_warnings", []):
        st.warning(warning)
    step = st.session_state.get("step", "form")
    if step == "fill":
        fill_screen(bases)
    elif step == "recheck":
        recheck_screen(bases)
    elif step == "result":
        result_screen(bases)
    else:
        questionnaire_screen(bases)


main()
