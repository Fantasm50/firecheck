"""Corrective action plan as an Excel file (service-roadmap.md 1.3; project-spec.md, 4.13).

build_plan_xlsx() returns the .xlsx file as bytes: one row per violation in priority order,
editable columns for the action, owner, deadline and status; overdue rows are marked.
"""

from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

from core.action_plan import STATUSES, empty_entry, is_overdue, parse_due
from core.report import GROUP_COLORS, GROUP_LABELS, norm_ref

HEADERS = ["№", "Норма", "Нарушение", "Приоритет", "Мероприятие", "Ответственный", "Срок", "Статус", "Просрочено"]
WIDTHS = [5, 22, 60, 12, 40, 22, 12, 14, 12]
OVERDUE_FILL = "F4C7C3"  # light red, as the high priority in the report
THIN = Side(style="thin", color="BBBBBB")


def build_plan_xlsx(result, plan, object_name="", on_date=None, closed=None, items=None):
    """Return the plan as .xlsx bytes. result: evaluate() result; plan: item id -> entry.

    closed: violations confirmed as fixed (4.14), shown on a second sheet; items: item id -> base item.
    """
    on_date = on_date or date.today()
    wb = Workbook()
    ws = wb.active
    ws.title = "План устранения"
    ws["A1"] = f"План устранения нарушений: {object_name or 'объект без названия'}"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = (f"Сформирован {on_date.strftime('%d.%m.%Y')}. Порядок строк — по приоритету нарушений. "
                "Прототип: данные вымышленные, баллы приоритета черновые.")
    ws["A2"].font = Font(italic=True, size=9)

    header_row = 4
    for col, (title, width) in enumerate(zip(HEADERS, WIDTHS), 1):
        cell = ws.cell(row=header_row, column=col, value=title)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="E8E8E8")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        cell.border = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
        ws.column_dimensions[cell.column_letter].width = width

    for n, v in enumerate(result.violations, 1):
        entry = plan.get(v.id, empty_entry())
        due = parse_due(entry.get("due"))
        late = is_overdue(entry, on_date)
        values = [n, norm_ref(v.item), v.item["check"], GROUP_LABELS[v.group], entry.get("action", ""),
                  entry.get("owner", ""), due, STATUSES[entry.get("status", "new")], "да" if late else ""]
        row = header_row + n
        for col, value in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.border = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
        ws.cell(row=row, column=4).fill = PatternFill("solid", fgColor=GROUP_COLORS[v.group])
        ws.cell(row=row, column=7).number_format = "DD.MM.YYYY"
        if late:
            for col in (7, 9):
                ws.cell(row=row, column=col).fill = PatternFill("solid", fgColor=OVERDUE_FILL)

    last = header_row + len(result.violations)
    if result.violations:
        # status column offers the same four values as the screen
        statuses = DataValidation(type="list", formula1='"' + ",".join(STATUSES.values()) + '"', allow_blank=False)
        ws.add_data_validation(statuses)
        statuses.add(f"H{header_row + 1}:H{last}")
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    ws.auto_filter.ref = f"A{header_row}:I{max(last, header_row)}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToHeight = 0

    if closed:
        done = wb.create_sheet("Устранено")
        titles = ["№", "Норма", "Нарушение", "Мероприятие", "Ответственный", "Подтверждено", "Комментарий"]
        for col, (title, width) in enumerate(zip(titles, [5, 22, 60, 40, 22, 14, 40]), 1):
            cell = done.cell(row=1, column=col, value=title)
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="E8E8E8")
            done.column_dimensions[cell.column_letter].width = width
        for n, (item_id, e) in enumerate(closed.items(), 1):
            item = (items or {}).get(item_id, {"check": item_id})
            row = [n, norm_ref(item) if "ppr" in item or "source" in item else "", item["check"], e.get("action", ""),
                   e.get("owner", ""), parse_due(e.get("verified_on")), e.get("note", "")]
            for col, value in enumerate(row, 1):
                done.cell(row=n + 1, column=col, value=value).alignment = Alignment(wrap_text=True, vertical="top")
            done.cell(row=n + 1, column=6).number_format = "DD.MM.YYYY"
        done.freeze_panes = "A2"

    out = BytesIO()
    wb.save(out)
    return out.getvalue()
