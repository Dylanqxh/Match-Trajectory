import json
import sys

from app.models import ResumeContent
from app.rendering import render_docx, render_pdf


def main() -> int:
    try:
        payload = json.loads(sys.stdin.buffer.read())
        content = ResumeContent.model_validate(payload["content"])
        renderer = {"docx": render_docx, "pdf": render_pdf}[payload["format"]]
        data = renderer(content, payload["demo"], payload["draft"])
        sys.stdout.buffer.write(data)
        return 0
    except Exception as error:  # noqa: BLE001 -- worker boundary must redact arbitrary library errors
        code = str(error) if str(error) in ("FONT_MISSING", "PDF_LAYOUT") else "EXPORT_ERROR"
        sys.stderr.write(code)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
