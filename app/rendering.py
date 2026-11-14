import base64
import html
import os
import re
import sys
from io import BytesIO
from pathlib import Path

from app.models import ResumeContent
from app.resume_layout import (
    date_key,
    display_period,
    display_text,
    education_text,
    grouped_blocks,
    presentation_highlights,
    section_text,
    text_runs,
)


def resolve_font_path(root: Path, configured: str = "") -> Path:
    filename = "NotoSansCJKsc-Regular.otf"
    candidates = [
        *([Path(configured)] if configured else []),
        root / "assets" / "fonts" / filename,
        root.parent / ".dev-environment" / "runtimes" / "fonts" / filename,
        root / "dist" / "MatchTrajectory" / "_internal" / "assets" / "fonts" / filename,
    ]
    return next((path for path in candidates if path.is_file()), candidates[0])


def font_path() -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return resolve_font_path(root, os.environ.get("MATCH_TRAJECTORY_FONT_PATH", ""))


def expected_texts(content: ResumeContent) -> list[str]:
    values = [content.name, content.target_role, content.contact, content.summary,
              *[value for row in content.education for value in (row.school, row.degree, row.major, row.start_date, row.end_date)],
              *[value for section in content.sections for value in [section.title, section.organization, section.role,
                 section.start_date, section.end_date, *[item.text for item in section.items]]]]
    return [display_text(value) for value in values if value]


def marker(demo: bool, draft: bool) -> str:
    return " · ".join(value for value in ["草稿" if draft else "", "虚构演示，不可直接投递" if demo else ""] if value)


def layout_density(content: ResumeContent) -> str:
    body_chars = len(content.summary) + sum(len(item.text) for section in content.sections for item in section.items)
    item_count = sum(len(section.items) for section in content.sections)
    if body_chars > 1900 or item_count > 18:
        return "dense"
    if body_chars > 1100 or item_count >= 14:
        return "balanced"
    return "normal"


def dense_layout(content: ResumeContent) -> bool:
    return layout_density(content) == "dense"


def resume_fit_script() -> str:
    """One CSP-safe layout program shared by the preview and PDF renderer."""
    return r"""(() => {
  const fit = () => {
    const sheet = document.querySelector('.sheet');
    const content = document.querySelector('.resume-content');
    if (!sheet || !content) return;
    const style = getComputedStyle(sheet);
    const available = sheet.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
    const target = available * 0.965;
    const applySpacing = (amount) => {
      sheet.style.setProperty('--extra-item-gap', `${16 * amount}px`);
      sheet.style.setProperty('--extra-section-gap', `${10 * amount}px`);
      sheet.style.setProperty('--extra-heading-gap', `${5 * amount}px`);
      sheet.style.setProperty('--extra-leading', String(0.14 * amount));
      content.style.transform = '';
      return content.getBoundingClientRect().height;
    };
    const applyShrink = (scale) => {
      sheet.style.setProperty('--extra-item-gap', '0px');
      sheet.style.setProperty('--extra-section-gap', '0px');
      sheet.style.setProperty('--extra-heading-gap', '0px');
      sheet.style.setProperty('--extra-leading', '0');
      content.style.transformOrigin = 'top left';
      content.style.transform = `scale(${scale})`;
      return content.getBoundingClientRect().height;
    };
    let scale = 1;
    let amount = 0;
    const natural = applySpacing(0);
    if (natural <= target) {
      let low = 0, high = 1, best = 0;
      for (let index = 0; index < 14; index += 1) {
        const middle = (low + high) / 2;
        if (applySpacing(middle) <= target) { best = middle; low = middle; }
        else high = middle;
      }
      amount = best;
      applySpacing(best);
    } else {
      let low = 0.78, high = 1, best = 0.78;
      for (let index = 0; index < 14; index += 1) {
        const middle = (low + high) / 2;
        if (applyShrink(middle) <= target) { best = middle; low = middle; }
        else high = middle;
      }
      scale = best;
      applyShrink(best);
    }
    document.documentElement.dataset.fitScale = scale.toFixed(4);
    document.documentElement.dataset.fitSpacing = amount.toFixed(4);
    document.documentElement.dataset.fitReady = 'true';
  };
  document.fonts.ready.then(fit);
})();"""


def _section_body(section, esc, rich, show_title: bool) -> str:
    metadata = ""
    if show_title or section.organization or section.role or display_period(section):
        metadata = (f'<div class="experience-heading"><strong>{esc(section_text(section))}</strong>'
                    f'<span>{esc(display_period(section))}</span></div>')
    return metadata + '<ul>' + ''.join(f'<li>{rich(item)}</li>' for item in section.items) + '</ul>'


def render_html(
    content: ResumeContent,
    demo: bool = False,
    draft: bool = False,
    font_uri: str = "/api/font",
    fit_script_uri: str = "/resume-fit.js",
) -> str:
    esc = html.escape
    notice = marker(demo, draft)
    def rich(item):
        text = display_text(item.text)
        highlights = [display_text(phrase) for phrase in presentation_highlights(item.text, item.highlights)]
        return "".join(f"<strong>{esc(part)}</strong>" if bold else esc(part) for part, bold in text_runs(text, highlights))

    education_rows = ''.join(
        f'<div class="experience-heading"><strong>{esc(education_text(row))}</strong><span>{esc(display_period(row))}</span></div>'
        for row in sorted(content.education, key=date_key, reverse=True))
    body_blocks = []
    grouped = grouped_blocks(content.sections)
    education_extra = next((rows for label, rows in grouped if label == "教育经历"), [])
    if content.education or education_extra:
        extra = ''.join(_section_body(section, esc, rich, show_title=section.title not in ("", "教育经历")) for section in education_extra)
        education = f'<section><h2>教育经历</h2>{education_rows}{extra}</section>'
    else:
        education = ''
    for label, rows in grouped:
        if label == "教育经历":
            continue
        parts = [f'<h2>{esc(label)}</h2>']
        for section in rows:
            show_title = section.title not in ("", label)
            parts.append(_section_body(section, esc, rich, show_title=show_title or section.organization or section.role or display_period(section)))
        body_blocks.append('<section>' + ''.join(parts) + '</section>')
    sections = ''.join(body_blocks)
    density = layout_density(content)
    density_class = "" if density == "normal" else f" {density}"
    fit_script = f'<script src="{esc(fit_script_uri, quote=True)}" defer></script>' if fit_script_uri else ""
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>
@font-face{{font-family:ResumeCJK;src:url("{esc(font_uri, quote=True)}")}}*{{box-sizing:border-box}}
@page{{size:A4;margin:0}}html,body{{margin:0;background:white;color:#17232d}}
body{{font-family:ResumeCJK,"Microsoft YaHei",sans-serif;font-size:9.35pt;line-height:1.38}}
.sheet{{--extra-item-gap:0px;--extra-section-gap:0px;--extra-heading-gap:0px;--extra-leading:0;width:210mm;height:297mm;padding:8mm;margin:auto;overflow:hidden}}.resume-content{{line-height:calc(1.38 + var(--extra-leading))}}h1{{font-size:21pt;margin:0 0 1mm;line-height:1.2;letter-spacing:.3px}}
.role{{font-size:10.5pt;color:#17695e;margin-bottom:1mm}}.contact{{font-size:8.6pt;color:#56626a;white-space:pre-wrap}}
.summary{{margin-top:2mm;white-space:pre-wrap}}h2{{font-size:10.6pt;color:#17695e;border-bottom:1.2px solid #79a79f;padding-bottom:.8mm;margin:calc(3mm + var(--extra-section-gap)) 0 calc(1.2mm + var(--extra-heading-gap))}}
.experience-heading{{display:flex;justify-content:space-between;gap:4mm;margin:.5mm 0 calc(.8mm + var(--extra-heading-gap));break-after:avoid}}.experience-heading span{{white-space:nowrap;font-size:8.5pt;color:#56626a}}strong{{font-weight:700}}
ul{{margin:0;padding-left:4mm}}li{{margin-bottom:calc(.8mm + var(--extra-item-gap));white-space:pre-wrap;overflow-wrap:break-word;word-break:normal;line-break:strict;text-wrap:pretty}}
.notice{{font-size:9pt;color:#8b5121;border:1px solid #d6b788;padding:2mm;margin-bottom:4mm}}
section{{break-inside:auto;margin-top:calc(2mm + var(--extra-section-gap))}}h2{{break-after:avoid}}li{{break-inside:avoid}}
.sheet.dense{{font-size:8.85pt}}.dense .resume-content{{line-height:calc(1.3 + var(--extra-leading))}}.dense h1{{font-size:19.5pt;margin-bottom:.6mm}}
.dense .role{{font-size:9.8pt;margin-bottom:.6mm}}.dense .contact,.dense .experience-heading span{{font-size:8pt}}
.dense h2{{font-size:9.8pt;margin:calc(2mm + var(--extra-section-gap)) 0 calc(.7mm + var(--extra-heading-gap));padding-bottom:.55mm}}.dense .experience-heading{{margin:.25mm 0 calc(.45mm + var(--extra-heading-gap))}}
.dense ul{{padding-left:3.6mm}}.dense li{{margin-bottom:calc(.4mm + var(--extra-item-gap))}}.dense section{{margin-top:calc(.8mm + var(--extra-section-gap))}}
.sheet.balanced{{font-size:9.15pt}}.balanced .resume-content{{line-height:calc(1.34 + var(--extra-leading))}}.balanced h1{{font-size:20pt;margin-bottom:.8mm}}
.balanced .role{{font-size:10pt;margin-bottom:.8mm}}.balanced .contact,.balanced .experience-heading span{{font-size:8.2pt}}
.balanced h2{{font-size:10.2pt;margin:calc(2.5mm + var(--extra-section-gap)) 0 calc(1mm + var(--extra-heading-gap));padding-bottom:.65mm}}.balanced .experience-heading{{margin:.35mm 0 calc(.6mm + var(--extra-heading-gap))}}
.balanced ul{{padding-left:3.8mm}}.balanced li{{margin-bottom:calc(.58mm + var(--extra-item-gap))}}.balanced section{{margin-top:calc(1.3mm + var(--extra-section-gap))}}
@media print{{html,body{{width:210mm;height:297mm}}.sheet{{margin:0}}}}
</style></head><body><main class="sheet"><div class="resume-content">
{f'<div class="notice">{esc(notice)}</div>' if notice else ''}<h1>{esc(content.name or '姓名待填写')}</h1>
<div class="role">{esc(content.target_role)}</div><div class="contact">{esc(content.contact)}</div>
{education}{f'<div class="summary">{esc(content.summary)}</div>' if content.summary else ''}{sections}</div></main>{fit_script}</body></html>'''.replace('class="sheet"', f'class="sheet{density_class}"', 1)


def render_docx(content: ResumeContent, demo: bool, draft: bool) -> bytes:
    from docx import Document
    from docx.enum.text import WD_TAB_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Mm, Pt, RGBColor

    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    density = layout_density(content)
    dense, balanced = density == "dense", density == "balanced"
    margin = 11 if dense else 11 if balanced else 12
    section.top_margin = section.bottom_margin = section.left_margin = section.right_margin = Mm(margin)
    normal = doc.styles["Normal"]
    body_size = 9.8 if dense else 9.15 if balanced else 9.3
    normal.font.name, normal.font.size = "Noto Sans CJK SC", Pt(body_size)
    fonts = normal.element.get_or_add_rPr().find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        normal.element.get_or_add_rPr().append(fonts)
    fonts.set(qn("w:eastAsia"), "Noto Sans CJK SC")
    normal.paragraph_format.space_after = Pt(1.8 if dense else 1.6 if balanced else 2)
    normal.paragraph_format.line_spacing = 1.12 if dense else 1.08
    bullets = doc.styles["List Bullet"]
    bullets.font.name, bullets.font.size = "Noto Sans CJK SC", Pt(body_size)
    bullet_fonts = bullets.element.get_or_add_rPr().find(qn("w:rFonts"))
    if bullet_fonts is None:
        bullet_fonts = OxmlElement("w:rFonts")
        bullets.element.get_or_add_rPr().append(bullet_fonts)
    bullet_fonts.set(qn("w:eastAsia"), "Noto Sans CJK SC")
    bullets.paragraph_format.space_after = Pt(1.8 if dense else 1.6 if balanced else 2)
    bullets.paragraph_format.line_spacing = 1.12 if dense else 1.08
    if marker(demo, draft):
        doc.add_paragraph(marker(demo, draft))
    heading = doc.add_paragraph()
    run = heading.add_run(content.name or "姓名待填写")
    heading.paragraph_format.space_after = Pt(1)
    run.bold, run.font.size = True, Pt(21 if dense else 20)
    for text in (content.target_role, content.contact):
        if text:
            paragraph = doc.add_paragraph(text)
            paragraph.paragraph_format.space_after = Pt(1)
    def heading(text):
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.keep_with_next = True
        paragraph.paragraph_format.space_before = Pt(3.2 if dense else 3.2 if balanced else 4)
        paragraph.paragraph_format.space_after = Pt(1)
        title = paragraph.add_run(text)
        title.bold, title.font.size = True, Pt(10.5 if dense else 10.2 if balanced else 10.5)
        title.font.color.rgb = RGBColor(23, 105, 94)

    def dated_heading(text, dates):
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.keep_with_next = True
        paragraph.paragraph_format.space_after = Pt(1)
        paragraph.paragraph_format.tab_stops.add_tab_stop(Mm(182), WD_TAB_ALIGNMENT.RIGHT)
        paragraph.add_run(text).bold = True
        if dates:
            paragraph.add_run("\t" + dates)

    grouped = grouped_blocks(content.sections)
    education_extra = next((rows for label, rows in grouped if label == "教育经历"), [])
    if content.education or education_extra:
        heading("教育经历")
        for row in sorted(content.education, key=date_key, reverse=True):
            dated_heading(education_text(row), display_period(row))
        for block in education_extra:
            if block.title not in ("", "教育经历"):
                dated_heading(section_text(block), display_period(block))
            for item in block.items:
                paragraph = doc.add_paragraph(style="List Bullet")
                shown = display_text(item.text)
                highlights = [display_text(phrase) for phrase in presentation_highlights(item.text, item.highlights)]
                for text, bold in text_runs(shown, highlights):
                    paragraph.add_run(text).bold = bold
    if content.summary:
        doc.add_paragraph(content.summary)
    for label, rows in grouped:
        if label == "教育经历":
            continue
        heading(label)
        for block in rows:
            if block.title not in ("", label) or block.organization or block.role or display_period(block):
                dated_heading(section_text(block), display_period(block))
            for item in block.items:
                paragraph = doc.add_paragraph(style="List Bullet")
                shown = display_text(item.text)
                highlights = [display_text(phrase) for phrase in presentation_highlights(item.text, item.highlights)]
                for text, bold in text_runs(shown, highlights):
                    paragraph.add_run(text).bold = bold
    doc.core_properties.comments = "手工核对版本，未经 AI 审阅。" + marker(demo, draft)
    result = BytesIO()
    doc.save(result)
    return result.getvalue()


def pdf_page_count(data: bytes) -> int:
    """Count page dictionaries without loading a crash-prone native PDF DLL."""
    return len(re.findall(rb"/Type\s*/Page\b", data))


def render_pdf(content: ResumeContent, demo: bool, draft: bool) -> bytes:
    from playwright.sync_api import sync_playwright

    path = font_path()
    if not path.is_file():
        raise RuntimeError("FONT_MISSING")
    uri = "data:font/otf;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(render_html(content, demo, draft, uri, fit_script_uri=""), wait_until="load")
            page.evaluate("() => document.fonts.ready")
            page.add_script_tag(content=resume_fit_script())
            page.wait_for_function("document.documentElement.dataset.fitReady === 'true'")
            rendered = "".join(page.locator("body").inner_text().split())
            if any("".join(text.split()) not in rendered for text in expected_texts(content)):
                raise RuntimeError("PDF_LAYOUT")
            data = page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
        finally:
            browser.close()
    if not data.startswith(b"%PDF-") or pdf_page_count(data) != 1:
        raise RuntimeError("PDF_LAYOUT")
    return data
