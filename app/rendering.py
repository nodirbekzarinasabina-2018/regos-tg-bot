from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.config import get_settings
from app.formatting import format_money, unix_to_local
from app.message_builders import _person_name, resolve_wholesale_sale_amount


def _wrap_lines(text: str, max_chars: int = 52) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) > max_chars:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)
    return lines


def render_png_from_text(text: str) -> bytes:
    font = ImageFont.load_default()
    raw_lines = []
    for line in text.splitlines():
        if line.strip():
            raw_lines.extend(_wrap_lines(line, max_chars=58))
        else:
            raw_lines.append("")

    line_height = 18
    width = 900
    height = 40 + len(raw_lines) * line_height + 20
    img = Image.new("RGB", (width, max(height, 220)), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (width - 1, max(height, 220) - 1)], outline=(220, 220, 220))
    y = 24
    for line in raw_lines:
        draw.text((24, y), line, fill=(25, 25, 25), font=font)
        y += line_height

    output = BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()


def render_pdf_from_text(text: str) -> bytes:
    blocks = [_thermal_text_block(_brand_name(), "brand")]
    if text.strip():
        blocks.extend(
            [
                _thermal_separator_block(),
                _thermal_text_block(text, "body"),
            ]
        )
    return _thermal_render_blocks(blocks)


_THERMAL_PAGE_WIDTH = 80 * mm
_THERMAL_MARGIN_X = 4 * mm
_THERMAL_MARGIN_Y = 4 * mm
_THERMAL_CONTENT_WIDTH = _THERMAL_PAGE_WIDTH - (_THERMAL_MARGIN_X * 2)
_THERMAL_SEPARATOR_GAP = 6

_THERMAL_STYLES: dict[str, dict[str, Any]] = {
    "brand": {
        "font_name": "RegosSansBold",
        "font_size": 12.5,
        "leading": 14.5,
        "align": "center",
        "space_after": 2.5,
    },
    "subtitle": {
        "font_name": "RegosSans",
        "font_size": 8.2,
        "leading": 10.2,
        "align": "center",
        "space_after": 2.5,
    },
    "title": {
        "font_name": "RegosSansBold",
        "font_size": 10.5,
        "leading": 12.5,
        "align": "center",
        "space_after": 3.0,
    },
    "section": {
        "font_name": "RegosSansBold",
        "font_size": 9.2,
        "leading": 11.4,
        "align": "left",
        "space_after": 1.5,
    },
    "body": {
        "font_name": "RegosSans",
        "font_size": 8.6,
        "leading": 10.8,
        "align": "left",
        "space_after": 1.2,
    },
    "strong": {
        "font_name": "RegosSansBold",
        "font_size": 9.2,
        "leading": 11.6,
        "align": "left",
        "space_after": 1.5,
    },
    "total": {
        "font_name": "RegosSansBold",
        "font_size": 10.2,
        "leading": 12.8,
        "align": "left",
        "space_after": 1.8,
    },
    "meta": {
        "font_name": "RegosSans",
        "font_size": 7.8,
        "leading": 9.6,
        "align": "left",
        "space_after": 1.0,
    },
}


def _thermal_wrap_text(text: str, font_name: str, font_size: float, max_width: float) -> list[str]:
    text = str(text or "").strip()
    if not text:
        return [""]

    def split_token(token: str) -> list[str]:
        if pdfmetrics.stringWidth(token, font_name, font_size) <= max_width:
            return [token]

        parts: list[str] = []
        current = ""
        for char in token:
            candidate = f"{current}{char}"
            if current and pdfmetrics.stringWidth(candidate, font_name, font_size) > max_width:
                parts.append(current)
                current = char
            else:
                current = candidate
        if current:
            parts.append(current)
        return parts or [token]

    lines: list[str] = []
    current = ""
    for raw_word in text.split():
        for word in split_token(raw_word):
            candidate = f"{current} {word}".strip()
            if current and pdfmetrics.stringWidth(candidate, font_name, font_size) > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
    if current:
        lines.append(current)
    return lines or [text]


def _thermal_prepare_text(text: str, style_name: str) -> list[str]:
    style = _THERMAL_STYLES[style_name]
    prepared: list[str] = []
    for raw_line in str(text or "").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            prepared.append("")
            continue
        prepared.extend(
            _thermal_wrap_text(
                stripped,
                style["font_name"],
                style["font_size"],
                _THERMAL_CONTENT_WIDTH,
            )
        )
    return prepared or [""]


def _thermal_text_block(text: str, style_name: str) -> dict[str, Any]:
    return {"type": "text", "style": style_name, "text": text}


def _thermal_item_block(item_text: str, detail_text: str) -> dict[str, Any]:
    return {"type": "item", "item_text": item_text, "detail_text": detail_text}


def _thermal_separator_block() -> dict[str, Any]:
    return {"type": "separator"}


def _thermal_spacer_block(size: float = 4.0) -> dict[str, Any]:
    return {"type": "spacer", "size": float(size)}


def _thermal_render_blocks(blocks: list[dict[str, Any]]) -> bytes:
    _register_fonts()

    prepared_blocks: list[dict[str, Any]] = []
    total_height = _THERMAL_MARGIN_Y * 2

    for block in blocks:
        block_type = block["type"]
        if block_type == "text":
            style_name = str(block["style"])
            style = _THERMAL_STYLES[style_name]
            lines = _thermal_prepare_text(str(block["text"]), style_name)
            block_height = (len(lines) * float(style["leading"])) + float(style["space_after"])
            prepared_blocks.append({"type": "text", "style": style_name, "lines": lines})
            total_height += block_height
            continue
        if block_type == "item":
            body_style = _THERMAL_STYLES["body"]
            meta_style = _THERMAL_STYLES["meta"]
            item_text = str(block["item_text"])
            detail_text = str(block["detail_text"])
            single_line_text = f"{item_text}  {detail_text}"
            fits_single_line = (
                pdfmetrics.stringWidth(
                    single_line_text,
                    str(body_style["font_name"]),
                    float(body_style["font_size"]),
                )
                <= _THERMAL_CONTENT_WIDTH
            )
            prepared_blocks.append(
                {
                    "type": "item",
                    "single_line": fits_single_line,
                    "item_text": item_text,
                    "detail_text": detail_text,
                    "item_font_name": str(body_style["font_name"]),
                    "item_font_size": float(body_style["font_size"]),
                    "item_leading": float(body_style["leading"]),
                    "detail_font_name": str(meta_style["font_name"]),
                    "detail_font_size": float(meta_style["font_size"]),
                    "detail_leading": float(meta_style["leading"]),
                    "space_after": 2.2,
                }
            )
            total_height += float(body_style["leading"]) + 2.2
            if not fits_single_line:
                total_height += float(meta_style["leading"])
            continue
        if block_type == "separator":
            prepared_blocks.append(block)
            total_height += _THERMAL_SEPARATOR_GAP
            continue
        size = float(block.get("size") or 0)
        prepared_blocks.append({"type": "spacer", "size": size})
        total_height += size

    page_height = max(total_height + 2, 100 * mm)
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(_THERMAL_PAGE_WIDTH, page_height))
    pdf.setAuthor(_brand_name())
    pdf.setTitle("Receipt")

    y = page_height - _THERMAL_MARGIN_Y
    for block in prepared_blocks:
        block_type = block["type"]
        if block_type == "separator":
            y -= _THERMAL_SEPARATOR_GAP / 2
            pdf.setLineWidth(1.2)
            pdf.line(_THERMAL_MARGIN_X, y, _THERMAL_PAGE_WIDTH - _THERMAL_MARGIN_X, y)
            y -= _THERMAL_SEPARATOR_GAP / 2
            continue
        if block_type == "spacer":
            y -= float(block["size"])
            continue
        if block_type == "item":
            if bool(block["single_line"]):
                y -= float(block["item_leading"])
                pdf.setFont(str(block["item_font_name"]), float(block["item_font_size"]))
                pdf.drawString(
                    _THERMAL_MARGIN_X,
                    y,
                    f"{block['item_text']}  {block['detail_text']}",
                )
            else:
                y -= float(block["item_leading"])
                pdf.setFont(str(block["item_font_name"]), float(block["item_font_size"]))
                pdf.drawString(_THERMAL_MARGIN_X, y, str(block["item_text"]))
                y -= float(block["detail_leading"])
                pdf.setFont(str(block["detail_font_name"]), float(block["detail_font_size"]))
                pdf.drawString(_THERMAL_MARGIN_X, y, str(block["detail_text"]))
            y -= float(block["space_after"])
            continue

        style = _THERMAL_STYLES[str(block["style"])]
        pdf.setFont(str(style["font_name"]), float(style["font_size"]))
        for line in block["lines"]:
            y -= float(style["leading"])
            if not line:
                continue
            text_width = pdfmetrics.stringWidth(line, str(style["font_name"]), float(style["font_size"]))
            align = str(style["align"])
            if align == "center":
                x = (_THERMAL_PAGE_WIDTH - text_width) / 2
            elif align == "right":
                x = _THERMAL_PAGE_WIDTH - _THERMAL_MARGIN_X - text_width
            else:
                x = _THERMAL_MARGIN_X
            pdf.drawString(x, y, line)
        y -= float(style["space_after"])

    pdf.showPage()
    pdf.save()
    return output.getvalue()


def _thermal_money(amount: float, currency_code: str) -> str:
    if currency_code == "UZS":
        return f"{format_money(amount)} so'm"
    return f"{_format_currency_value(amount)} {currency_code}"


def _thermal_receipt_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "thermal_brand",
            parent=base["Normal"],
            fontName="RegosSansBold",
            fontSize=15,
            leading=17,
            alignment=1,
            textColor=colors.black,
            spaceAfter=1,
        ),
        "subtitle": ParagraphStyle(
            "thermal_subtitle",
            parent=base["Normal"],
            fontName="RegosSans",
            fontSize=8.6,
            leading=10,
            alignment=1,
            textColor=colors.black,
            spaceAfter=1,
        ),
        "title": ParagraphStyle(
            "thermal_title",
            parent=base["Normal"],
            fontName="RegosSansBold",
            fontSize=11.5,
            leading=13,
            alignment=1,
            textColor=colors.black,
            spaceAfter=4,
        ),
        "info_label": ParagraphStyle(
            "thermal_info_label",
            parent=base["Normal"],
            fontName="RegosSansBold",
            fontSize=8.3,
            leading=10,
            textColor=colors.black,
        ),
        "info_value": ParagraphStyle(
            "thermal_info_value",
            parent=base["Normal"],
            fontName="RegosSans",
            fontSize=8.3,
            leading=10,
            textColor=colors.black,
        ),
        "table_header": ParagraphStyle(
            "thermal_table_header",
            parent=base["Normal"],
            fontName="RegosSansBold",
            fontSize=7.6,
            leading=9,
            alignment=1,
            textColor=colors.black,
        ),
        "table_item": ParagraphStyle(
            "thermal_table_item",
            parent=base["Normal"],
            fontName="RegosSans",
            fontSize=7.4,
            leading=8.7,
            textColor=colors.black,
        ),
        "table_qty": ParagraphStyle(
            "thermal_table_qty",
            parent=base["Normal"],
            fontName="RegosSans",
            fontSize=7.2,
            leading=8.5,
            alignment=1,
            textColor=colors.black,
        ),
        "table_num": ParagraphStyle(
            "thermal_table_num",
            parent=base["Normal"],
            fontName="RegosSans",
            fontSize=7.2,
            leading=8.5,
            alignment=2,
            textColor=colors.black,
        ),
        "summary_label": ParagraphStyle(
            "thermal_summary_label",
            parent=base["Normal"],
            fontName="RegosSansBold",
            fontSize=9.7,
            leading=11.8,
            textColor=colors.black,
        ),
        "summary_value": ParagraphStyle(
            "thermal_summary_value",
            parent=base["Normal"],
            fontName="RegosSansBold",
            fontSize=9.7,
            leading=11.8,
            alignment=2,
            textColor=colors.black,
        ),
    }


def _thermal_story_pdf(story: list[Any]) -> bytes:
    _register_fonts()
    available_width = _THERMAL_CONTENT_WIDTH
    estimated_height = (_THERMAL_MARGIN_Y * 2) + (8 * mm)
    for flowable in story:
        _, height = flowable.wrap(available_width, 10_000)
        estimated_height += height

    output = BytesIO()
    pdf = SimpleDocTemplate(
        output,
        pagesize=(_THERMAL_PAGE_WIDTH, max(estimated_height, 120 * mm)),
        leftMargin=_THERMAL_MARGIN_X,
        rightMargin=_THERMAL_MARGIN_X,
        topMargin=_THERMAL_MARGIN_Y,
        bottomMargin=_THERMAL_MARGIN_Y,
    )
    pdf.build(story)
    return output.getvalue()


def _thermal_quantity(quantity: float) -> str:
    rounded = round(float(quantity or 0), 3)
    if abs(rounded - int(rounded)) < 0.001:
        return str(int(round(rounded)))
    return f"{rounded:,.3f}".replace(",", " ").rstrip("0").rstrip(".")


def render_inventory_snapshot_pdf(
    *,
    report_date: str,
    stock_rows: list[dict[str, Any]],
    total_item_count: int,
    total_units: float,
    total_value: float,
    currency_code: str = "UZS",
) -> bytes:
    _register_fonts()
    styles = _pdf_styles()

    output = BytesIO()
    pdf = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    story: list[Any] = []
    story.extend(
        _build_header_block(
            _brand_name(),
            "",
            "OSTATKA",
            report_date,
            styles,
            title_text="OMBOR QOLDIQ HISOBOTI",
            subtitle_text="Omborlar bo'yicha umumiy qoldiq summasi",
        )
    )
    story.extend(
        _build_info_section(
            "QISQACHA",
            [
                ("Omborlar", f"{len(stock_rows)} ta", "Mahsulotlar", f"{total_item_count} ta"),
                ("Jami birlik", _format_number(total_units), "Jami summa", _format_currency(total_value, currency_code)),
            ],
            styles,
        )
    )

    story.extend([_section_bar("OMBORLAR BO'YICHA HISOBOT", styles), Spacer(1, 4)])
    rows: list[list[Any]] = [
        [
            Paragraph("#", styles["table_header"]),
            Paragraph("Ombor", styles["table_header"]),
            Paragraph("Mahsulotlar", styles["table_header"]),
            Paragraph("Birlik", styles["table_header"]),
            Paragraph("Qoldiq summasi", styles["table_header"]),
        ]
    ]
    for index, row in enumerate(stock_rows, start=1):
        rows.append(
            [
                Paragraph(str(index), styles["table_cell_right"]),
                Paragraph(_escape(str(row.get("name") or "-")), styles["table_cell"]),
                Paragraph(_escape(str(int(row.get("item_count") or 0))), styles["table_cell_right"]),
                Paragraph(_escape(_format_number(float(row.get("unit_total") or 0))), styles["table_cell_right"]),
                Paragraph(
                    _escape(_format_currency(float(row.get("value_total") or 0), currency_code)),
                    styles["table_cell_right"],
                ),
            ]
        )

    table = Table(rows, colWidths=[12 * mm, 74 * mm, 26 * mm, 28 * mm, 38 * mm], repeatRows=1)
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    for row_index in range(1, len(rows)):
        if row_index % 2 == 0:
            style_commands.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#F8FAFC")))
    table.setStyle(TableStyle(style_commands))
    story.extend([table, Spacer(1, 10)])

    story.extend(
        _build_generic_summary_section(
            "JAMI",
            [
                ("Omborlar soni", f"{len(stock_rows)} ta", "normal"),
                ("Mahsulotlar soni", f"{total_item_count} ta", "normal"),
                ("Umumiy birlik", _format_number(total_units), "info"),
                ("Barcha do'konlar jami", _format_currency(total_value, currency_code), "total"),
            ],
            styles,
        )
    )

    pdf.build(story)
    return output.getvalue()


def render_low_stock_pdf(
    *,
    report_date: str,
    rows: list[dict[str, Any]],
) -> bytes:
    _register_fonts()
    styles = _pdf_styles()

    output = BytesIO()
    pdf = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    story: list[Any] = []
    story.extend(
        _build_header_block(
            _brand_name(),
            "",
            "LOW-STOCK",
            report_date,
            styles,
            title_text="KAM QOLGAN MAHSULOTLAR",
            subtitle_text="1 ta va undan kam qolgan mahsulotlar ro'yxati",
        )
    )
    story.extend(
        _build_generic_summary_section(
            "QISQACHA",
            [
                ("Kam qolgan mahsulotlar", f"{len(rows)} ta", "warning"),
            ],
            styles,
        )
    )
    story.extend([_section_bar("RO'YXAT", styles), Spacer(1, 4)])

    data: list[list[Any]] = [
        [
            Paragraph("#", styles["table_header"]),
            Paragraph("Mahsulot", styles["table_header"]),
            Paragraph("Omborlar bo'yicha", styles["table_header"]),
            Paragraph("Jami", styles["table_header"]),
        ]
    ]
    for index, row in enumerate(rows, start=1):
        data.append(
            [
                Paragraph(str(index), styles["table_cell_right"]),
                Paragraph(_escape(str(row.get("name") or "-")), styles["table_cell"]),
                Paragraph(_escape(str(row.get("stocks_text") or "-")), styles["table_cell"]),
                Paragraph(_escape(str(row.get("total") or "0")), styles["table_cell_right"]),
            ]
        )

    table = Table(data, colWidths=[12 * mm, 78 * mm, 70 * mm, 18 * mm], repeatRows=1)
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    for row_index in range(1, len(data)):
        style_commands.append(("LINEBELOW", (0, row_index), (-1, row_index), 0.35, colors.HexColor("#CBD5E1")))
        if row_index % 2 == 0:
            style_commands.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#F8FAFC")))
    table.setStyle(TableStyle(style_commands))
    story.extend([table, Spacer(1, 10)])

    pdf.build(story)
    return output.getvalue()


def render_debt_report_pdf(
    *,
    report_date: str,
    records: list[dict[str, Any]],
    total_amount: float,
) -> bytes:
    _register_fonts()
    styles = _pdf_styles()

    output = BytesIO()
    pdf = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    wholesale_count = sum(1 for row in records if str(row.get("source")) == "Ulgurji")
    retail_count = sum(1 for row in records if str(row.get("source")) == "Chakana")

    story: list[Any] = []
    story.extend(
        _build_header_block(
            _brand_name(),
            "",
            "QARZDORLAR",
            report_date,
            styles,
            title_text="QARZDORLAR RO'YXATI",
            subtitle_text="USD valyutadagi qarzdorlar hisoboti",
        )
    )
    story.extend(
        _build_generic_summary_section(
            "QISQACHA",
            [
                ("Ulgurji", f"{wholesale_count} ta", "normal"),
                ("Chakana", f"{retail_count} ta", "normal"),
                ("Jami qarzdorlar", f"{len(records)} ta", "info"),
                ("Jami qarz", _format_currency(total_amount, "USD"), "total"),
            ],
            styles,
        )
    )
    story.extend([_section_bar("QARZDORLAR", styles), Spacer(1, 4)])

    data: list[list[Any]] = [
        [
            Paragraph("#", styles["table_header"]),
            Paragraph("Turi", styles["table_header"]),
            Paragraph("Qarzdor", styles["table_header"]),
            Paragraph("Telefon", styles["table_header"]),
            Paragraph("Qarz", styles["table_header"]),
        ]
    ]
    for index, row in enumerate(records, start=1):
        data.append(
            [
                Paragraph(str(index), styles["table_cell_right"]),
                Paragraph(_escape(str(row.get("source") or "-")), styles["table_cell"]),
                Paragraph(_escape(str(row.get("name") or "-")), styles["table_cell"]),
                Paragraph(_escape(str(row.get("phone") or "-")), styles["table_cell"]),
                Paragraph(_escape(_format_currency(float(row.get("amount") or 0), "USD")), styles["table_cell_right"]),
            ]
        )

    table = Table(data, colWidths=[10 * mm, 24 * mm, 64 * mm, 46 * mm, 34 * mm], repeatRows=1)
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    for row_index in range(1, len(data)):
        style_commands.append(("LINEBELOW", (0, row_index), (-1, row_index), 0.35, colors.HexColor("#CBD5E1")))
        if row_index % 2 == 0:
            style_commands.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#F8FAFC")))
    table.setStyle(TableStyle(style_commands))
    story.extend([table, Spacer(1, 10)])

    pdf.build(story)
    return output.getvalue()


def render_private_debt_pdf(
    *,
    report_date: str,
    debtor_name: str,
    debtor_phone: str,
    records: list[dict[str, Any]],
    total_amount: float,
) -> bytes:
    _register_fonts()
    styles = _pdf_styles()

    output = BytesIO()
    pdf = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    story: list[Any] = []
    story.extend(
        _build_header_block(
            _brand_name(),
            "",
            "ESLATMA",
            report_date,
            styles,
            title_text="QARZDORLIK ESLATMASI",
            subtitle_text="Mijozga yuboriladigan shaxsiy qarzdorlik hujjati",
        )
    )
    story.extend(
        _build_info_section(
            "MIJOZ MA'LUMOTLARI",
            [
                ("Nomi", debtor_name or "Noma'lum", "Telefon", debtor_phone or "-"),
                ("Yozuvlar", f"{len(records)} ta", "Jami qarz", _format_currency(total_amount, "USD")),
            ],
            styles,
        )
    )
    story.extend([_section_bar("ESLATMA", styles), Spacer(1, 4)])
    story.append(Paragraph(_escape(f"Assalomu alaykum, {debtor_name or 'hurmatli mijoz'}."), styles["body"]))
    story.append(Spacer(1, 4))
    story.append(
        Paragraph(
            _escape(
                "Sizda qarzdorlik mavjudligini eslatib o'tamiz. "
                "Iltimos, to'lovni imkon qadar vaqtida amalga oshirishingizni so'raymiz."
            ),
            styles["body"],
        )
    )
    story.append(Spacer(1, 10))
    story.extend([_section_bar("QARZDORLIK HOLATI", styles), Spacer(1, 4)])

    data: list[list[Any]] = [
        [
            Paragraph("#", styles["table_header"]),
            Paragraph("Turi", styles["table_header"]),
            Paragraph("Qarz", styles["table_header"]),
        ]
    ]
    for index, row in enumerate(records, start=1):
        data.append(
            [
                Paragraph(str(index), styles["table_cell_right"]),
                Paragraph(_escape(str(row.get("source") or "-")), styles["table_cell"]),
                Paragraph(_escape(_format_currency(float(row.get("amount") or 0), "USD")), styles["table_cell_right"]),
            ]
        )

    table = Table(data, colWidths=[14 * mm, 96 * mm, 50 * mm], repeatRows=1)
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    for row_index in range(1, len(data)):
        style_commands.append(("LINEBELOW", (0, row_index), (-1, row_index), 0.35, colors.HexColor("#CBD5E1")))
        if row_index % 2 == 0:
            style_commands.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#F8FAFC")))
    table.setStyle(TableStyle(style_commands))
    story.extend([table, Spacer(1, 10)])

    story.extend(
        _build_generic_summary_section(
            "JAMI",
            [
                ("Shaxsiy qarz", _format_currency(total_amount, "USD"), "total"),
            ],
            styles,
        )
    )

    pdf.build(story)
    return output.getvalue()


def render_sale_pdf(
    *,
    doc: dict[str, Any],
    operations: list[dict[str, Any]],
    previous_debt_base: float,
    timezone_name: str,
) -> bytes:
    _register_fonts()
    company_name = _extract_company_name(doc)
    stock_name = _extract_stock_name(doc)
    actor_name = _person_name(doc.get("attached_user")) or _person_name(doc.get("seller")) or "Noma'lum"
    partner = doc.get("partner") or {}
    partner_name = partner.get("name") or partner.get("fullname") or "Noma'lum"
    partner_phone = partner.get("main_phone") or partner.get("phones") or "-"
    doc_code = doc.get("code") or f"WSL-{doc.get('id', '-')}"
    doc_date = unix_to_local(int(doc.get("date") or 0), timezone_name)
    currency = doc.get("currency") or {}
    currency_code = str(currency.get("code_chr") or "UZS")
    exchange_rate = float(doc.get("exchange_rate") or 0)
    amount = resolve_wholesale_sale_amount(doc, operations)
    previous_debt_doc_currency = _convert_base_to_doc_currency(previous_debt_base, exchange_rate, currency)
    total_debt_doc_currency = previous_debt_doc_currency + amount

    styles = _thermal_receipt_styles()
    story: list[Any] = [
        Paragraph(_escape(company_name), styles["brand"]),
    ]
    if stock_name and stock_name != "-":
        story.append(Paragraph(_escape(stock_name.upper()), styles["subtitle"]))
    story.append(Paragraph("SAVDO CHEKI", styles["title"]))

    info_rows = [
        [
            Paragraph("Kod:", styles["info_label"]),
            Paragraph(_escape(str(doc_code)), styles["info_value"]),
        ],
        [
            Paragraph("Sana:", styles["info_label"]),
            Paragraph(_escape(doc_date), styles["info_value"]),
        ],
        [
            Paragraph("Mijoz:", styles["info_label"]),
            Paragraph(_escape(partner_name), styles["info_value"]),
        ],
        [
            Paragraph("Tel:", styles["info_label"]),
            Paragraph(_escape(str(partner_phone)), styles["info_value"]),
        ],
        [
            Paragraph("Sotuvchi:", styles["info_label"]),
            Paragraph(_escape(actor_name), styles["info_value"]),
        ],
    ]
    info_table = Table(info_rows, colWidths=[15 * mm, _THERMAL_CONTENT_WIDTH - (15 * mm)])
    info_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    story.extend([info_table, Spacer(1, 2 * mm)])

    product_col_widths = [34 * mm, 8 * mm, 12 * mm, 18 * mm]
    product_header_table = Table(
        [
            [
                Paragraph("Mahsulot", styles["table_header"]),
                Paragraph("Soni", styles["table_header"]),
                Paragraph("Narxi", styles["table_header"]),
                Paragraph("Summa", styles["table_header"]),
            ]
        ],
        colWidths=[34 * mm, 8 * mm, 12 * mm, 18 * mm],
    )
    product_header_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1.2, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 1.0, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2.4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2.4),
                ("TOPPADDING", (0, 0), (-1, -1), 3.0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.0),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ]
        )
    )
    story.extend([product_header_table, Spacer(1, 0.8 * mm)])

    if operations:
        for index, op in enumerate(operations, start=1):
            item = op.get("item") or {}
            item_name = str(item.get("name") or item.get("code") or f"Item-{item.get('id', '-')}")
            quantity = float(op.get("quantity") or 0)
            price = float(op.get("price") or 0)
            row_total = quantity * price
            row_table = Table(
                [
                    [
                        Paragraph(_escape(f"{index}. {item_name}"), styles["table_item"]),
                        Paragraph(_escape(_thermal_quantity(quantity)), styles["table_qty"]),
                        Paragraph(_escape(format_money(price)), styles["table_num"]),
                        Paragraph(_escape(format_money(row_total)), styles["table_num"]),
                    ]
                ],
                colWidths=product_col_widths,
            )
            row_table.setStyle(
                TableStyle(
                    [
                        ("BOX", (0, 0), (-1, -1), 1.0, colors.black),
                        ("INNERGRID", (0, 0), (-1, -1), 0.9, colors.black),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 2.4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 2.4),
                        ("TOPPADDING", (0, 0), (-1, -1), 3.0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.0),
                        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ]
                )
            )
            story.extend([row_table, Spacer(1, 0.7 * mm)])
    else:
        empty_row_table = Table(
            [
                [
                    Paragraph("Pozitsiyalar topilmadi", styles["table_item"]),
                    Paragraph("-", styles["table_qty"]),
                    Paragraph("-", styles["table_num"]),
                    Paragraph("-", styles["table_num"]),
                ]
            ],
            colWidths=product_col_widths,
        )
        empty_row_table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 1.0, colors.black),
                    ("INNERGRID", (0, 0), (-1, -1), 0.9, colors.black),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2.4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2.4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3.0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3.0),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ]
            )
        )
        story.extend([empty_row_table, Spacer(1, 0.7 * mm)])

    story.append(Spacer(1, 2 * mm))

    summary_rows = [
        [
            Paragraph("Jami:", styles["summary_label"]),
            Paragraph(_escape(_thermal_money(amount, currency_code)), styles["summary_value"]),
        ],
        [
            Paragraph("Eski qarz:", styles["summary_label"]),
            Paragraph(_escape(_thermal_money(previous_debt_doc_currency, currency_code)), styles["summary_value"]),
        ],
        [
            Paragraph("Umumiy qarz:", styles["summary_label"]),
            Paragraph(_escape(_thermal_money(total_debt_doc_currency, currency_code)), styles["summary_value"]),
        ],
    ]
    summary_table = Table(summary_rows, colWidths=[24 * mm, _THERMAL_CONTENT_WIDTH - (24 * mm)])
    summary_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    story.append(summary_table)

    return _thermal_story_pdf(story)


def render_payment_pdf(
    *,
    payment_doc: dict[str, Any],
    previous_debt_base: float,
    current_debt_base: float,
    timezone_name: str,
) -> bytes:
    company_name = _extract_company_name(payment_doc)
    actor_name = _person_name(payment_doc.get("attached_user")) or "Noma'lum"
    partner = payment_doc.get("partner") or {}
    partner_name = partner.get("name") or partner.get("fullname") or "Noma'lum"
    partner_phone = partner.get("main_phone") or partner.get("phones") or "-"
    doc_code = payment_doc.get("code") or f"PAY-{payment_doc.get('id', '-')}"
    doc_date = unix_to_local(int(payment_doc.get("date") or 0), timezone_name)
    payment_type = payment_doc.get("type") or {}
    currency = ((payment_type.get("account") or {}).get("currency") or {})
    currency_code = str(currency.get("code_chr") or "UZS")
    exchange_rate = float(payment_doc.get("exchange_rate") or 0)
    payment_amount = float(payment_doc.get("amount") or 0)
    previous_debt_doc_currency = _convert_base_to_doc_currency(previous_debt_base, exchange_rate, currency)
    current_debt_doc_currency = _convert_base_to_doc_currency(current_debt_base, exchange_rate, currency)
    payment_type_name = str(payment_type.get("name") or "-")
    description = str(payment_doc.get("description") or "-")

    blocks: list[dict[str, Any]] = [
        _thermal_text_block(company_name, "brand"),
        _thermal_text_block("TO'LOV CHEKI", "title"),
        _thermal_separator_block(),
        _thermal_text_block(f"Kod: {doc_code}", "strong"),
        _thermal_text_block(f"Sana: {doc_date}", "body"),
        _thermal_text_block(f"Mijoz: {partner_name}", "body"),
        _thermal_text_block(f"Tel: {partner_phone}", "body"),
        _thermal_text_block(f"To'lov turi: {payment_type_name}", "body"),
        _thermal_text_block(f"Qabul qilgan: {actor_name}", "body"),
    ]
    if description and description != "-":
        blocks.append(_thermal_text_block(f"Izoh: {description}", "body"))

    blocks.extend(
        [
            _thermal_separator_block(),
            _thermal_text_block(f"To'lov: {_thermal_money(payment_amount, currency_code)}", "total"),
            _thermal_text_block(f"Oldingi qarz: {_thermal_money(previous_debt_doc_currency, currency_code)}", "strong"),
            _thermal_text_block(f"Qolgan qarz: {_thermal_money(current_debt_doc_currency, currency_code)}", "total"),
        ]
    )

    return _thermal_render_blocks(blocks)


def render_movement_pdf(
    *,
    movement_doc: dict[str, Any],
    operations: list[dict[str, Any]],
    timezone_name: str,
) -> bytes:
    _register_fonts()
    styles = _pdf_styles()

    output = BytesIO()
    pdf = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    company_name = _extract_movement_company_name(movement_doc)
    sender_name = _extract_movement_stock_name(movement_doc, "stock_sender")
    receiver_name = _extract_movement_stock_name(movement_doc, "stock_receiver")
    actor_name = _person_name(movement_doc.get("attached_user")) or "Noma'lum"
    doc_code = movement_doc.get("code") or f"MOV-{movement_doc.get('id', '-')}"
    doc_date = unix_to_local(int(movement_doc.get("date") or 0), timezone_name)
    description = str(movement_doc.get("description") or "-")

    story = []
    story.extend(
        _build_header_block(
            company_name,
            "",
            doc_code,
            doc_date,
            styles,
            title_text="PEREMISHENIYA HUJJATI",
            subtitle_text="Skladlar orasidagi ko'chirish hujjati",
        )
    )
    story.extend(
        _build_info_section(
            "PEREMISHENIYA MA'LUMOTLARI",
            [
                ("Yuboruvchi sklad", sender_name, "Qabul qiluvchi sklad", receiver_name),
                ("Amalni bajargan", actor_name, "Izoh", description),
            ],
            styles,
        )
    )
    story.extend(_build_movement_products_section(operations, styles))
    story.extend(_build_movement_summary_section(operations, styles))

    pdf.build(story)
    return output.getvalue()


def render_retail_sale_pdf(
    *,
    cheque: dict[str, Any],
    operations: list[dict[str, Any]],
    previous_debt: float,
    paid_amount: float,
    current_sale_debt: float,
    total_debt: float,
    operating_cash: dict[str, Any] | None,
    timezone_name: str,
) -> bytes:
    _register_fonts()
    styles = _pdf_styles()

    output = BytesIO()
    pdf = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    company_name = _extract_retail_company_name(operating_cash)
    actor_name = _person_name(cheque.get("seller")) or _person_name(cheque.get("cashier")) or "Noma'lum"
    customer = ((cheque.get("card") or {}).get("customer") or {})
    customer_name = _person_name(customer) or "Noma'lum"
    customer_phone = customer.get("main_phone") or customer.get("phones") or "-"
    doc_code = cheque.get("code") or f"CHQ-{cheque.get('uuid', '-')}"
    doc_date = unix_to_local(int(cheque.get("date") or 0), timezone_name)
    cash_number = _extract_operating_cash_number(operating_cash, cheque)
    cash_place = _extract_operating_cash_place(operating_cash)
    amount = float(cheque.get("amount") or 0)

    story = []
    story.extend(
        _build_header_block(
            company_name,
            "",
            doc_code,
            doc_date,
            styles,
            title_text="CHAKANA CHEK",
            subtitle_text="POS orqali yopilgan savdo cheki",
        )
    )
    story.extend(
        _build_info_section(
            "MIJOZ MA'LUMOTLARI",
            [
                ("Nomi", customer_name, "Tel", str(customer_phone)),
                ("Kassa raqami", cash_number, "Amalni bajargan", actor_name),
                ("Ombor kassasi", cash_place, "Korxona", company_name),
            ],
            styles,
        )
    )
    story.extend(_build_products_section(operations, "UZS", styles))
    story.extend(
        _build_retail_sale_summary_section(
            amount=amount,
            paid_amount=paid_amount,
            current_sale_debt=current_sale_debt,
            previous_debt=previous_debt,
            total_debt=total_debt,
            styles=styles,
        )
    )
    story.extend(_build_signatures_section(company_name, customer_name, styles))

    pdf.build(story)
    return output.getvalue()


def render_retail_payment_pdf(
    *,
    cheque: dict[str, Any],
    previous_debt: float,
    current_debt: float,
    payment_type_name: str,
    operating_cash: dict[str, Any] | None,
    timezone_name: str,
) -> bytes:
    _register_fonts()
    styles = _pdf_styles()

    output = BytesIO()
    pdf = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    company_name = _extract_retail_company_name(operating_cash)
    actor_name = _person_name(cheque.get("seller")) or _person_name(cheque.get("cashier")) or "Noma'lum"
    customer = ((cheque.get("card") or {}).get("customer") or {})
    customer_name = _person_name(customer) or "Noma'lum"
    customer_phone = customer.get("main_phone") or customer.get("phones") or "-"
    doc_code = cheque.get("code") or f"PAY-{cheque.get('uuid', '-')}"
    doc_date = unix_to_local(int(cheque.get("date") or 0), timezone_name)
    amount = float(cheque.get("amount") or 0)
    cash_number = _extract_operating_cash_number(operating_cash, cheque)
    cash_place = _extract_operating_cash_place(operating_cash)

    story = []
    story.extend(
        _build_header_block(
            company_name,
            "",
            doc_code,
            doc_date,
            styles,
            title_text="CHAKANA TO'LOV",
            subtitle_text="POS orqali qarz to'lovi cheki",
        )
    )
    story.extend(
        _build_info_section(
            "MIJOZ MA'LUMOTLARI",
            [
                ("Nomi", customer_name, "Tel", str(customer_phone)),
                ("To'lov turi", payment_type_name, "Amalni bajargan", actor_name),
                ("Kassa raqami", cash_number, "Hujjat", str(doc_code)),
                ("Ombor kassasi", cash_place, "Korxona", company_name),
            ],
            styles,
        )
    )
    story.extend(
        _build_payment_section(
            payment_amount=amount,
            currency_code="UZS",
            payment_type_name=payment_type_name,
            styles=styles,
        )
    )
    story.extend(
        _build_payment_summary_section(
            payment_amount=amount,
            previous_debt=previous_debt,
            current_debt=current_debt,
            currency_code="UZS",
            styles=styles,
        )
    )
    story.extend(_build_signatures_section(company_name, customer_name, styles))

    pdf.build(story)
    return output.getvalue()


def render_purchase_pdf(
    *,
    doc: dict[str, Any],
    operations: list[dict[str, Any]],
    timezone_name: str,
) -> bytes:
    _register_fonts()
    styles = _pdf_styles()

    output = BytesIO()
    pdf = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    company_name = _extract_company_name(doc)
    stock_name = _extract_stock_name(doc)
    actor_name = _person_name(doc.get("attached_user")) or "Noma'lum"
    partner = doc.get("partner") or {}
    partner_name = partner.get("name") or partner.get("fullname") or "Noma'lum"
    partner_phone = partner.get("main_phone") or partner.get("phones") or "-"
    doc_code = doc.get("code") or f"PUR-{doc.get('id', '-')}"
    doc_date = unix_to_local(int(doc.get("date") or 0), timezone_name)
    description = str(doc.get("description") or "-")
    currency_code = _doc_currency_code(doc)
    amount = float(doc.get("amount") or 0)
    total_quantity = sum(float(op.get("quantity") or 0) for op in operations)

    story = []
    story.extend(
        _build_header_block(
            company_name,
            stock_name,
            doc_code,
            doc_date,
            styles,
            title_text="POSTUPLENIYA HUJJATI",
            subtitle_text="Kontragentdan kelgan mahsulotlar hujjati",
        )
    )
    story.extend(
        _build_info_section(
            "POSTUPLENIYA MA'LUMOTLARI",
            [
                ("Kontragent", partner_name, "Tel", str(partner_phone)),
                ("Sklad", stock_name, "Amalni bajargan", actor_name),
                ("Izoh", description, "Korxona", company_name),
            ],
            styles,
        )
    )
    story.extend(
        _build_products_section_with_price_field(
            operations,
            currency_code,
            styles,
            price_field="cost",
        )
    )
    story.extend(
        _build_generic_summary_section(
            "HUJJAT YAKUNI",
            [
                ("Pozitsiya", f"{len(operations)} ta", "normal"),
                ("Jami soni", _format_number(total_quantity), "normal"),
                ("Hujjat summasi", _format_currency(amount, currency_code), "total"),
            ],
            styles,
        )
    )

    pdf.build(story)
    return output.getvalue()


def render_returns_to_partner_pdf(
    *,
    doc: dict[str, Any],
    operations: list[dict[str, Any]],
    timezone_name: str,
) -> bytes:
    _register_fonts()
    styles = _pdf_styles()

    output = BytesIO()
    pdf = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    company_name = _extract_company_name(doc)
    stock_name = _extract_stock_name(doc)
    actor_name = _person_name(doc.get("attached_user")) or "Noma'lum"
    partner = doc.get("partner") or {}
    partner_name = partner.get("name") or partner.get("fullname") or "Noma'lum"
    partner_phone = partner.get("main_phone") or partner.get("phones") or "-"
    doc_code = doc.get("code") or f"RTP-{doc.get('id', '-')}"
    doc_date = unix_to_local(int(doc.get("date") or 0), timezone_name)
    description = str(doc.get("description") or "-")
    currency_code = _doc_currency_code(doc)
    amount = float(doc.get("amount") or 0)
    total_quantity = sum(float(op.get("quantity") or 0) for op in operations)

    story = []
    story.extend(
        _build_header_block(
            company_name,
            stock_name,
            doc_code,
            doc_date,
            styles,
            title_text="VOZVRAT KONTAGENTGA",
            subtitle_text="Kontragentga qaytarilgan mahsulotlar hujjati",
        )
    )
    story.extend(
        _build_info_section(
            "VOZVRAT MA'LUMOTLARI",
            [
                ("Kontragent", partner_name, "Tel", str(partner_phone)),
                ("Sklad", stock_name, "Amalni bajargan", actor_name),
                ("Izoh", description, "Korxona", company_name),
            ],
            styles,
        )
    )
    story.extend(
        _build_products_section_with_price_field(
            operations,
            currency_code,
            styles,
            price_field="cost",
        )
    )
    story.extend(
        _build_generic_summary_section(
            "HUJJAT YAKUNI",
            [
                ("Pozitsiya", f"{len(operations)} ta", "normal"),
                ("Jami soni", _format_number(total_quantity), "normal"),
                ("Hujjat summasi", _format_currency(amount, currency_code), "total"),
            ],
            styles,
        )
    )

    pdf.build(story)
    return output.getvalue()


def render_wholesale_return_pdf(
    *,
    doc: dict[str, Any],
    operations: list[dict[str, Any]],
    current_debt_base: float,
    timezone_name: str,
) -> bytes:
    _register_fonts()
    styles = _pdf_styles()

    output = BytesIO()
    pdf = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    company_name = _extract_company_name(doc)
    stock_name = _extract_stock_name(doc)
    actor_name = _person_name(doc.get("attached_user")) or "Noma'lum"
    partner = doc.get("partner") or {}
    partner_name = partner.get("name") or partner.get("fullname") or "Noma'lum"
    partner_phone = partner.get("main_phone") or partner.get("phones") or "-"
    doc_code = doc.get("code") or f"WSR-{doc.get('id', '-')}"
    doc_date = unix_to_local(int(doc.get("date") or 0), timezone_name)
    currency = doc.get("currency") or {}
    currency_code = str(currency.get("code_chr") or "UZS")
    exchange_rate = float(doc.get("exchange_rate") or 0)
    amount = float(doc.get("amount") or 0)
    current_debt = _convert_base_to_doc_currency(current_debt_base, exchange_rate, currency)

    story = []
    story.extend(
        _build_header_block(
            company_name,
            stock_name,
            doc_code,
            doc_date,
            styles,
            title_text="ULGURJI VOZVRAT",
            subtitle_text="Kontragentdan qaytgan mahsulotlar hujjati",
        )
    )
    story.extend(
        _build_info_section(
            "MIJOZ MA'LUMOTLARI",
            [
                ("Nomi", partner_name, "Tel", str(partner_phone)),
                ("Ombor", stock_name, "Amalni bajargan", actor_name),
            ],
            styles,
        )
    )
    story.extend(_build_products_section(operations, currency_code, styles))
    story.extend(
        _build_generic_summary_section(
            "QARZ HOLATI",
            [
                ("Vozvrat summasi", _format_currency(amount, currency_code), "normal"),
                ("Joriy qarz", _format_currency(current_debt, currency_code), "total"),
            ],
            styles,
        )
    )
    story.extend(_build_signatures_section(company_name, partner_name, styles))

    pdf.build(story)
    return output.getvalue()


def render_wholesale_order_pdf(
    *,
    doc: dict[str, Any],
    operations: list[dict[str, Any]],
    timezone_name: str,
) -> bytes:
    _register_fonts()
    styles = _pdf_styles()

    output = BytesIO()
    pdf = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    company_name = _extract_company_name(doc)
    stock_name = _extract_stock_name(doc)
    actor_name = _person_name(doc.get("attached_user")) or "Noma'lum"
    partner = doc.get("partner") or {}
    partner_name = partner.get("name") or partner.get("fullname") or "Noma'lum"
    partner_phone = partner.get("main_phone") or partner.get("phones") or "-"
    doc_code = doc.get("code") or f"OFP-{doc.get('id', '-')}"
    doc_date = unix_to_local(int(doc.get("date") or 0), timezone_name)
    currency_code = _doc_currency_code(doc)
    amount = float(doc.get("amount") or 0)
    status_name = str((doc.get("status") or {}).get("name") or "-")
    booked_text = "Ha" if bool(doc.get("booked")) else "Yo'q"

    story = []
    story.extend(
        _build_header_block(
            company_name,
            stock_name,
            doc_code,
            doc_date,
            styles,
            title_text="ULGURJI ZAKAZ",
            subtitle_text="Kontragentdan kelgan ulgurji zakaz hujjati",
        )
    )
    story.extend(
        _build_info_section(
            "ZAKAZ MA'LUMOTLARI",
            [
                ("Mijoz", partner_name, "Tel", str(partner_phone)),
                ("Ombor", stock_name, "Amalni bajargan", actor_name),
                ("Status", status_name, "Bron", booked_text),
            ],
            styles,
        )
    )
    story.extend(_build_products_section(operations, currency_code, styles))
    story.extend(
        _build_generic_summary_section(
            "ZAKAZ YAKUNI",
            [
                ("Pozitsiya", f"{len(operations)} ta", "normal"),
                ("Status", status_name, "normal"),
                ("Zakaz summasi", _format_currency(amount, currency_code), "total"),
            ],
            styles,
        )
    )
    story.extend(_build_signatures_section(company_name, partner_name, styles))

    pdf.build(story)
    return output.getvalue()


def render_retail_return_pdf(
    *,
    cheque: dict[str, Any],
    operations: list[dict[str, Any]],
    total_debt: float,
    operating_cash: dict[str, Any] | None,
    timezone_name: str,
) -> bytes:
    _register_fonts()
    styles = _pdf_styles()

    output = BytesIO()
    pdf = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    company_name = _extract_retail_company_name(operating_cash)
    actor_name = _person_name(cheque.get("seller")) or _person_name(cheque.get("cashier")) or "Noma'lum"
    customer = ((cheque.get("card") or {}).get("customer") or {})
    customer_name = _person_name(customer) or "Noma'lum"
    customer_phone = customer.get("main_phone") or customer.get("phones") or "-"
    doc_code = cheque.get("code") or f"RET-{cheque.get('uuid', '-')}"
    doc_date = unix_to_local(int(cheque.get("date") or 0), timezone_name)
    amount = float(cheque.get("amount") or 0)
    cash_number = _extract_operating_cash_number(operating_cash, cheque)
    cash_place = _extract_operating_cash_place(operating_cash)
    return_reason = str(((cheque.get("return_reason") or {}).get("name")) or "-")

    story = []
    story.extend(
        _build_header_block(
            company_name,
            "",
            doc_code,
            doc_date,
            styles,
            title_text="CHAKANA VOZVRAT",
            subtitle_text="POS orqali qaytarilgan chek",
        )
    )
    story.extend(
        _build_info_section(
            "MIJOZ MA'LUMOTLARI",
            [
                ("Nomi", customer_name, "Tel", str(customer_phone)),
                ("Kassa raqami", cash_number, "Amalni bajargan", actor_name),
                ("Ombor kassasi", cash_place, "Sabab", return_reason),
            ],
            styles,
        )
    )
    story.extend(_build_products_section(operations, "UZS", styles))
    story.extend(
        _build_generic_summary_section(
            "MIJOZ QARZ HOLATI",
            [
                ("Vozvrat summasi", _format_currency(amount, "UZS"), "normal"),
                ("Joriy qarz", _format_currency(total_debt, "UZS"), "total"),
            ],
            styles,
        )
    )
    story.extend(_build_signatures_section(company_name, customer_name, styles))

    pdf.build(story)
    return output.getvalue()


def render_session_pdf(
    *,
    session: dict[str, Any],
    operating_cash: dict[str, Any] | None,
    opened: bool,
    timezone_name: str,
) -> bytes:
    _register_fonts()
    styles = _pdf_styles()

    output = BytesIO()
    pdf = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    company_name = _extract_retail_company_name(operating_cash)
    cash_number = _extract_operating_cash_number(operating_cash, session)
    cash_place = _extract_operating_cash_place(operating_cash)
    actor = _person_name(session.get("start_user") if opened else session.get("close_user")) or "Noma'lum"
    doc_code = session.get("code") or f"SMN-{session.get('uuid', '-')}"
    doc_date = unix_to_local(
        int((session.get("start_date") if opened else session.get("close_date")) or 0),
        timezone_name,
    )
    title_text = "SMENA OCHILDI" if opened else "SMENA YOPILDI"
    subtitle_text = "Kassadagi smena ochilish hujjati" if opened else "Kassadagi smena yopilish hujjati"
    start_amount = float(session.get("start_amount") or 0)
    close_amount = float(session.get("close_amount") or 0)
    status_text = "Ochiq" if not bool(session.get("closed")) else "Yopilgan"

    story = []
    story.extend(
        _build_header_block(
            company_name,
            "",
            doc_code,
            doc_date,
            styles,
            title_text=title_text,
            subtitle_text=subtitle_text,
        )
    )
    story.extend(
        _build_info_section(
            "SMENA MA'LUMOTLARI",
            [
                ("Smena", str(doc_code), "Kassa raqami", cash_number),
                ("Ombor kassasi", cash_place, "Amalni bajargan", actor),
                ("Holat", status_text, "Korxona", company_name),
            ],
            styles,
        )
    )
    summary_rows = [("Boshlang'ich summa", _format_currency(start_amount, "UZS"), "normal")]
    if opened:
        summary_rows.append(("Holat", "Smena ochildi", "total"))
    else:
        summary_rows.extend(
            [
                ("Yopish summasi", _format_currency(close_amount, "UZS"), "normal"),
                ("Holat", "Smena yopildi", "total"),
            ]
        )
    story.extend(_build_generic_summary_section("SMENA YAKUNI", summary_rows, styles))

    pdf.build(story)
    return output.getvalue()


def _register_fonts() -> None:
    regular_name = "RegosSans"
    bold_name = "RegosSansBold"
    if regular_name not in pdfmetrics.getRegisteredFontNames():
        regular_font, bold_font = _font_paths()
        pdfmetrics.registerFont(TTFont(regular_name, str(regular_font)))
        pdfmetrics.registerFont(TTFont(bold_name, str(bold_font)))


def _font_paths() -> tuple[Path, Path]:
    candidates = [
        (Path(r"C:\Windows\Fonts\segoeui.ttf"), Path(r"C:\Windows\Fonts\segoeuib.ttf")),
        (Path(r"C:\Windows\Fonts\arial.ttf"), Path(r"C:\Windows\Fonts\arialbd.ttf")),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
        (Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"), Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf")),
    ]
    for regular, bold in candidates:
        if regular.exists() and bold.exists():
            return regular, bold
    raise FileNotFoundError("Unicode shrift topilmadi.")


def _pdf_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "brand",
            parent=base["Normal"],
            fontName="RegosSansBold",
            fontSize=17,
            leading=20,
            textColor=colors.HexColor("#17324D"),
            spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["Normal"],
            fontName="RegosSans",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#667085"),
        ),
        "title": ParagraphStyle(
            "title",
            parent=base["Normal"],
            fontName="RegosSansBold",
            fontSize=15,
            leading=18,
            alignment=2,
            textColor=colors.HexColor("#0F172A"),
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=base["Normal"],
            fontName="RegosSans",
            fontSize=9,
            leading=12,
            alignment=2,
            textColor=colors.HexColor("#334155"),
        ),
        "section": ParagraphStyle(
            "section",
            parent=base["Normal"],
            fontName="RegosSansBold",
            fontSize=10,
            leading=13,
            textColor=colors.white,
        ),
        "label": ParagraphStyle(
            "label",
            parent=base["Normal"],
            fontName="RegosSansBold",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#334155"),
        ),
        "value": ParagraphStyle(
            "value",
            parent=base["Normal"],
            fontName="RegosSans",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#0F172A"),
        ),
        "table_header": ParagraphStyle(
            "table_header",
            parent=base["Normal"],
            fontName="RegosSansBold",
            fontSize=8.5,
            leading=11,
            textColor=colors.white,
            alignment=1,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            parent=base["Normal"],
            fontName="RegosSans",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#0F172A"),
        ),
        "table_cell_right": ParagraphStyle(
            "table_cell_right",
            parent=base["Normal"],
            fontName="RegosSans",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#0F172A"),
            alignment=2,
        ),
        "summary_label": ParagraphStyle(
            "summary_label",
            parent=base["Normal"],
            fontName="RegosSansBold",
            fontSize=9.5,
            leading=12,
            textColor=colors.HexColor("#0F172A"),
        ),
        "summary_value": ParagraphStyle(
            "summary_value",
            parent=base["Normal"],
            fontName="RegosSansBold",
            fontSize=9.5,
            leading=12,
            alignment=2,
            textColor=colors.HexColor("#0F172A"),
        ),
        "summary_total_label": ParagraphStyle(
            "summary_total_label",
            parent=base["Normal"],
            fontName="RegosSansBold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#17324D"),
        ),
        "summary_total_value": ParagraphStyle(
            "summary_total_value",
            parent=base["Normal"],
            fontName="RegosSansBold",
            fontSize=11,
            leading=14,
            alignment=2,
            textColor=colors.HexColor("#17324D"),
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="RegosSans",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#111827"),
        ),
    }


def _build_header_block(
    company_name: str,
    stock_name: str,
    doc_code: str,
    doc_date: str,
    styles: dict[str, ParagraphStyle],
    *,
    title_text: str = "SAVDO HUJJATI",
    subtitle_text: str | None = None,
) -> list[Any]:
    subtitle = subtitle_text or "Savdo hujjati"
    if subtitle_text is None and stock_name:
        subtitle = f"Savdo hujjati | {stock_name}"

    left = [
        Paragraph(_escape(company_name), styles["brand"]),
        Paragraph(_escape("Magazin savdosi bo'yicha avtomatik shakllantirilgan hujjat"), styles["subtitle"]),
        Paragraph(_escape(subtitle), styles["subtitle"]),
    ]
    right = [
        Paragraph(_escape(title_text), styles["title"]),
        Paragraph(_escape(f"Raqami: #{doc_code}"), styles["meta"]),
        Paragraph(_escape(f"Sana: {doc_date}"), styles["meta"]),
    ]

    table = Table([[left, right]], colWidths=[110 * mm, 68 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return [table, Spacer(1, 8)]


def _build_info_section(
    title: str,
    rows: list[tuple[str, str, str, str]],
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    story: list[Any] = [_section_bar(title, styles), Spacer(1, 4)]
    data = []
    for left_label, left_value, right_label, right_value in rows:
        data.append(
            [
                Paragraph(_escape(left_label), styles["label"]),
                Paragraph(_escape(left_value or "-"), styles["value"]),
                Paragraph(_escape(right_label), styles["label"]),
                Paragraph(_escape(right_value or "-"), styles["value"]),
            ]
        )
    table = Table(data, colWidths=[28 * mm, 56 * mm, 34 * mm, 60 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E2E8F0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([table, Spacer(1, 10)])
    return story


def _build_products_section(
    operations: list[dict[str, Any]],
    currency_code: str,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    story: list[Any] = [_section_bar("MAHSULOTLAR RO'YXATI", styles), Spacer(1, 4)]

    header = [
        Paragraph("#", styles["table_header"]),
        Paragraph("Mahsulot", styles["table_header"]),
        Paragraph("Soni", styles["table_header"]),
        Paragraph(_escape(f"Narx ({currency_code})"), styles["table_header"]),
        Paragraph(_escape(f"Jami ({currency_code})"), styles["table_header"]),
    ]
    rows: list[list[Any]] = [header]

    for index, op in enumerate(operations, start=1):
        item = op.get("item") or {}
        item_name = item.get("name") or item.get("code") or f"Item-{item.get('id', '-')}"
        quantity = float(op.get("quantity") or 0)
        price = float(op.get("price") or 0)
        total = quantity * price
        rows.append(
            [
                Paragraph(str(index), styles["table_cell_right"]),
                Paragraph(_escape(item_name), styles["table_cell"]),
                Paragraph(_escape(_format_number(quantity)), styles["table_cell_right"]),
                Paragraph(_escape(_format_currency_value(price)), styles["table_cell_right"]),
                Paragraph(_escape(_format_currency_value(total)), styles["table_cell_right"]),
            ]
        )

    table = Table(rows, colWidths=[12 * mm, 92 * mm, 20 * mm, 28 * mm, 28 * mm], repeatRows=1)
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#17324D")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for row_index in range(1, len(rows)):
        if row_index % 2 == 0:
            style_commands.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#F8FAFC")))
    table.setStyle(TableStyle(style_commands))
    story.extend([table, Spacer(1, 10)])
    return story


def _build_products_section_with_price_field(
    operations: list[dict[str, Any]],
    currency_code: str,
    styles: dict[str, ParagraphStyle],
    *,
    price_field: str,
    section_title: str = "MAHSULOTLAR RO'YXATI",
) -> list[Any]:
    story: list[Any] = [_section_bar(section_title, styles), Spacer(1, 4)]

    header = [
        Paragraph("#", styles["table_header"]),
        Paragraph("Mahsulot", styles["table_header"]),
        Paragraph("Soni", styles["table_header"]),
        Paragraph(_escape(f"Narx ({currency_code})"), styles["table_header"]),
        Paragraph(_escape(f"Jami ({currency_code})"), styles["table_header"]),
    ]
    rows: list[list[Any]] = [header]

    for index, op in enumerate(operations, start=1):
        item = op.get("item") or {}
        item_name = item.get("name") or item.get("code") or f"Item-{item.get('id', '-')}"
        quantity = float(op.get("quantity") or 0)
        price = float(op.get(price_field) or 0)
        total = quantity * price
        rows.append(
            [
                Paragraph(str(index), styles["table_cell_right"]),
                Paragraph(_escape(item_name), styles["table_cell"]),
                Paragraph(_escape(_format_number(quantity)), styles["table_cell_right"]),
                Paragraph(_escape(_format_currency_value(price)), styles["table_cell_right"]),
                Paragraph(_escape(_format_currency_value(total)), styles["table_cell_right"]),
            ]
        )

    table = Table(rows, colWidths=[12 * mm, 92 * mm, 20 * mm, 28 * mm, 28 * mm], repeatRows=1)
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#17324D")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for row_index in range(1, len(rows)):
        if row_index % 2 == 0:
            style_commands.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#F8FAFC")))
    table.setStyle(TableStyle(style_commands))
    story.extend([table, Spacer(1, 10)])
    return story


def _build_payment_section(
    *,
    payment_amount: float,
    currency_code: str,
    payment_type_name: str,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    story: list[Any] = [_section_bar("TO'LOV MA'LUMOTLARI", styles), Spacer(1, 4)]
    rows = [
        [
            Paragraph("To'lov turi", styles["summary_label"]),
            Paragraph(_escape(payment_type_name), styles["summary_value"]),
        ],
        [
            Paragraph("To'lov summasi", styles["summary_total_label"]),
            Paragraph(_escape(_format_currency(payment_amount, currency_code)), styles["summary_total_value"]),
        ],
    ]
    table = Table(rows, colWidths=[95 * mm, 55 * mm], hAlign="RIGHT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8FAFC")),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#DCFCE7")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E2E8F0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([table, Spacer(1, 10)])
    return story


def _build_generic_summary_section(
    title: str,
    rows: list[tuple[str, str, str]],
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    story: list[Any] = [_section_bar(title, styles), Spacer(1, 4)]
    data: list[list[Any]] = []
    style_commands = [
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E2E8F0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]

    tone_map = {
        "normal": colors.HexColor("#F8FAFC"),
        "info": colors.HexColor("#E0F2FE"),
        "success": colors.HexColor("#DCFCE7"),
        "warning": colors.HexColor("#FEF3C7"),
        "danger": colors.HexColor("#FEE2E2"),
        "total": colors.HexColor("#DBEAFE"),
    }

    for index, (label, value, tone) in enumerate(rows):
        is_total = tone == "total"
        label_style = styles["summary_total_label"] if is_total else styles["summary_label"]
        value_style = styles["summary_total_value"] if is_total else styles["summary_value"]
        data.append(
            [
                Paragraph(_escape(label), label_style),
                Paragraph(_escape(value), value_style),
            ]
        )
        style_commands.append(
            (
                "BACKGROUND",
                (0, index),
                (-1, index),
                tone_map.get(tone, tone_map["normal"]),
            )
        )

    table = Table(data, colWidths=[95 * mm, 55 * mm], hAlign="RIGHT")
    table.setStyle(TableStyle(style_commands))
    story.extend([table, Spacer(1, 10)])
    return story


def _build_summary_section(
    *,
    amount: float,
    previous_debt: float,
    total_debt: float,
    currency_code: str,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    story: list[Any] = [_section_bar("MIJOZ QARZ HOLATI", styles), Spacer(1, 4)]
    rows = [
        [
            Paragraph("Hozirgi xarid", styles["summary_label"]),
            Paragraph(_escape(f"+{_format_currency(amount, currency_code)}"), styles["summary_value"]),
        ],
        [
            Paragraph("Eski qarz", styles["summary_label"]),
            Paragraph(_escape(_format_currency(previous_debt, currency_code)), styles["summary_value"]),
        ],
        [
            Paragraph("JAMI", styles["summary_total_label"]),
            Paragraph(_escape(_format_currency(total_debt, currency_code)), styles["summary_total_value"]),
        ],
    ]
    table = Table(rows, colWidths=[95 * mm, 55 * mm], hAlign="RIGHT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -2), colors.HexColor("#F8FAFC")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E0F2FE")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E2E8F0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([table, Spacer(1, 12)])
    return story


def _build_payment_summary_section(
    *,
    payment_amount: float,
    previous_debt: float,
    current_debt: float,
    currency_code: str,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    story: list[Any] = [_section_bar("MIJOZ QARZ HOLATI", styles), Spacer(1, 4)]
    rows = [
        [
            Paragraph("To'lov", styles["summary_label"]),
            Paragraph(_escape(f"-{_format_currency(payment_amount, currency_code)}"), styles["summary_value"]),
        ],
        [
            Paragraph("Oldingi qarz", styles["summary_label"]),
            Paragraph(_escape(_format_currency(previous_debt, currency_code)), styles["summary_value"]),
        ],
        [
            Paragraph("Qolgan qarz", styles["summary_total_label"]),
            Paragraph(_escape(_format_currency(current_debt, currency_code)), styles["summary_total_value"]),
        ],
    ]
    table = Table(rows, colWidths=[95 * mm, 55 * mm], hAlign="RIGHT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -2), colors.HexColor("#F8FAFC")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E0F2FE")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E2E8F0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([table, Spacer(1, 12)])
    return story


def _build_retail_sale_summary_section(
    *,
    amount: float,
    paid_amount: float,
    current_sale_debt: float,
    previous_debt: float,
    total_debt: float,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    story: list[Any] = [_section_bar("MIJOZ QARZ HOLATI", styles), Spacer(1, 4)]
    rows = [
        [
            Paragraph("Chek summasi", styles["summary_label"]),
            Paragraph(_escape(_format_currency(amount, "UZS")), styles["summary_value"]),
        ],
        [
            Paragraph("To'langan", styles["summary_label"]),
            Paragraph(_escape(_format_currency(paid_amount, "UZS")), styles["summary_value"]),
        ],
        [
            Paragraph("Yangi qarz", styles["summary_label"]),
            Paragraph(_escape(_format_currency(current_sale_debt, "UZS")), styles["summary_value"]),
        ],
        [
            Paragraph("Eski qarz", styles["summary_label"]),
            Paragraph(_escape(_format_currency(previous_debt, "UZS")), styles["summary_value"]),
        ],
        [
            Paragraph("JAMI", styles["summary_total_label"]),
            Paragraph(_escape(_format_currency(total_debt, "UZS")), styles["summary_total_value"]),
        ],
    ]
    table = Table(rows, colWidths=[95 * mm, 55 * mm], hAlign="RIGHT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -2), colors.HexColor("#F8FAFC")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E0F2FE")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E2E8F0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([table, Spacer(1, 12)])
    return story


def _build_movement_products_section(
    operations: list[dict[str, Any]],
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    story: list[Any] = [_section_bar("MAHSULOTLAR RO'YXATI", styles), Spacer(1, 4)]

    header = [
        Paragraph("#", styles["table_header"]),
        Paragraph("Mahsulot", styles["table_header"]),
        Paragraph("Soni", styles["table_header"]),
        Paragraph("Izoh", styles["table_header"]),
    ]
    rows: list[list[Any]] = [header]

    for index, op in enumerate(operations, start=1):
        item = op.get("item") or {}
        item_name = item.get("name") or item.get("fullname") or item.get("code") or f"Item-{item.get('id', '-')}"
        quantity = float(op.get("quantity") or 0)
        description = str(op.get("description") or "-")
        rows.append(
            [
                Paragraph(str(index), styles["table_cell_right"]),
                Paragraph(_escape(item_name), styles["table_cell"]),
                Paragraph(_escape(_format_number(quantity)), styles["table_cell_right"]),
                Paragraph(_escape(description), styles["table_cell"]),
            ]
        )

    table = Table(rows, colWidths=[12 * mm, 102 * mm, 22 * mm, 42 * mm], repeatRows=1)
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#17324D")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for row_index in range(1, len(rows)):
        if row_index % 2 == 0:
            style_commands.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#F8FAFC")))
    table.setStyle(TableStyle(style_commands))
    story.extend([table, Spacer(1, 10)])
    return story


def _build_movement_summary_section(
    operations: list[dict[str, Any]],
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    total_quantity = sum(float(op.get("quantity") or 0) for op in operations)
    total_value = sum(float(op.get("quantity") or 0) * float(op.get("price") or 0) for op in operations)

    story: list[Any] = [_section_bar("QISQACHA", styles), Spacer(1, 4)]
    rows = [
        [
            Paragraph("Pozitsiyalar soni", styles["summary_label"]),
            Paragraph(_escape(str(len(operations))), styles["summary_value"]),
        ],
        [
            Paragraph("Jami birlik", styles["summary_label"]),
            Paragraph(_escape(_format_number(total_quantity)), styles["summary_value"]),
        ],
        [
            Paragraph("Umumiy qiymat", styles["summary_total_label"]),
            Paragraph(_escape(_format_currency(total_value, "UZS")), styles["summary_total_value"]),
        ],
    ]
    table = Table(rows, colWidths=[95 * mm, 55 * mm], hAlign="RIGHT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -2), colors.HexColor("#F8FAFC")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E0F2FE")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E2E8F0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([table, Spacer(1, 12)])
    return story


def _build_signatures_section(
    company_name: str,
    partner_name: str,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    story: list[Any] = [_section_bar("TASDIQLASH", styles), Spacer(1, 4)]
    left = [
        Paragraph(_escape(company_name), styles["label"]),
        Paragraph("Sotuv menejeri:", styles["value"]),
        Spacer(1, 12),
        Paragraph("__________________________", styles["value"]),
        Paragraph("imzo", styles["subtitle"]),
    ]
    right = [
        Paragraph(_escape(f"Mijoz: {partner_name}"), styles["label"]),
        Paragraph("Qabul qildi:", styles["value"]),
        Spacer(1, 12),
        Paragraph("__________________________", styles["value"]),
        Paragraph("imzo / F.I.O.", styles["subtitle"]),
    ]
    table = Table([[left, right]], colWidths=[88 * mm, 88 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E2E8F0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    story.append(table)
    return story


def _section_bar(title: str, styles: dict[str, ParagraphStyle]) -> Table:
    table = Table([[Paragraph(_escape(title), styles["section"])]], colWidths=[178 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#17324D")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _extract_company_name(doc: dict[str, Any]) -> str:
    if doc.get("firm"):
        return str((doc.get("firm") or {}).get("name") or "REGOS COMPANY")
    stock = doc.get("stock") or {}
    firm = stock.get("firm") or {}
    return str(firm.get("name") or "REGOS COMPANY")


def _extract_stock_name(doc: dict[str, Any]) -> str:
    stock = doc.get("stock") or {}
    return str(stock.get("name") or "-")


def _doc_currency_code(doc: dict[str, Any]) -> str:
    currency = doc.get("currency") or {}
    return str(currency.get("code_chr") or "UZS")


def _extract_movement_company_name(doc: dict[str, Any]) -> str:
    sender_stock = doc.get("stock_sender") or {}
    sender_firm = sender_stock.get("firm") or {}
    if sender_firm.get("name"):
        return str(sender_firm.get("name"))

    receiver_stock = doc.get("stock_receiver") or {}
    receiver_firm = receiver_stock.get("firm") or {}
    if receiver_firm.get("name"):
        return str(receiver_firm.get("name"))

    return "REGOS COMPANY"


def _brand_name() -> str:
    return str(get_settings().app_brand_name or "Chust optom No 1")


def _extract_retail_company_name(operating_cash: dict[str, Any] | None) -> str:
    operating_cash = operating_cash or {}
    stock = operating_cash.get("stock") or {}
    firm = stock.get("firm") or {}
    return str(firm.get("name") or _brand_name())


def _extract_operating_cash_number(operating_cash: dict[str, Any] | None, cheque: dict[str, Any]) -> str:
    operating_cash = operating_cash or {}
    return str(operating_cash.get("id") or cheque.get("operating_cash_id") or "-")


def _extract_operating_cash_place(operating_cash: dict[str, Any] | None) -> str:
    operating_cash = operating_cash or {}
    stock = operating_cash.get("stock") or {}
    stock_name = str(stock.get("name") or "-")
    cash_description = str(operating_cash.get("description") or "").strip()
    if cash_description:
        return f"{stock_name} / {cash_description}"
    return stock_name


def _extract_movement_stock_name(doc: dict[str, Any], field_name: str) -> str:
    stock = doc.get(field_name) or {}
    return str(stock.get("name") or stock.get("fullname") or "-")


def _convert_base_to_doc_currency(total_debt_base: float, exchange_rate: float, currency: dict[str, Any]) -> float:
    is_base = bool(currency.get("is_base"))
    if is_base or exchange_rate <= 0:
        return float(total_debt_base or 0)
    return float(total_debt_base or 0) / exchange_rate


def _format_currency(amount: float, currency_code: str) -> str:
    return f"{currency_code} {_format_currency_value(amount)}"


def _format_currency_value(amount: float) -> str:
    rounded = round(float(amount or 0), 2)
    if abs(rounded - int(rounded)) < 0.005:
        return f"{int(round(rounded))}"
    return f"{rounded:,.2f}".replace(",", " ")


def _format_number(value: float) -> str:
    rounded = round(float(value or 0), 3)
    if abs(rounded - int(rounded)) < 0.001:
        return str(int(round(rounded)))
    return f"{rounded:g}"


def _escape(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
