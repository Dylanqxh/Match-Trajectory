"""Lifecycle browser regression using isolated data and a local HTTP model fixture."""
import argparse
import json
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from smoke_m1 import service


class LifecycleFixture(BaseHTTPRequestHandler):
    """Native local model protocol fixture with two independently reviewable issues."""

    def log_message(self, *_):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        system = payload["messages"][0]["content"] if len(payload["messages"]) > 1 else ""
        context = json.loads(payload["messages"][1]["content"]) if system else {}
        source = context.get("evidence", [{"text": ""}])[0]["text"]
        if "执行中删除" in source:
            time.sleep(3)
        if not system:
            result = {"ok": True}
        elif "当前阶段：plan" in system:
            result = {"decision": "draft", "selected_fact_ids": ["e1"], "focus": ["保留本人动作"]}
        elif "当前阶段：review" in system:
            issues = [{"item_id": f"item{i}", "severity": "blocking", "code": "unsupported", "message": f"问题{i}：请核对本人动作是否有原文支持"} for i in (1, 2)] if "人工核对场景" in source else []
            result = {"verdict": "blocked" if issues else "pass", "issues": issues, "quality": {
                "status": "ready", "dimensions": [{"dimension": dimension, "score": 2, "reason": "本地协议固定输出，不代表真实质量。", "item_ids": ["document"], "evidence_ids": ["e1"], "action": "keep"} for dimension in ("fit", "contribution", "evidence", "readability")], "interview_topics": [],
            }}
        else:
            result = {"sections": [{"id": "projects", "title": "项目经历", "items": [{"id": f"item{i}", "text": source, "fact_ids": ["e1"]} for i in (1, 2)]}]}
        data = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result, ensure_ascii=False)}}], "usage": {"total_tokens": 10}}, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run(output, executable=None):
    output.mkdir(parents=True, exist_ok=True)
    command = [str(executable)] if executable else [sys.executable, "-m", "app.cli"]
    command += ["--port", "0", "--no-browser", "--data-dir", str(output / "data")]
    with service([sys.executable, str(Path(__file__).resolve()), "--fixture"], output, "fixture") as fixture, service(command, output, "app") as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(url)
            page.get_by_role("button", name="⚙ 模型连接").click()
            page.get_by_label("供应商", exact=True).select_option("custom")
            page.get_by_label("接口地址", exact=True).fill(fixture)
            page.get_by_label("API Key", exact=True).fill("local-fixture-secret")
            page.get_by_text("高级：模型名称", exact=True).click()
            page.get_by_label("模型 ID", exact=True).fill("test-fixture-not-a-real-model")
            page.get_by_role("button", name="测试并保存到会话").click()
            expect(page.get_by_role("dialog").get_by_role("status")).to_contain_text("测试通过")
            page.get_by_role("button", name="关闭模型设置").click()

            def generate(name="人工核对测试用户", material="人工核对场景：使用 Java 完成课程查询接口，编写测试记录。", adopt=True):
                page.get_by_label("姓名", exact=True).fill(name)
                page.get_by_label("联系方式", exact=True).fill("lifecycle@example.com")
                page.get_by_label("目标岗位", exact=True).fill("Java 后端")
                page.get_by_label("现有材料", exact=True).fill(material)
                page.get_by_label("确认将材料和可选 JD 发送给所选模型服务").check()
                page.get_by_role("button", name="AI 生成简历", exact=True).click()
                if adopt:
                    page.get_by_role("button", name="采用并进入编辑器", exact=True).click(timeout=20000)

            generate()
            page.get_by_role("button", name="自行核对并接管", exact=True).click()
            review = page.get_by_role("dialog", name="核对审阅问题", exact=True)
            expect(review.get_by_role("button", name="内容不对，返回编辑", exact=True)).to_be_visible()
            expect(review.get_by_role("button", name="不确定，先下载 Word 草稿", exact=True)).to_be_visible()
            review.get_by_role("button", name="内容不对，返回编辑", exact=True).click()
            expect(review).not_to_be_visible()
            expect(page.locator(".editor-panel textarea:focus")).to_have_count(1)
            page.get_by_role("button", name="自行核对并接管", exact=True).click()
            with page.expect_download() as download:
                review.get_by_role("button", name="不确定，先下载 Word 草稿", exact=True).click()
            download.value.save_as(output / "uncertain-draft.docx")
            expect(page.get_by_test_id("ai-review-state")).not_to_contain_text("用户自行核对")
            page.get_by_role("button", name="自行核对并接管", exact=True).click()
            for index in (1, 2):
                expect(review).to_contain_text(f"问题{index}：")
                review.get_by_label("选择材料 e1", exact=True).check()
                review.get_by_label("核对说明", exact=True).fill("原文明确说明本人完成查询接口并编写测试记录，与当前表述一致。")
                review.get_by_label("我已核对所选原文支持当前表述", exact=True).check()
                if index == 2:
                    page.once("dialog", lambda dialog: dialog.accept())
                review.get_by_role("button", name="保存人工核对结果", exact=True).click()
            expect(page.get_by_test_id("ai-review-state")).to_contain_text("用户自行核对")
            with page.expect_download() as download:
                page.get_by_role("button", name="确认并导出 Word", exact=True).click()
            download.value.save_as(output / "manual-final.docx")
            resume_id = page.evaluate("localStorage.getItem('mt_resume_id')")
            job_id = page.request.get(url + f"/api/resumes/{resume_id}").json()["ai"]["job_id"]
            page.once("dialog", lambda dialog: dialog.dismiss())
            page.get_by_role("button", name="删除生成任务 Java 后端", exact=True).click()
            expect(page.get_by_role("button", name="删除生成任务 Java 后端", exact=True)).to_have_count(1)
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="删除生成任务 Java 后端", exact=True).click()
            expect(page.get_by_role("button", name="删除生成任务 Java 后端", exact=True)).to_have_count(0)
            assert page.request.get(url + f"/api/generation-jobs/{job_id}").status == 404
            retained = page.request.get(url + f"/api/resumes/{resume_id}/evidence")
            assert retained.status == 200 and retained.json()["evidence"][0]["id"] == "e1"
            page.reload()
            expect(page.get_by_role("heading", name="编辑内容", exact=True)).to_be_visible()
            # Hold DELETE to reproduce a stale callback clearing a newly opened form.
            held_deletes = []

            def hold_delete(route):
                if route.request.method == "DELETE":
                    held_deletes.append(route)
                else:
                    route.continue_()

            delete_url = url + f"/api/resumes/{resume_id}"
            page.route(delete_url, hold_delete)
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="删除简历 人工核对测试用户", exact=True).click()
            expect(page.get_by_role("button", name="＋ 新建简历", exact=True)).to_be_disabled()
            expect(page.get_by_label("姓名", exact=True)).to_be_disabled()
            expect(page.get_by_role("button", name="先下载 Word 草稿", exact=True)).to_be_disabled()
            assert held_deletes, "DELETE must remain pending while the interaction lock is checked"
            page.get_by_role("button", name="＋ 新建简历", exact=True).evaluate("button => button.click()")
            expect(page.get_by_role("heading", name="编辑内容", exact=True)).to_be_visible()
            held_deletes.pop().continue_()
            page.unroute(delete_url, hold_delete)
            expect(page.get_by_role("heading", name="编辑内容", exact=True)).to_have_count(0)
            assert page.evaluate("localStorage.getItem('mt_resume_id')") is None
            assert page.request.get(url + f"/api/resumes/{resume_id}").status == 404
            page.reload()
            expect(page.get_by_role("button", name="删除简历 人工核对测试用户", exact=True)).to_have_count(0)

            # A record with no blocking issues still requires explicit acknowledgement.
            generate("无阻断测试用户", "使用 Java 完成查询接口，保留测试记录。")
            page.once("dialog", lambda dialog: dialog.dismiss())
            page.get_by_role("button", name="自行核对并接管", exact=True).click()
            expect(page.get_by_test_id("ai-review-state")).not_to_contain_text("用户自行核对")
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="自行核对并接管", exact=True).click()
            expect(page.get_by_test_id("ai-review-state")).to_contain_text("用户自行核对")
            page.get_by_label("姓名", exact=True).fill("尚未保存的名字")
            page.once("dialog", lambda dialog: dialog.dismiss())
            page.get_by_role("button", name="删除简历 无阻断测试用户", exact=True).click()
            expect(page.get_by_label("姓名", exact=True)).to_have_value("尚未保存的名字")
            page.get_by_role("button", name="保存修改", exact=True).click()
            expect(page.get_by_role("button", name="保存修改", exact=True)).to_be_disabled()
            page.get_by_role("button", name="＋ 新建简历", exact=True).click()
            # Deleting an unselected resume must fetch its current revision.
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="删除简历 尚未保存的名字", exact=True).click()
            expect(page.get_by_role("button", name="删除简历 尚未保存的名字", exact=True)).to_have_count(0)
            generate("执行中任务测试", "执行中删除：使用 Java 完成查询接口，保留测试记录。", adopt=False)
            expect(page.get_by_role("button", name="取消任务", exact=True)).to_be_visible(timeout=10000)
            running_id = page.evaluate("localStorage.getItem('mt_job_id')")
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="删除生成任务 Java 后端", exact=True).click()
            expect(page.get_by_role("region", name="AI 生成任务", exact=True)).to_have_count(0)
            assert page.evaluate("localStorage.getItem('mt_job_id')") is None
            assert page.request.get(url + f"/api/generation-jobs/{running_id}").status == 404
            page.reload()
            expect(page.get_by_role("button", name="删除生成任务 Java 后端", exact=True)).to_have_count(0)
            assert not errors, errors
            page.screenshot(path=str(output / "lifecycle.png"), full_page=True)
        except Exception:
            page.screenshot(path=str(output / "failure.png"), full_page=True)
            raise
        finally:
            browser.close()
    report = {"manual_edit_and_draft_exits": "passed", "two_issues_auto_advance": "passed", "resolve_takeover_export": "passed", "no_blocker_acknowledgement": "passed", "dirty_delete_guard": "passed", "delete_interaction_lock": "passed", "delete_unselected_resume": "passed", "delete_running_job": "passed", "delete_adopted_source_and_resume": "passed", "refresh_no_resurrection": "passed", "javascript_errors": errors, "real_providers_tested": 0, "frozen_executable_tested": bool(executable)}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--fixture", action="store_true")
    args = parser.parse_args()
    if args.fixture:
        server = ThreadingHTTPServer(("127.0.0.1", 0), LifecycleFixture)
        print(f"http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()
    else:
        run(args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="mt-lifecycle-")), args.executable.resolve() if args.executable else None)
