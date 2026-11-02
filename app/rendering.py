import base64
import html
import os
import sys
from contextlib import closing
from io import BytesIO
from pathlib import Path

from app.models import ResumeContent


def font_path() -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return Path(os.environ.get("MATCH_TRAJECTORY_FONT_PATH", root / "assets" / "fonts" / "NotoSansCJKsc-Regular.otf"))


def expected_texts(content: ResumeContent) -> list[str]:
    return [value for value in [content.name, content.target_role, content.contact, content.summary,
            *[value for section in content.sections for value in [section.title, *[item.text for item in section.items]]]] if value]


def marker(demo: bool, draft: bool) -> str:
    return " · ".join(value for value in ["草稿" if draft else "", "虚构演示，不可直接投递" if demo else ""] if value)


def render_html(content: ResumeContent, demo: bool = False, draft: bool = False, font_uri: str = "/api/font") -> str:
    esc = html.escape
    notice = marker(demo, draft)
    sections = "".join(f'<section><h2>{esc(section.title)}</h2><ul>' +
                       "".join(f'<li>{esc(item.text)}</li>' for item in section.items) + "</ul></section>"
                       for section in content.sections)
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>
@font-face{{font-family:ResumeCJK;src:url("{esc(font_uri, quote=True)}")}}*{{box-sizing:border-box}}
@page{{size:A4;margin:16mm}}html,body{{margin:0;background:white;color:#17232d}}
body{{font-family:ResumeCJK,"Microsoft YaHei",sans-serif;font-size:10.5pt;line-height:1.65}}
.sheet{{width:210mm;min-height:297mm;padding:16mm;margin:auto}}h1{{font-size:23pt;margin:0 0 2mm;line-height:1.3}}
.role{{font-size:12pt;color:#1e6157;margin-bottom:2mm}}.contact{{font-size:9pt;color:#56626a;white-space:pre-wrap}}
.summary{{margin-top:4mm;white-space:pre-wrap}}h2{{font-size:11.5pt;border-bottom:1px solid #aebeb9;padding-bottom:1.5mm;margin:5mm 0 2mm}}
ul{{margin:0;padding-left:4.5mm}}li{{margin-bottom:2mm;white-space:pre-wrap;overflow-wrap:anywhere}}
.notice{{font-size:9pt;color:#8b5121;border:1px solid #d6b788;padding:2mm;margin-bottom:4mm}}
section{{break-inside:auto}}h2{{break-after:avoid}}li{{break-inside:avoid}}
@media print{{.sheet{{width:auto;min-height:0;padding:0;margin:0}}}}
</style></head><body><main class="sheet">
{f'<div class="notice">{esc(notice)}</div>' if notice else ''}<h1>{esc(content.name or '姓名待填写')}</h1>
<div class="role">{esc(content.target_role)}</div><div class="contact">{esc(content.contact)}</div>
{f'<div class="summary">{esc(content.summary)}</div>' if content.summary else ''}{sections}</main></body></html>'''


def render_docx(content: ResumeContent, demo: bool, draft: bool) -> bytes:
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Mm, Pt

    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.top_margin = section.bottom_margin = section.left_margin = section.right_margin = Mm(16)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = "Noto Sans CJK SC", Pt(10.5)
    fonts = normal.element.get_or_add_rPr().find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        normal.element.get_or_add_rPr().append(fonts)
    fonts.set(qn("w:eastAsia"), "Noto Sans CJK SC")
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.line_spacing = 1.25
    if marker(demo, draft):
        doc.add_paragraph(marker(demo, draft))
    heading = doc.add_paragraph()
    run = heading.add_run(content.name or "姓名待填写")
    run.bold, run.font.size = True, Pt(22)
    for text in (content.target_role, content.contact, content.summary):
        if text:
            doc.add_paragraph(text)
    for block in content.sections:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.keep_with_next = True
        title = paragraph.add_run(block.title)
        title.bold, title.font.size = True, Pt(12)
        for item in block.items:
            doc.add_paragraph(item.text)
    doc.core_properties.comments = "手工核对版本，未经 AI 审阅。" + marker(demo, draft)
    result = BytesIO()
    doc.save(result)
    return result.getvalue()


def render_pdf(content: ResumeContent, demo: bool, draft: bool) -> bytes:
    import pypdfium2 as pdfium
    from playwright.sync_api import sync_playwright

    path = font_path()
    if not path.is_file():
        raise RuntimeError("FONT_MISSING")
    uri = "data:font/otf;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.abort())
            page.set_content(render_html(content, demo, draft, uri), wait_until="load")
            page.evaluate("() => document.fonts.ready")
            data = page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
        finally:
            browser.close()
    with pdfium.PdfDocument(data) as pdf:
        texts = []
        for i in range(len(pdf)):
            with closing(pdf[i]) as page, closing(page.get_textpage()) as textpage:
                texts.append(textpage.get_text_range())
        actual = "".join("".join(texts).split())
        if len(pdf) > 2 or any("".join(text.split()) not in actual for text in expected_texts(content)):
            raise RuntimeError("PDF_LAYOUT")
    return data
