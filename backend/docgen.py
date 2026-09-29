"""Converts a markdown-formatted AI reply into a real downloadable
document — a Word file (.docx) for the whole reply, an Excel workbook
(.xlsx) for just the tables in it, or a PowerPoint deck (.pptx) with one
slide per heading. The client-side renderMarkdown() in app.js
does equivalent parsing for on-screen HTML; this is the server-side
counterpart for an actual file, since building a .docx/.xlsx/.pptx has to
happen in Python (python-docx/openpyxl/python-pptx) — a browser can't
construct any of them on its own.

markdown_to_docx deliberately covers the same markdown subset
renderMarkdown() does (headings, bold/italic/inline-code, fenced code
blocks, bullet/numbered lists, plus basic pipe tables) rather than a full
CommonMark implementation — that's what a local model's replies actually
use.
"""

from __future__ import annotations

import io
import re

from docx import Document
from docx.shared import Pt

INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)")
HEADER_RE = re.compile(r"^(#{1,4})\s+(.*)")
UL_RE = re.compile(r"^[-*]\s+(.*)")
OL_RE = re.compile(r"^\d+\.\s+(.*)")
TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
TABLE_SEP_RE = re.compile(r"^\|[\s:|-]+\|\s*$")


def _strip_inline_markdown(text: str) -> str:
    """For headings and list items — plain text is enough there (a bold
    heading reads no differently than a plain one once it's already a
    heading), so this skips building multiple runs for them."""
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    return text


def _add_inline_runs(paragraph, text: str) -> None:
    """Splits a line on **bold**/`code`/*italic* spans and adds each as its
    own run with the right formatting, same idea as inlineMarkdown() in
    app.js but building docx runs instead of HTML."""
    for part in INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            paragraph.add_run(part[2:-2]).bold = True
        elif part.startswith("`") and part.endswith("`"):
            run = paragraph.add_run(part[1:-1])
            run.font.name = "Consolas"
        elif part.startswith("*") and part.endswith("*"):
            paragraph.add_run(part[1:-1]).italic = True
        else:
            paragraph.add_run(part)


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def markdown_to_docx(text: str, title: str | None = None) -> bytes:
    doc = Document()
    if title:
        doc.add_heading(title, level=0)

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            code_lines = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip the closing fence
            p = doc.add_paragraph()
            run = p.add_run("\n".join(code_lines))
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
            continue

        # A pipe-table: a row, then a "---|---" separator row confirms it's
        # really a table and not just a line that happens to contain "|".
        if TABLE_ROW_RE.match(line) and i + 1 < n and TABLE_SEP_RE.match(lines[i + 1].strip()):
            header_cells = _split_table_row(line)
            i += 2  # header + separator
            body_rows = []
            while i < n and TABLE_ROW_RE.match(lines[i]):
                body_rows.append(_split_table_row(lines[i]))
                i += 1
            table = doc.add_table(rows=1, cols=len(header_cells))
            table.style = "Light Grid Accent 1"
            for cell, text_ in zip(table.rows[0].cells, header_cells):
                cell.paragraphs[0].add_run(_strip_inline_markdown(text_)).bold = True
            for row_cells in body_rows:
                row = table.add_row()
                for cell, text_ in zip(row.cells, row_cells):
                    cell.text = _strip_inline_markdown(text_)
            continue

        header_match = HEADER_RE.match(line)
        ul_match = UL_RE.match(line)
        ol_match = OL_RE.match(line)

        if header_match:
            level = min(len(header_match.group(1)) + 1, 9)
            doc.add_heading(_strip_inline_markdown(header_match.group(2)), level=level)
        elif ul_match:
            _add_inline_runs(doc.add_paragraph(style="List Bullet"), ul_match.group(1))
        elif ol_match:
            _add_inline_runs(doc.add_paragraph(style="List Number"), ol_match.group(1))
        elif stripped == "":
            pass  # blank line — just a paragraph break, nothing to add
        else:
            _add_inline_runs(doc.add_paragraph(), line)
        i += 1

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def extract_markdown_tables(text: str) -> list[list[list[str]]]:
    """Finds every markdown pipe-table in `text`, each returned as rows of
    plain-text cells (row 0 is the header). Kept separate from
    markdown_to_docx's own table handling above — that one has to interleave
    tables with everything else in document order, while this only cares
    about the tables themselves, for markdown_tables_to_xlsx below."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    tables: list[list[list[str]]] = []
    i, n = 0, len(lines)
    while i < n:
        if TABLE_ROW_RE.match(lines[i]) and i + 1 < n and TABLE_SEP_RE.match(lines[i + 1].strip()):
            rows = [_split_table_row(lines[i])]
            i += 2  # header + separator
            while i < n and TABLE_ROW_RE.match(lines[i]):
                rows.append(_split_table_row(lines[i]))
                i += 1
            tables.append(rows)
        else:
            i += 1
    return tables


def markdown_tables_to_xlsx(text: str) -> bytes:
    """Exports every markdown table found in `text` to a .xlsx workbook,
    one sheet per table. Raises ValueError if there's nothing to export —
    the frontend only offers this as an option once it's already found a
    table client-side (see hasMarkdownTable() in app.js), so hitting this
    means that detection and this one disagreed, not that the user asked
    for something reasonable that's missing."""
    tables = extract_markdown_tables(text)
    if not tables:
        raise ValueError("No table found in that reply to export.")

    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    wb.remove(wb.active)  # openpyxl always creates one default sheet; replaced by the loop below
    for idx, rows in enumerate(tables, 1):
        ws = wb.create_sheet(title=f"Table {idx}" if len(tables) > 1 else "Table")
        header, *body = rows
        for col, value in enumerate(header, 1):
            ws.cell(row=1, column=col, value=_strip_inline_markdown(value)).font = Font(bold=True)
        for r, row in enumerate(body, 2):
            for col, value in enumerate(row, 1):
                ws.cell(row=r, column=col, value=_strip_inline_markdown(value))
        # A quick, good-enough auto-width — not measuring rendered pixel
        # width, just character count, so it's not pixel-perfect, but it's
        # what stands between "usable at a glance" and every column jammed
        # to Excel's ~8-character default.
        for col_idx in range(1, len(header) + 1):
            widest = max(
                (len(str(row[col_idx - 1])) for row in rows if col_idx - 1 < len(row)),
                default=10,
            )
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max(widest + 2, 10), 40)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()



# Any heading level, not just #/## — confirmed directly that a local model
# asked for "two sections, each with its own heading" answered with ###
# for both, not # or ##. Requiring a specific level to mean "new slide"
# turned that into two headings rendered as literal, un-stripped "### ..."
# bullet text instead of two clean slides. Treating every level the same
# avoids needing to guess which one a given model/prompt will reach for.
SLIDE_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)")


def _split_into_slide_sections(text: str) -> list[tuple[str | None, list[str]]]:
    """Breaks `text` at each markdown heading, any level (ignoring any
    inside a fenced code block) — each becomes one slide, titled with that
    heading; everything under it up to the next one is that slide's body."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    sections: list[tuple[str | None, list[str]]] = []
    heading: str | None = None
    body: list[str] = []
    in_code = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            body.append(line)
            continue
        match = None if in_code else SLIDE_HEADING_RE.match(line)
        if match:
            sections.append((heading, body))
            heading = _strip_inline_markdown(match.group(1))
            body = []
        else:
            body.append(line)
    sections.append((heading, body))
    return sections


def markdown_to_pptx(text: str, title: str | None = None) -> bytes:
    """Turns a markdown reply into a slide deck: each markdown heading, of
    any level, starts a new slide titled with that heading, with
    everything under it becoming bullet points (list items get their own
    indent level; everything else — including code/table lines, since neither
    translates cleanly onto a slide — becomes a plain top-level bullet). A
    reply with no headings at all becomes a single slide, titled with
    `title` if given.

    The most speculative of the three export formats: a Word doc is just
    "the reply, formatted," and a spreadsheet only ever appears when
    there's an actual table to put in it, but a good slide deck really
    wants deliberate slide breaks a local model won't reliably produce
    unless asked for by heading. This still produces something reasonable
    either way — worst case, one slide with all of it — rather than
    failing outright."""
    from pptx import Presentation

    prs = Presentation()
    layout = prs.slide_layouts[1]  # "Title and Content"

    sections = _split_into_slide_sections(text)
    # Drop a leading, heading-less section if it has nothing in it — text
    # before the first real heading that's just blank lines isn't a slide.
    if len(sections) > 1 and sections[0][0] is None and not any(l.strip() for l in sections[0][1]):
        sections = sections[1:]

    for idx, (heading, body_lines) in enumerate(sections):
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = heading or (title if idx == 0 else None) or "Slide"
        text_frame = slide.placeholders[1].text_frame
        text_frame.clear()
        wrote_first = False
        in_code = False
        for line in body_lines:
            if line.strip().startswith("```"):
                in_code = not in_code
                continue
            stripped = line.strip()
            if not stripped:
                continue
            ul_match = UL_RE.match(line)
            ol_match = OL_RE.match(line)
            if ul_match:
                content, level = ul_match.group(1), 1
            elif ol_match:
                content, level = ol_match.group(1), 1
            else:
                content, level = stripped, 0
            content = _strip_inline_markdown(content)
            if not content:
                continue
            paragraph = text_frame.paragraphs[0] if not wrote_first else text_frame.add_paragraph()
            paragraph.text = content
            paragraph.level = level
            wrote_first = True
        if not wrote_first:
            text_frame.paragraphs[0].text = "(no content)"

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
