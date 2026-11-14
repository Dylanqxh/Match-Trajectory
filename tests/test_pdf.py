def test_real_chinese_pdf_keeps_all_demo_text_and_can_be_read():
    import pytest

    from app.demo import demo_content
    from app.rendering import font_path, pdf_page_count, render_pdf

    if not font_path().is_file():
        pytest.skip("需要通过启动环境配置中文字体；M0 发布探针不可跳过此项")
    data = render_pdf(demo_content(), demo=True, draft=False)
    assert data.startswith(b"%PDF-")
    assert pdf_page_count(data) == 1
    assert len(data) > 10_000


def test_representative_resume_fills_one_page_without_a_large_bottom_void():
    import pypdfium2 as pdfium
    import pytest

    from app.models import Education, Item, ResumeContent, Section
    from app.rendering import font_path, render_pdf

    if not font_path().is_file():
        pytest.skip("需要中文字体")
    content = ResumeContent(
        name="候选人姓名", target_role="软件工程师", contact="candidate@example.com 13800000000",
        education=[
            Education(id="m", school="示例大学", degree="硕士", major="计算机技术", start_date="2023-09", end_date="2026-07"),
            Education(id="b", school="示例理工大学", degree="本科", major="软件工程", start_date="2019-09", end_date="2023-07"),
        ],
        sections=[
            Section(id="skills", title="专业技能", kind="skills", items=[
                Item(id=f"s{i}", text=text) for i, text in enumerate([
                    "编程基础：熟悉 Java 与 Python，能够完成模块开发、问题定位和测试记录。",
                    "数据处理：使用 SQL 完成数据核验，了解消息队列与任务调度的基本场景。",
                    "工程实践：使用 Git 管理代码，能够编写单元测试并跟进缺陷修复。",
                    "交付协作：参与需求拆解、方案讨论、联调验收与文档沉淀。",
                ])
            ]),
            Section(id="project", title="统一任务平台", kind="project", start_date="2025-01", end_date="2025-10", items=[
                Item(id=f"p{i}", text="负责需求拆解、模块实现、异常处理与联调验收，保留测试记录和上线清单。")
                for i in range(7)
            ]),
            Section(id="work1", title="示例科技有限公司 · 软件工程师", kind="work", start_date="2024-01", end_date="2024-12", items=[
                Item(id=f"w{i}", text="实现业务功能并处理输入边界，补充自动化测试、缺陷记录和交付文档。")
                for i in range(5)
            ]),
            Section(id="work2", title="示例信息有限公司 · 研发实习生", kind="work", start_date="2023-06", end_date="2023-09", items=[
                Item(id=f"i{i}", text="参与模块开发与接口联调，通过日志和测试用例定位问题并完成修复验证。")
                for i in range(4)
            ]),
            Section(id="campus", title="校园与荣誉", kind="campus", items=[
                Item(id="c1", text="完成软件工程课程设计，负责核心模块与验收材料，作品通过课程答辩。")
            ]),
        ],
    )

    data = render_pdf(content, demo=False, draft=False)
    pdf = pdfium.PdfDocument(data)
    try:
        assert len(pdf) == 1
        image = pdf[0].render(scale=1.5).to_pil().convert("L")
    finally:
        pdf.close()
    ink = image.point(lambda value: 255 if value < 245 else 0)
    bounds = ink.getbbox()
    assert bounds is not None
    fill = bounds[3] / image.height
    assert 0.93 <= fill <= 0.985


def test_font_resolution_finds_the_portable_workspace_runtime(tmp_path):
    from app.rendering import resolve_font_path

    project = tmp_path / "project"
    bundled = tmp_path / ".dev-environment" / "runtimes" / "fonts" / "NotoSansCJKsc-Regular.otf"
    bundled.parent.mkdir(parents=True)
    bundled.write_bytes(b"font")

    assert resolve_font_path(project) == bundled
