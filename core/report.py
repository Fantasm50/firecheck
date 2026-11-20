"""DOCX report of the self-check (project-spec.md, 4.7 and section 7).

build_report() returns the file as bytes, ready for a download button or for saving to disk.
"""

from datetime import date
from io import BytesIO

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from core.action_plan import due_text
from core.scoring import NA, OK, UNKNOWN, VIOLATION
from core.validity import validity_alerts

GROUP_LABELS = {"H": "высокий", "M": "средний", "L": "низкий"}
GROUP_COLORS = {"H": "F4C7C3", "M": "FCE8B2", "L": "D9EAD3"}  # light red, yellow, green

WARNINGS = [
    "Самопроверка не заменяет проверку органа надзора; проверка МЧС не ограничивается "
    "вопросами проверочного листа (п. 2 приказа МЧС России от 14.07.2026 № 525).",
    "Версия базы норм: Правила противопожарного режима (постановление Правительства РФ "
    "от 16.09.2020 № 1479) в редакции от 03.02.2025; действуют до 31.12.2026. "
    "Проверьте актуальную редакцию норм.",
    "Баллы тяжести S, вероятности O и обнаруживаемости D — черновые, до экспертной проверки.",
    "Пункты с отметкой «требует сверки» ещё не сверены с первоисточником.",
]


def norm_ref(item):
    """PPR item, or the source field for DOC items (4.7)."""
    return f"ППР № 1479, п. {item['ppr']}" if item.get("ppr") else item.get("source", "")


def requirement_text(item):
    text = item["check"]
    if not item.get("verified", False):
        text += " [требует сверки]"
    return text


def _shade(cell, color):
    """Fill a table cell with a background color (hex RGB)."""
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    cell._tc.get_or_add_tcPr().append(shd)


def _fix_widths(table, widths_cm):
    """Fixed layout with explicit column widths: some viewers collapse auto-sized tables."""
    table.autofit = False  # writes <w:tblLayout w:type="fixed"/> in the right place
    total = table._tbl.tblPr.find(qn("w:tblW"))
    total.set(qn("w:type"), "dxa")
    total.set(qn("w:w"), str(int(sum(widths_cm) * 567)))  # 1 cm = 567 twips
    for column, width in zip(table.columns, widths_cm):
        column.width = Cm(width)
    for row in table.rows:
        for cell, width in zip(row.cells, widths_cm):
            cell.width = Cm(width)


def _table(doc, header, rows, widths_cm):
    """Simple bordered table with a bold header row and fixed column widths."""
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for cell, text in zip(table.rows[0].cells, header):
        cell.text = ""
        cell.paragraphs[0].add_run(text).bold = True
        _shade(cell, "E7E6E6")
    for row in rows:
        cells = table.add_row().cells
        for cell, value in zip(cells, row):
            cell.text = str(value)
    _fix_widths(table, widths_cm)
    for row in table.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(10)
    return table


def _setup(doc):
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    for name in ("Title", "Heading 1"):
        fonts = doc.styles[name].element.get_or_add_rPr().get_or_add_rFonts()
        for attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
            fonts.attrib.pop(qn(f"w:{attr}"), None)  # theme fonts would override the name below
        for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
            fonts.set(qn(f"w:{attr}"), "Times New Roman")
    section = doc.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin = section.right_margin = Cm(2)
    section.top_margin = section.bottom_margin = Cm(2)


def build_report(bases, answers, checklist, result, responses, on_date=None, plan=None):
    """Return the DOCX report as bytes. plan: corrective actions by item id (4.13), may be empty."""
    on_date = on_date or date.today()
    doc = Document()
    _setup(doc)
    items = checklist.items
    counts = {a: sum(1 for i in items if responses[i["id"]]["answer"] == a) for a in (OK, VIOLATION, NA, UNKNOWN)}

    # ---------- title ----------
    doc.add_heading("Отчёт о самопроверке пожарной безопасности", level=0)
    for label, value in [
        ("Объект", answers.get("name") or "без названия"),
        ("Тип объекта", "производственный объект"),
        ("Дата самопроверки", on_date.strftime("%d.%m.%Y")),
        ("База норм", f"ППР № 1479, {bases.edition}"),
    ]:
        p = doc.add_paragraph()
        p.add_run(f"{label}: ").bold = True
        p.add_run(str(value))

    # ---------- 1. summary ----------
    doc.add_heading("1. Итоги", level=1)
    # critical status first: the index alone hides a threat to life (4.6, 4.7)
    p = doc.add_paragraph()
    p.add_run("Критических нарушений (угроза жизни, S = 5): ").bold = True
    run = p.add_run(str(len(result.critical)))
    run.bold, run.font.size = True, Pt(16)
    if result.critical:
        p.add_run(" — устранить в первую очередь: " + ", ".join(norm_ref(v.item) for v in result.critical))
    p = doc.add_paragraph()
    p.add_run("Индекс готовности: ").bold = True
    index = "не рассчитан (нет пунктов с оценкой)" if result.index is None else f"{result.index} %"
    run = p.add_run(index)
    run.bold, run.font.size = True, Pt(16)
    doc.add_paragraph(
        f"Пунктов в чек-листе: {len(items)}; соответствует: {counts[OK]}; "
        f"не соответствует: {counts[VIOLATION]}; не применимо: {counts[NA]}; требует уточнения: {counts[UNKNOWN]}. "
        f"По анкете скрыто пунктов: {result.hidden_count}."
    )
    counts = result.group_counts
    doc.add_paragraph(f"Нарушения по приоритету: высокий — {counts['H']}, средний — {counts['M']}, "
                      f"низкий — {counts['L']}.")
    if result.na_unconditional:
        doc.add_paragraph(f"«Не применимо» у пунктов, обязательных для всех объектов: "
                          f"{', '.join(result.na_unconditional)}. Эти пункты не входят ни в индекс, "
                          "ни в реестр нарушений; причина указана в комментарии к ответу.")
    doc.add_paragraph("Индекс = соответствует / (соответствует + не соответствует) × 100 %; "
                      "ответы «не применимо» не учитываются. Все пункты весят одинаково, поэтому "
                      "высокий индекс не означает отсутствия опасных нарушений: смотрите сначала "
                      "критические нарушения.").runs[0].font.size = Pt(10)

    # ---------- 2. top 5 ----------
    doc.add_heading("2. Пять нарушений с наивысшим приоритетом", level=1)
    if not result.top5:
        doc.add_paragraph("Нарушений не выявлено.")
    for n, v in enumerate(result.top5, 1):
        p = doc.add_paragraph()
        p.add_run(f"{n}. {requirement_text(v.item)}").bold = True
        p.add_run(f"\n{norm_ref(v.item)}; приоритет: {GROUP_LABELS[v.group]}")

    # ---------- 3. matrix ----------
    doc.add_heading("3. Матрица приоритетов: тяжесть S × вероятность O", level=1)
    table = doc.add_table(rows=6, cols=6)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.cell(0, 0).text = "S \\ O"
    for o in range(1, 6):
        table.cell(0, o).text = str(o)
    for r, s in enumerate(range(5, 0, -1), 1):
        table.cell(r, 0).text = str(s)
        for o in range(1, 6):
            cell = table.cell(r, o)
            count = result.cells.get((s, o), 0)
            cell.text = str(count) if count else ""
            _shade(cell, GROUP_COLORS[bases.matrix[s][o - 1]])
    _fix_widths(table, [1.6] * 6)
    for row in table.rows:
        for cell in row.cells:
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in cell.paragraphs[0].runs:
                run.bold = True
    doc.add_paragraph("В клетке — число нарушений. Цвет клетки — группа приоритета: "
                      "красный — высокий, жёлтый — средний, зелёный — низкий.").runs[0].font.size = Pt(10)

    # ---------- 4. register ----------
    doc.add_heading("4. Реестр нарушений по приоритету", level=1)
    if not result.violations:
        doc.add_paragraph("Нарушений не выявлено.")
    else:
        rows = []
        for n, v in enumerate(result.violations, 1):
            comment = (responses[v.id].get("comment") or "").strip()
            text = requirement_text(v.item) + (f"\nКомментарий: {comment}" if comment else "")
            if v.o_raise:
                text += f"\nВероятность O повышена с {v.o_base} до {v.o}: {v.o_reason}"
            entry = (plan or {}).get(v.id, {})
            if entry.get("action"):
                text += f"\nМероприятие: {entry['action']}"
            o = f"{v.o}*" if v.o_raise else str(v.o)
            rows.append([n, norm_ref(v.item), text, v.s, o, GROUP_LABELS[v.group], due_text(entry),
                         entry.get("owner", "")])
        table = _table(doc, ["№", "Норма", "Требование", "S", "O", "Приоритет", "Срок устранения", "Ответственный"],
                       rows, [0.7, 2.2, 4.9, 0.7, 0.8, 2.3, 2.3, 3.1])
        for row, v in zip(table.rows[1:], result.violations):
            _shade(row.cells[5], GROUP_COLORS[v.group])
        if any(v.o_raise for v in result.violations):
            doc.add_paragraph("* Вероятность O повышена специалистом: нарушение массовое или постоянное "
                              "(причина — в графе «Требование»).").runs[0].font.size = Pt(10)

    # ---------- 5. not applicable ----------
    na_items = [i for i in items if responses[i["id"]]["answer"] == NA]
    if na_items:
        doc.add_heading("5. Пункты «не применимо»", level=1)
        _table(doc, ["Норма", "Требование", "Почему не применимо"],
               [[norm_ref(i), requirement_text(i), responses[i["id"]].get("comment", "")] for i in na_items],
               [3.0, 9.0, 5.0])

    section = 6 if na_items else 5

    # ---------- «не знаю, уточнить» ----------
    if result.unknown:
        doc.add_heading(f"{section}. Пункты, требующие уточнения", level=1)
        doc.add_paragraph("На эти пункты специалист не смог ответить сразу. Они не входят в индекс готовности: "
                          "уточните и повторите проверку.").runs[0].font.size = Pt(10)
        _table(doc, ["Норма", "Требование", "Что уточнить"],
               [[norm_ref(i), requirement_text(i), responses[i["id"]].get("comment", "")] for i in result.unknown],
               [3.0, 9.0, 5.0])
        section += 1

    # ---------- hidden by the questionnaire, with the reason (4.9.2) ----------
    if checklist.hidden:
        doc.add_heading(f"{section}. Пункты, не включённые по анкете", level=1)
        _table(doc, ["Норма", "Требование", "Когда пункт включается"],
               [[norm_ref(i), requirement_text(i), i.get("condition") or ""] for i in checklist.hidden],
               [3.0, 9.0, 5.0])
        doc.add_paragraph("Если условие на объекте выполняется, исправьте анкету: пункт появится в чек-листе."
                          ).runs[0].font.size = Pt(10)
        section += 1

    # ---------- coverage of order No 525 ----------
    doc.add_heading(f"{section}. Покрытие вопросов проверочного листа (приказ МЧС № 525)", level=1)
    rows = [[q.replace("Q525-", "№ "), "; ".join(bases.questions[q].get("refs", [])), n, status]
            for q, n, status in result.coverage]
    _table(doc, ["Вопрос", "Нормы вопроса", "Пунктов", "Статус"], rows, [1.8, 8.2, 1.8, 5.2])
    rest = len(bases.questions) - len(bases.scope)
    doc.add_paragraph(f"Остальные {rest} вопросов листа в прототипе не проверяются.").runs[0].font.size = Pt(10)

    # ---------- warnings ----------
    doc.add_heading(f"{section + 1}. Важно", level=1)
    for alert in validity_alerts(bases, on_date):  # outdated or expiring acts go first
        doc.add_paragraph(style="List Bullet").add_run(alert.text).bold = True
    for warning in WARNINGS:
        doc.add_paragraph(warning, style="List Bullet")

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
