"""Real browser + real HTTP model fixture. No real model-quality claims."""
import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from contextlib import closing, contextmanager
from pathlib import Path

import httpx
import pypdfium2 as pdfium
from docx import Document
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.processes import WindowsJob


@contextmanager
def service(command, output, label):
    lines = queue.Queue()
    with (output / f"{label}.stderr.log").open("wb") as stderr, subprocess.Popen(
        command, cwd=ROOT, stdout=subprocess.PIPE, stderr=stderr, text=True, encoding="utf-8",
        env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    ) as process:
        job = WindowsJob(process) if os.name == "nt" else None
        threading.Thread(target=lambda: [lines.put(line) for line in process.stdout], daemon=True).start()
        try:
            deadline = time.monotonic() + 30
            url = None
            while time.monotonic() < deadline:
                try:
                    match = re.search(r"http://127\.0\.0\.1:\d+", lines.get(timeout=0.3))
                    if match:
                        url = match.group()
                        break
                except queue.Empty:
                    if process.poll() is not None:
                        break
            if not url:
                raise RuntimeError(f"{label} did not start; inspect local stderr log")
            yield url
        finally:
            if job:
                job.close()
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)


def run(output, executable=None):
    output.mkdir(parents=True, exist_ok=True)
    command = [str(executable)] if executable else [sys.executable, "-m", "app.cli"]
    command += ["--port", "0", "--no-browser", "--data-dir", str(output / "data")]
    with service([sys.executable, str(ROOT / "tools/local_model_fixture.py")], output, "fixture") as fixture, service(command, output, "app") as url:
        for _ in range(50):
            try:
                if httpx.get(url + "/health", trust_env=False, timeout=1).is_success:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1050})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                page.goto(url)
                expect(page.get_by_role("button", name="AI 生成简历", exact=True)).to_be_visible()
                page.get_by_role("button", name="⚙ 模型连接").click()
                page.get_by_label("供应商", exact=True).select_option("custom")
                page.get_by_label("接口地址", exact=True).fill(fixture)
                page.get_by_label("API Key", exact=True).fill("local-fixture-secret")
                page.get_by_text("高级：模型名称", exact=True).click()
                page.get_by_label("模型 ID", exact=True).fill("test-fixture-not-a-real-model")
                page.get_by_role("button", name="测试并保存到会话").click()
                expect(page.get_by_role("dialog").get_by_role("status")).to_contain_text("测试通过")
                page.get_by_role("button", name="关闭模型设置").click()
                page.get_by_label("姓名", exact=True).fill("生成测试用户")
                page.get_by_label("目标岗位", exact=True).fill("推荐算法")
                page.get_by_label("联系方式", exact=True).fill("fixture@example.com")
                material = "使用 Python 复现推荐实验，整理离线评价记录；本人只负责复现，未上线。"
                page.locator("form textarea").first.fill(material)
                page.get_by_label("确认将材料和可选 JD 发送给所选模型服务").check()
                page.get_by_role("button", name="AI 生成简历", exact=True).click()
                expect(page.get_by_role("heading", name="AI 候选简历", exact=True)).to_be_visible(timeout=20000)
                page.reload()
                expect(page.get_by_role("heading", name="AI 候选简历", exact=True)).to_be_visible()
                page.get_by_role("button", name="采用并进入编辑器", exact=True).click()
                expect(page.get_by_role("heading", name="编辑内容", exact=True)).to_be_visible()
                expect(page.get_by_test_id("writing-quality-state")).to_contain_text("达到写作检查要求")
                page.get_by_label("姓名", exact=True).fill("生成测试用户（修改）")
                expect(page.get_by_text("正文已修改，上一版写作质量结论已失效，请保存并重新审阅。", exact=True)).to_be_visible()
                expect(page.get_by_test_id("writing-quality-state")).to_have_count(0)
                page.get_by_role("button", name="保存并重新审阅", exact=True).click()
                expect(page.get_by_test_id("ai-review-state")).to_contain_text("审阅通过", timeout=20000)
                for label, filename in (("确认并导出 PDF", "resume.pdf"), ("确认并导出 Word", "resume.docx")):
                    with page.expect_download(timeout=65000) as download:
                        page.get_by_role("button", name=label, exact=True).click()
                    download.value.save_as(output / filename)
                with pdfium.PdfDocument(output / "resume.pdf") as pdf:
                    text = []
                    for index in range(len(pdf)):
                        with closing(pdf[index]) as pdf_page, closing(pdf_page.get_textpage()) as textpage:
                            text.append(textpage.get_text_range())
                    assert "生成测试用户（修改）" in "".join(text) and "未上线" in "".join(text)
                    with closing(pdf[0]) as pdf_page:
                        pdf_page.render(scale=1.2).to_pil().save(output / "pdf-page.png")
                assert material in "\n".join(p.text for p in Document(output / "resume.docx").paragraphs)
                page.get_by_role("button", name="＋ 新建简历").click()
                page.get_by_label("姓名", exact=True).fill("补问测试用户")
                page.get_by_label("联系方式", exact=True).fill("questions@example.com")
                page.get_by_label("目标岗位", exact=True).fill("产品经理")
                page.locator("form textarea").first.fill("补问场景：参与校园预约流程讨论，尚未说明个人交付。")
                page.get_by_label("确认将材料和可选 JD 发送给所选模型服务").check()
                page.get_by_role("button", name="AI 生成简历", exact=True).click()
                expect(page.get_by_role("button", name="跳过，直接生成", exact=True)).to_be_visible(timeout=20000)
                page.get_by_role("button", name="跳过，直接生成", exact=True).click()
                expect(page.get_by_role("heading", name="AI 候选简历", exact=True)).to_be_visible(timeout=20000)
                page.get_by_role("button", name="＋ 新建简历").click()
                page.get_by_label("姓名", exact=True).fill("人工核对测试用户")
                page.get_by_label("联系方式", exact=True).fill("manual@example.com")
                page.get_by_label("目标岗位", exact=True).fill("Java 后端")
                manual_material = "人工核对场景：使用 Java 完成课程查询接口，编写测试记录。"
                page.locator("form textarea").first.fill(manual_material)
                page.get_by_label("确认将材料和可选 JD 发送给所选模型服务").check()
                page.get_by_role("button", name="AI 生成简历", exact=True).click()
                page.get_by_role("button", name="采用并进入编辑器", exact=True).click(timeout=20000)
                page.get_by_role("button", name="自行核对并接管", exact=True).click()
                expect(page.get_by_role("dialog", name="核对审阅问题", exact=True)).to_be_visible()
                page.get_by_label("选择材料 e1", exact=True).check()
                page.get_by_label("核对说明", exact=True).fill("原文明确说明本人完成查询接口并编写测试记录，与当前表述一致。")
                page.get_by_label("我已核对所选原文支持当前表述", exact=True).check()
                page.get_by_role("button", name="保存人工核对结果", exact=True).click()
                expect(page.get_by_role("dialog", name="核对审阅问题", exact=True)).not_to_be_visible()
                page.once("dialog", lambda dialog: dialog.accept())
                page.get_by_role("button", name="自行核对并接管", exact=True).click()
                expect(page.get_by_test_id("ai-review-state")).to_contain_text("用户自行核对")
                with page.expect_download(timeout=65000) as download:
                    page.get_by_role("button", name="确认并导出 Word", exact=True).click()
                download.value.save_as(output / "manual-reviewed.docx")
                assert manual_material in "\n".join(p.text for p in Document(output / "manual-reviewed.docx").paragraphs)
                page.get_by_role("button", name="＋ 新建简历").click()
                assert page.get_by_label("姓名", exact=True).evaluate("e => e.required")
                assert page.get_by_label("联系方式", exact=True).evaluate("e => e.required")
                page.get_by_label("姓名", exact=True).fill("结构测试用户")
                page.get_by_label("联系方式", exact=True).fill("structure@example.com")
                page.get_by_label("目标岗位", exact=True).fill("Agent 应用开发实习")
                page.get_by_text("求职背景（可选，用于调整写法）", exact=True).click()
                page.get_by_label("求职阶段", exact=True).select_option("transition")
                page.get_by_label("有职业空窗（可选，不必说明私人原因）", exact=True).check()
                page.get_by_role("button", name="＋ 添加教育经历", exact=True).click()
                page.get_by_label("教育1学校", exact=True).fill("虚构测试学院")
                page.get_by_label("教育1学历", exact=True).fill("硕士（在读）")
                page.get_by_label("教育1专业", exact=True).fill("计算机")
                page.get_by_label("教育1开始时间", exact=True).fill("2024-09")
                page.get_by_label("教育1结束时间", exact=True).fill("至今")
                page.locator("form textarea").first.fill("结构化样例：早期查询项目2023.01—2023.06，使用 Python 完成查询接口，保留测试记录；近期检索项目2025.01—2025.06，使用 Python 完成检索实验，交付评估脚本。")
                page.get_by_label("确认将材料和可选 JD 发送给所选模型服务").check()
                page.get_by_role("button", name="AI 生成简历", exact=True).click()
                page.get_by_role("button", name="采用并进入编辑器", exact=True).click(timeout=20000)
                expect(page.get_by_role("heading", name="编辑内容", exact=True)).to_be_visible()
                expect(page.get_by_label("教育1学校", exact=True)).to_have_value("虚构测试学院")
                resume_id = page.evaluate("localStorage.getItem('mt_resume_id')")
                resume_info = page.request.get(url + f"/api/resumes/{resume_id}").json()
                job_info = page.request.get(url + f"/api/generation-jobs/{resume_info['ai']['job_id']}").json()
                assert job_info["input"]["career_stage"] == "transition" and job_info["input"]["has_career_gap"]
                assert "references/candidates/returning.md" in job_info["skill"]["resources"]
                frame = page.frame_locator('iframe[title="简历预览"]')
                expect(frame.locator("strong", has_text="评估脚本")).to_be_visible()
                preview_text = frame.locator("body").inner_text()
                assert preview_text.index("近期检索项目") < preview_text.index("早期查询项目")
                for label, filename in (("确认并导出 PDF", "structured.pdf"), ("确认并导出 Word", "structured.docx")):
                    with page.expect_download(timeout=65000) as download:
                        page.get_by_role("button", name=label, exact=True).click()
                    download.value.save_as(output / filename)
                structured_doc = Document(output / "structured.docx")
                structured_text = "\n".join(p.text for p in structured_doc.paragraphs)
                assert "虚构测试学院" in structured_text and "2024-09" in structured_text
                assert structured_text.index("近期检索项目") < structured_text.index("早期查询项目")
                assert any(r.bold and r.text == "评估脚本" for p in structured_doc.paragraphs for r in p.runs)
                with pdfium.PdfDocument(output / "structured.pdf") as pdf:
                    assert len(pdf) == 1
                    with closing(pdf[0]) as pdf_page:
                        pdf_page.render(scale=1.3).to_pil().save(output / "structured-page.png")
                page.get_by_role("button", name="＋ 新建简历").click()
                page.get_by_role("button", name="＋ 添加教育经历", exact=True).click()
                page.get_by_label("教育1学校", exact=True).fill("尚未保存的虚构学校")
                page.once("dialog", lambda dialog: dialog.dismiss())
                page.get_by_role("button", name="＋ 新建简历").click()
                expect(page.get_by_label("教育1学校", exact=True)).to_have_value("尚未保存的虚构学校")
                page.screenshot(path=str(output / "workbench.png"), full_page=True)
                assert errors == [], errors
            except Exception:
                page.screenshot(path=str(output / "failure.png"), full_page=True)
                raise
            finally:
                browser.close()
        report = {"browser_generation": "passed", "question_skip": "passed", "refresh_recovery": "passed",
                  "source_backed_manual_resolution": "passed", "education_dates_highlights": "passed", "education_only_unsaved_guard": "passed", "quality_current_version": "passed", "career_context_routing": "passed",
                  "adopt_edit_recheck": "passed", "pdf_and_docx": "passed", "javascript_errors": len(errors),
                  "frozen_executable_tested": bool(executable), "model_service": "local deterministic HTTP fixture",
                  "real_providers_tested": 0, "real_model_quality_verified": False, "clean_machine_tested": False}
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--executable", type=Path)
    args = parser.parse_args()
    run(args.output.resolve(), args.executable.resolve() if args.executable else None)
