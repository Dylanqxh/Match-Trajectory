from app.models import ResumeContent


def demo_content() -> ResumeContent:
    return ResumeContent.model_validate({
        "name": "陈亦宁", "target_role": "Java 后端开发", "contact": "demo@example.com · 虚构示例",
        "summary": "计算机专业应届生，使用 Java、Spring Boot 和 MySQL 完成课程项目，关注接口实现与测试。",
        "sections": [
            {"id": "education", "title": "教育背景", "items": [
                {"id": "school", "text": "海岚大学 · 计算机科学与技术本科 · 2022.09—2026.06（虚构设定）"}]},
            {"id": "projects", "title": "项目经历", "items": [
                {"id": "project-context", "text": "课程预约系统｜三人课程项目，使用 Spring Boot 与 MySQL 实现预约流程。"},
                {"id": "project-own", "text": "本人完成预约查询、取消接口与参数校验；通过数据库唯一约束限制重复预约。"},
                {"id": "project-test", "text": "编写正常、重复预约与取消场景的测试记录，并使用 Git 协作管理代码。未提供线上用户或性能收益数据。"}]},
            {"id": "skills", "title": "技能与实践", "items": [
                {"id": "skill-java", "text": "Java 基础、Spring Boot 接口开发、MySQL 基础查询；在上述课程项目中使用 Git。"}]},
        ],
    })
