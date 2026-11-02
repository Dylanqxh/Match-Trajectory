"""Exercise a real local service, browser, PDF and DOCX using fictional inputs."""
import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from contextlib import closing
from pathlib import Path

import httpx
import pypdfium2 as pdfium
from docx import Document
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.processes import WindowsJob


def run(output: Path, executable: Path | None):
    output.mkdir(parents=True, exist_ok=True)
    command = [str(executable)] if executable else [sys.executable, "-m", "app.cli"]
    command += ["--port", "0", "--no-browser", "--data-dir", str(output / "data")]
    lines = queue.Queue()
    errors = []
    with subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          encoding="utf-8", env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0) as process:
        job = WindowsJob(process) if os.name == "nt" else None
        threading.Thread(target=lambda: [lines.put(line) for line in process.stdout], daemon=True).start()
        threading.Thread(target=lambda: errors.extend(process.stderr.readlines()), daemon=True).start()
        try:
            deadline = time.monotonic() + 30
            url = None
            while time.monotonic() < deadline:
                try:
                    line = lines.get(timeout=0.5)
                    match = re.search(r"http://127\.0\.0\.1:\d+", line)
                    if match:
                        url = match.group(0)
                        break
                except queue.Empty:
                    if process.poll() is not None:
                        break
            if not url:
                raise RuntimeError("Service did not start: " + "".join(errors)[-1500:])
            while time.monotonic() < deadline:
                try:
                    if httpx.get(url + "/health", timeout=1, trust_env=False).is_success:
                        break
                except httpx.HTTPError:
                    time.sleep(0.2)
            assert httpx.get(url + "/api/resumes", trust_env=False).status_code == 401
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
                    page_errors = []
                    page.on("pageerror", lambda error: page_errors.append(str(error)))
                    page.goto(url)
                    expect(page.get_by_role("heading", name="简历工作台", exact=True)).to_be_visible()
                    expect(page.get_by_role("button", name="＋ 新建简历")).to_be_enabled()
                    material = "未保存的真实输入线索，不应因切换被清空"
                    page.get_by_label("现有材料", exact=True).fill(material)
                    dialogs = []

                    def keep_material(dialog):
                        dialogs.append(dialog.message)
                        dialog.dismiss()

                    page.on("dialog", keep_material)
                    page.get_by_role("button", name="＋ 新建简历").click()
                    assert page.get_by_label("现有材料", exact=True).input_value() == material
                    assert len(dialogs) == 1
                    page.get_by_role("button", name="先用虚构示例体验 →").click()
                    assert page.get_by_label("现有材料", exact=True).input_value() == material
                    assert len(dialogs) == 2
                    assert page.evaluate("""() => {
                        const event = new Event('beforeunload', { cancelable: true });
                        window.dispatchEvent(event); return event.defaultPrevented;
                    }""") is True
                    page.remove_listener("dialog", keep_material)
                    page.get_by_label("现有材料", exact=True).fill("")
                    page.get_by_role("button", name="先用虚构示例体验 →").click()
                    expect(page.get_by_role("heading", name="编辑内容")).to_be_visible()
                    page.get_by_label("姓名", exact=True).fill("陈亦宁（演示修改）")
                    page.get_by_role("button", name="保存修改", exact=True).click()
                    expect(page.get_by_role("status")).to_have_text("已保存版本 2")
                    page.reload()
                    expect(page.get_by_label("姓名", exact=True)).to_have_value("陈亦宁（演示修改）")
                    with page.expect_download(timeout=65000) as downloaded:
                        page.get_by_role("button", name="确认并导出 PDF", exact=True).click()
                    pdf_path = output / "demo-resume.pdf"
                    downloaded.value.save_as(pdf_path)
                    with page.expect_download(timeout=65000) as downloaded:
                        page.get_by_role("button", name="确认并导出 Word", exact=True).click()
                    docx_path = output / "demo-resume.docx"
                    downloaded.value.save_as(docx_path)
                    with pdfium.PdfDocument(pdf_path) as pdf:
                        text = ""
                        for index in range(len(pdf)):
                            with closing(pdf[index]) as pdf_page, closing(pdf_page.get_textpage()) as textpage:
                                text += textpage.get_text_range()
                        assert "陈亦宁（演示修改）" in text and "虚构演示" in text
                        assert len(pdf) <= 2
                        pdf[0].render(scale=1.3).to_pil().save(output / "pdf-page.png")
                    docx_text = "\n".join(p.text for p in Document(docx_path).paragraphs)
                    assert "陈亦宁（演示修改）" in docx_text and "虚构演示" in docx_text
                    page.evaluate("window.scrollTo(0, 0)")
                    page.screenshot(path=str(output / "workbench.png"), full_page=True)
                    page.get_by_role("button", name="⚙ 模型连接").click()
                    expect(page.get_by_role("dialog", name="模型连接")).to_be_visible()
                    page.get_by_role("button", name="关闭模型设置").click()
                    page.get_by_role("button", name="＋ 新建简历").click()
                    page.get_by_label("姓名", exact=True).fill("测试用户")
                    page.get_by_label("目标岗位", exact=True).fill("产品经理")
                    page.get_by_label("联系方式", exact=True).fill("test@example.com")
                    page.get_by_label("现有材料", exact=True).fill("校园预约项目：整理同学反馈，画出预约流程草图。\n本人编写需求说明，并与同学核对方案；未提供上线收益。")
                    page.get_by_role("button", name="进入编辑器 →").click()
                    expect(page.get_by_role("heading", name="编辑内容")).to_be_visible()
                    with page.expect_download(timeout=65000) as downloaded:
                        page.get_by_role("button", name="确认并导出 Word", exact=True).click()
                    downloaded.value.save_as(output / "manual-resume.docx")
                    manual = "\n".join(p.text for p in Document(output / "manual-resume.docx").paragraphs)
                    assert "校园预约项目" in manual and "未提供上线收益" in manual and "虚构演示" not in manual
                    assert page_errors == [], page_errors
                except Exception:
                    page.screenshot(path=str(output / "failure.png"), full_page=True)
                    alerts = page.get_by_role("alert").all_text_contents()
                    (output / "failure.json").write_text(json.dumps({"alerts": alerts, "page_errors": page_errors}, ensure_ascii=False), encoding="utf-8")
                    raise
                finally:
                    browser.close()
            report = {"service": "passed", "unsaved_material_guard": "passed", "browser_edit_reload": "passed", "pdf_chinese_text": "passed",
                      "docx_editable_text": "passed", "manual_material_flow": "passed", "private_api_session": "passed",
                      "javascript_errors": 0, "frozen_executable_tested": bool(executable),
                      "clean_machine_tested": False, "live_model_providers_tested": 0}
            (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False))
        finally:
            if job:
                job.close()
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--executable", type=Path)
    args = parser.parse_args()
    run(args.output.resolve(), args.executable.resolve() if args.executable else None)
