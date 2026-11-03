"""Isolated browser acceptance with a loopback fixture, never real credentials."""
import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from smoke_m1 import ROOT, service


def run(output, executable=None):
    output.mkdir(parents=True, exist_ok=True)
    command = [str(executable)] if executable else [sys.executable, '-m', 'app.cli']
    command += ['--port', '0', '--no-browser', '--data-dir', str(output / 'data')]
    with service([sys.executable, str(ROOT / 'tools/local_model_fixture.py')], output, 'fixture') as fixture, service(command, output, 'app') as url, sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1050})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            page.goto(url)
            page.get_by_role('button', name='⚙ 模型连接').click()
            page.get_by_label('供应商', exact=True).select_option('custom')
            page.get_by_label('接口地址', exact=True).fill(fixture)
            page.get_by_label('API Key', exact=True).fill('local-fixture-secret')
            page.get_by_text('高级：模型名称', exact=True).click()
            page.get_by_label('模型 ID', exact=True).fill('local-supervisor-fixture')
            page.get_by_role('button', name='测试并保存到会话').click()
            expect(page.get_by_role('dialog').get_by_role('status')).to_contain_text('测试通过')
            page.get_by_text('可选：智能修正策略', exact=True).click()
            page.get_by_role('button', name='测试工具调用（1次模型请求）', exact=True).click()
            expect(page.get_by_role('dialog').get_by_role('status')).to_contain_text('合成工具调用测试通过')
            page.get_by_role('button', name='关闭模型设置').click()
            page.get_by_label('姓名', exact=True).fill('主管流程测试')
            page.get_by_label('目标岗位', exact=True).fill('算法实习')
            page.get_by_label('联系方式', exact=True).fill('local@example.com')
            page.get_by_label('现有材料', exact=True).fill('主管测试场景。使用 Python 完成检索实验，保留评估脚本和对照记录。')
            page.get_by_text('生成选项', exact=True).click()
            page.get_by_label('启用智能修正策略（试用）', exact=True).check()
            page.get_by_label('确认将材料和可选 JD 发送给所选模型服务').check()
            page.get_by_role('button', name='AI 生成简历', exact=True).click()
            expect(page.get_by_text('候选已保存', exact=True)).to_be_visible(timeout=25000)
            rows = page.request.get(url + '/api/generation-jobs').json()
            job = page.request.get(url + '/api/generation-jobs/' + rows[0]['id']).json()
            assert job['engine'] == 'supervisor' and job['calls'] == 6, job['error']
            assert job['review']['verdict'] == 'pass'
            assert any(row['stage'] == 'supervise' for row in job['call_log'])
            page.reload()
            expect(page.get_by_text('候选已保存', exact=True)).to_be_visible()
            page.get_by_role('button', name='采用并进入编辑器', exact=True).click()
            expect(page.get_by_role('heading', name='编辑内容', exact=True)).to_be_visible()
            with page.expect_download(timeout=65000) as download:
                page.get_by_role('button', name='确认并导出 PDF', exact=True).click()
            download.value.save_as(output / 'supervisor.pdf')
            page.screenshot(path=str(output / 'workbench.png'), full_page=True)
            assert not errors, errors
        except Exception:
            page.screenshot(path=str(output / 'failure.png'), full_page=True)
            raise
        finally:
            browser.close()
    report = {'supervisor_browser': 'passed', 'native_tool_probe': 'passed', 'calls': 6,
              'refresh_and_export': 'passed', 'real_model_quality_verified': False,
              'frozen_executable_tested': bool(executable), 'clean_machine_tested': False}
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--executable', type=Path)
    args = parser.parse_args()
    run(args.output.resolve(), args.executable.resolve() if args.executable else None)
