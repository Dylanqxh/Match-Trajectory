"""Extract copyable text from a DOCX or text PDF. Scanned pages are not OCR'd."""

from io import BytesIO
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
MAX_PAGES = 12
MAX_CHARS = 20000


def extract_upload(filename: str, data: bytes) -> dict:
    kind = Path(filename or "").suffix.lower().lstrip(".")
    if kind not in ("docx", "pdf"):
        return _fail(kind, "只支持 DOCX 和可复制文字的 PDF。扫描件、图片和旧版 DOC 请改为粘贴文字。")
    if len(data) > MAX_BYTES:
        return _fail(kind, "文件超过 8 MB。请换成更小的文件，或直接粘贴文字。")
    try:
        text, pages = read_docx(data) if kind == "docx" else read_pdf(data)
    except Exception:  # noqa: BLE001 -- parser failures stay a fixed message, never a stack or file dump
        return _fail(kind, "没有读出文字。文件可能已加密、已损坏，或不是可复制文字。请改为粘贴。")
    if kind == "pdf" and pages > MAX_PAGES:
        return _fail("pdf", f"PDF 有 {pages} 页，超过 12 页上限。请拆开或改为粘贴需要的部分。", pages=pages)
    text = (text or "").strip()
    warnings = []
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
        warnings.append("文字超过 20,000 字，已保留前 20,000 字。请在预览里删掉不需要的部分。")
    compact = "".join(text.split())
    if not compact or (kind == "pdf" and pages and len(compact) < 8):
        return {"kind": kind, "pages": pages, "text": text, "reliable": False, "warnings": warnings,
                "reason": "几乎没有可复制的文字，可能是扫描件。本程序不做扫描识别，请改为粘贴文字。"}
    return {"kind": kind, "pages": pages, "text": text, "reliable": True, "warnings": warnings, "reason": ""}


def read_docx(data: bytes) -> tuple[str, int]:
    from docx import Document

    document = Document(BytesIO(data))
    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(dict.fromkeys(cells)))
    return "\n".join(parts), 0


def read_pdf(data: bytes) -> tuple[str, int]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        pages = len(pdf)
        if pages > MAX_PAGES:
            return "", pages
        texts = []
        for index in range(pages):
            page = pdf[index]
            try:
                textpage = page.get_textpage()
                try:
                    texts.append(textpage.get_text_range() or "")
                finally:
                    textpage.close()
            finally:
                page.close()
        return "\n".join(texts), pages
    finally:
        pdf.close()


def _fail(kind: str, reason: str, pages: int = 0) -> dict:
    return {"kind": kind, "pages": pages, "text": "", "reliable": False, "warnings": [], "reason": reason}
