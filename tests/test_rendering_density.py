from app.models import Item, ResumeContent, Section
from app.rendering import layout_density


def test_medium_long_one_page_resume_uses_balanced_density_instead_of_maximum_compression():
    content = ResumeContent(name="何明鑫", target_role="数据开发工程师", sections=[
        Section(id="projects", title="项目经历", kind="project", items=[
            Item(id=f"item-{index}", text="负责数据处理、任务调度、质量核验与交付复盘，确保结果可追踪。" * 2)
            for index in range(14)
        ])
    ])

    assert layout_density(content) == "balanced"
