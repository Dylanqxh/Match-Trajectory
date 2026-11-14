from io import BytesIO

from docx import Document
from fastapi.testclient import TestClient

from app.main import create_app


def _pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET\n".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >> stream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, data in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{index} 0 obj ".encode() + data + b" endobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        output += f"{offset:010d} 00000 n \n".encode()
    output += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(output)


def test_docx_and_text_pdf_upload_return_correctable_text(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        client.get("/api/session")
        document = Document()
        document.add_paragraph("使用 Java 完成查询接口。")
        buffer = BytesIO()
        document.save(buffer)
        uploaded = client.post("/api/uploads", files={"file": (
            "resume.docx", buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )})
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["reliable"] is True
        assert "查询接口" in uploaded.json()["text"]

        pdf = client.post("/api/uploads", files={"file": ("resume.pdf", _pdf("Java query service"), "application/pdf")})
        assert pdf.status_code == 200, pdf.text
        assert "Java query service" in pdf.json()["text"]
        assert pdf.json()["reliable"] is True

        empty = client.post("/api/uploads", files={"file": ("scan.pdf", _pdf(""), "application/pdf")})
        assert empty.json()["reliable"] is False
        assert "粘贴" in empty.json()["reason"]


def test_txt_legacy_doc_and_scanned_pdf_uploads(tmp_path):
    sentence = "使用 Java 完成查询接口。"
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        client.get("/api/session")
        utf8 = client.post("/api/uploads", files={"file": ("简历.txt", sentence.encode(), "text/plain")})
        assert utf8.status_code == 200, utf8.text
        assert sentence in utf8.json()["text"]
        gbk = client.post("/api/uploads", files={"file": ("resume.txt", sentence.encode("gbk"), "text/plain")})
        assert sentence in gbk.json()["text"]
        legacy = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + sentence.encode("utf-16le")
        doc = client.post("/api/uploads", files={"file": ("resume.doc", legacy, "application/msword")})
        assert doc.json()["reliable"] is True
        assert "查询接口" in doc.json()["text"]
        noise = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes([0, 1]) * 80
        rejected = client.post("/api/uploads", files={"file": ("broken.doc", noise, "application/msword")})
        assert rejected.json()["reliable"] is False
        assert rejected.json()["text"] == ""
        scanned = client.post("/api/uploads", files={"file": ("scan.pdf", _pdf(""), "application/pdf")})
        assert scanned.json()["reliable"] is False
        assert "扫描" in scanned.json()["reason"]
