"""Extract copyable text from resume and JD files. Scanned pages are not OCR'd."""

from io import BytesIO
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
MAX_PAGES = 12
MAX_CHARS = 20000
TEXT_SUFFIXES = {"txt", "text", "md", "markdown"}
WORD_SUFFIXES = {"doc", "docx"}


def extract_upload(filename: str, data: bytes) -> dict:
    name = Path(filename or "未命名").name[:80]
    kind = _kind(filename, data)
    if kind not in {"pdf", "docx", "doc", "txt"}:
        return _fail(kind or "file", "请上传 PDF、Word（.docx / .doc）或 TXT。扫描件和图片请改为粘贴文字。", name)
    if len(data) > MAX_BYTES:
        return _fail(kind, "文件超过 8 MB。请换成更小的文件，或直接粘贴文字。", name)
    if not data:
        return _fail(kind, "文件是空的。请另选一份，或直接粘贴文字。", name)
    try:
        if kind == "docx":
            text, pages = read_docx(data)
        elif kind == "pdf":
            text, pages = read_pdf(data)
        elif kind == "doc":
            text, pages = read_doc(data), 0
        else:
            text, pages = read_txt(data), 0
    except Exception:  # noqa: BLE001 -- parser failures stay a fixed message, never a stack or file dump
        return _fail(kind, "没有读出文字。文件可能已加密、已损坏，或不是可复制文字。请改为粘贴。", name)
    if kind == "pdf" and pages > MAX_PAGES:
        return _fail("pdf", f"PDF 有 {pages} 页，超过 12 页上限。请拆开或改为粘贴需要的部分。", name, pages)
    text = (text or "").replace("\x00", "").strip()
    warnings = []
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
        warnings.append("文字超过 20,000 字，已保留前 20,000 字。请在预览里删掉不需要的部分。")
    if kind == "doc" and text:
        warnings.append("旧版 Word 只提取了能识别的文字，请在预览里核对。若是乱码，请另存为 .docx 或直接粘贴。")
    compact = "".join(text.split())
    if not compact or (kind == "pdf" and pages and len(compact) < 8) or (kind == "doc" and not _readable(text)):
        reason = "几乎没有可复制的文字，可能是扫描件。本程序不做扫描识别，请改为粘贴文字。" if kind == "pdf" else "没有读出可用文字。请另存为 .docx 或 TXT，或直接粘贴。"
        return {"kind": kind, "pages": pages, "text": "", "reliable": False, "warnings": [], "reason": reason, "name": name}
    return {"kind": kind, "pages": pages, "text": text, "reliable": True, "warnings": warnings, "reason": "", "name": name}


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


def read_txt(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("gb18030")


def read_doc(data: bytes) -> str:
    """Pull readable UTF-16 text out of a legacy .doc. A mislabeled .docx is read as Word XML."""
    if data.startswith(b"PK"):
        return read_docx(data)[0]
    best = ""
    for offset in (0, 1):
        runs = []
        current: list[str] = []
        index = offset
        while index + 1 < len(data):
            code = int.from_bytes(data[index:index + 2], "little")
            if _keep_char(code):
                current.append("\n" if code in (10, 13) else chr(code))
                index += 2
            else:
                _flush(current, runs)
                index += 2
        _flush(current, runs)
        text = "\n".join(runs).strip()
        if len(text) > len(best):
            best = text
    return best


def _kind(filename: str, data: bytes) -> str:
    suffix = Path(filename or "").suffix.lower().lstrip(".")
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"PK"):
        return "docx"
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1") or suffix == "doc":
        return "doc"
    if suffix == "pdf":
        return "pdf"
    if suffix == "docx":
        return "docx"
    if suffix in TEXT_SUFFIXES:
        return "txt"
    if suffix in WORD_SUFFIXES:
        return suffix
    if _looks_like_text(data[:4096]):
        return "txt"
    return suffix


def _looks_like_text(sample: bytes) -> bool:
    if not sample or b"\x00" in sample[:200]:
        return False
    try:
        text = sample.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = sample.decode("gb18030")
        except UnicodeDecodeError:
            return False
    return _readable(text)


def _keep_char(code: int) -> bool:
    return code in (9, 10, 13) or 32 <= code < 127 or 0x4E00 <= code <= 0x9FFF or 0x3000 <= code <= 0x303F


def _flush(current: list[str], runs: list[str]) -> None:
    text = "".join(current).strip()
    current.clear()
    letters = sum(1 for char in text if char.isascii() and char.isalnum() or "\u4e00" <= char <= "\u9fff")
    if letters >= 4:
        runs.append(text)


def _readable(text: str) -> bool:
    compact = "".join(text.split())
    if len(compact) < 8:
        return False
    good = sum(1 for char in compact if char.isalnum() or "\u4e00" <= char <= "\u9fff")
    return good / len(compact) >= 0.5


def _fail(kind: str, reason: str, name: str, pages: int = 0) -> dict:
    return {"kind": kind, "pages": pages, "text": "", "reliable": False, "warnings": [], "reason": reason, "name": name}
