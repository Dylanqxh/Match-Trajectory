"""Program gates for the five-block resume checklist."""
import asyncio
from pathlib import Path

import pytest
from test_skill import make_draft

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE1 = (FIXTURES / "sample1_source.txt").read_text(encoding="utf-8")
SAMPLE3 = (FIXTURES / "sample3_source.txt").read_text(encoding="utf-8")
JD = "熟练使用 MySQL 与 SQL。有计算机竞赛获奖者优先。"


def _job(source, *, contact="", education=None, answers="", mode="generate", career_stage="unspecified"):
    return {"mode": mode, "input": {"source_text": source, "contact": contact, "education": education or [],
                                     "career_stage": career_stage, "jd": JD},
            "answer_context": [{"question": "实习多久？", "answer": answers}] if answers else []}


def test_five_block_labels_hide_empty_blocks_and_fold_acm_into_honors():
    from io import BytesIO

    from docx import Document

    from app.models import Item, ResumeContent, Section
    from app.rendering import render_docx, render_html

    content = ResumeContent(name="虚构·宋知远", contact="campus-be-001@example.invalid", target_role="后端研发工程师",
                            sections=[
                                Section(id="acm", title="校 ACM 集训队", kind="other", items=[Item(id="a", text="省赛铜奖")]),
                                Section(id="book", title="校园二手书", kind="project", items=[Item(id="b", text="完成订单接口")]),
                                Section(id="empty-work", title="实习", kind="work", items=[]),
                                Section(id="legacy", title="旧简历", kind="other", items=[Item(id="c", text="保留原文")]),
                            ])
    html = render_html(content)
    assert "<h2>校园与荣誉</h2>" in html
    assert "<h2>校 ACM 集训队</h2>" not in html
    assert "<h2>项目</h2>" in html
    assert "<h2>工作 / 实习经历</h2>" not in html
    assert "旧简历" in html
    doc = "\n".join(p.text for p in Document(BytesIO(render_docx(content, False, False))).paragraphs)
    assert "校园与荣誉" in doc and "工作 / 实习经历" not in doc and "保留原文" in doc


def test_stronger_project_outranks_a_later_weaker_one_and_dates_stay_put():
    from app.models import Item, Section
    from app.resume_layout import arrange_draft_sections, arrange_sections

    rows = [Section(id="seat", title="图书馆座位预约", kind="project", start_date="2025-10", end_date="2026-01",
                    items=[Item(id="s", text="用 Spring 定时任务做了 2 周试运行。")]),
            Section(id="book", title="校园二手书", kind="project", start_date="2025-03", end_date="2025-06",
                    items=[Item(id="b", text="用 MySQL 做行锁校验，获评优秀，12 条单元测试。")])]
    assert [row.id for row in arrange_sections(rows, JD)] == ["book", "seat"]
    arranged = arrange_draft_sections([
        {"id": "acm", "title": "校 ACM 集训队", "kind": "other", "items": [{"text": "铜奖"}]},
        {"id": "book", "title": "校园二手书", "kind": "project", "end_date": "2025-06", "items": [{"text": "获评优秀"}]},
    ], JD)
    assert arranged[0]["kind"] == "project" and arranged[1]["kind"] == "campus"
    assert arranged[0]["end_date"] == "2025-06"


def test_status_upgrade_and_tech_expansion_stay_blocking_while_omission_is_allowed():
    from app.skill import build_evidence, validate_draft

    trial = build_evidence("社团组织 2 周试运行，覆盖一层自习区，未正式推广。")
    assert any(issue.code == "conflict" and issue.severity == "blocking"
               for issue in validate_draft(make_draft("上线座位预约系统，服务全校学生。"), trial))
    assert not validate_draft(make_draft("社团组织 2 周试运行，覆盖一层自习区。"), trial)
    spring = build_evidence("用 Spring 定时任务释放座位。")
    assert any("Spring Boot" in issue.message for issue in validate_draft(make_draft("用 Spring Boot 实现定时任务。"), spring))
    both = build_evidence("订单接口使用 Spring Boot，座位任务使用 Spring 定时任务。")
    assert not any("Spring Boot" in issue.message for issue in validate_draft(make_draft("订单接口使用 Spring Boot。"), both))
    scope = build_evidence("座位项目使用 Spring 定时任务。")
    assert any(issue.code == "unsupported" for issue in validate_draft(make_draft("Spring 用于两个项目。"), scope))
    docker = build_evidence("了解 Docker，只在课程实验里跑过官方镜像。")
    assert any(issue.code == "attribution" and issue.severity == "blocking"
               for issue in validate_draft(make_draft("熟悉 Docker。"), docker))
    java = build_evidence("熟悉 Java，完成查询接口。")
    assert not any(issue.code == "attribution" for issue in validate_draft(make_draft("熟悉 Java，完成查询接口。"), java))


def test_sample1_keeps_strong_results_drops_negative_lines_and_orders_projects():
    from app.gates import gate_warnings
    from app.generation_models import Draft

    thin = Draft.model_validate({"sections": [
        {"id": "seat", "title": "图书馆座位预约", "kind": "project", "end_date": "2026-01", "items": [
            {"id": "s1", "text": "试运行结束后因学校统一系统上线而停止，未正式推广。课程结束后已下线。", "fact_ids": ["e1"]}]},
        {"id": "book", "title": "校园二手书", "kind": "project", "end_date": "2025-06", "items": [
            {"id": "b1", "text": "前端与支付模拟由其他组员完成。", "fact_ids": ["e1"]}]},
    ]})
    warnings = gate_warnings(_job(SAMPLE1), thin)
    messages = " ".join(issue.message for issue in warnings)
    assert "优秀" in messages and "铜奖" in messages
    assert any("省略" in issue.message for issue in warnings)
    assert all(issue.severity == "warning" for issue in warnings)
    kept = Draft.model_validate({"sections": [
        {"id": "skills", "title": "专业技能", "kind": "skills", "items": [
            {"id": "sk", "text": "Java 与 MySQL：课程和订单项目中使用。Redis 基础用法。了解 Docker 的范围不写入正文。", "fact_ids": ["e1"]}]},
        {"id": "book", "title": "校园二手书交易平台", "kind": "project", "start_date": "2025-03", "end_date": "2025-06", "items": [
            {"id": "b1", "text": "小组课程验收获评优秀，全班 9 组中 2 组。", "fact_ids": ["e1"]}]},
        {"id": "seat", "title": "图书馆座位预约", "kind": "project", "start_date": "2025-10", "end_date": "2026-01", "items": [
            {"id": "s1", "text": "社团组织 2 周试运行，覆盖图书馆一层自习区。", "fact_ids": ["e1"]}]},
        {"id": "honor", "title": "校园与荣誉", "kind": "campus", "items": [
            {"id": "h1", "text": "校 ACM 集训队队员，省赛铜奖。", "fact_ids": ["e1"]}]},
    ]})
    assert not any(issue.repair_action == "revise" for issue in gate_warnings(_job(SAMPLE1, career_stage="entry"), kept))


def test_user_school_wins_with_one_warning_and_empty_contact_rejects_inventions():
    from app.gates import blocking_gates, gate_warnings, header_contact
    from app.generation_models import Draft

    source = "就读江城示例理工大学。使用 Java 完成查询接口。"
    draft = Draft.model_validate({"education": [{"id": "edu1", "school": "江城大学", "degree": "本科", "major": "软件工程", "fact_ids": ["e1"]}],
                                  "sections": [{"id": "p", "title": "查询", "kind": "project", "items": [
                                      {"id": "i", "text": "使用 Java 完成查询接口。", "fact_ids": ["e1"]}]}]})
    user = _job(source, contact="18800001111", education=[{"school": "江城大学"}])
    assert blocking_gates(user, draft) == []
    warnings = gate_warnings(user, draft)
    assert len(warnings) == 1 and warnings[0].severity == "warning" and warnings[0].repair_action is None
    assert "江城大学" in warnings[0].message and "江城示例理工大学" in warnings[0].message

    invented = Draft.model_validate({"sections": [{"id": "p", "title": "查询", "kind": "project", "items": [
        {"id": "i", "text": "请联系 18878765786 或 fake@example.com。", "fact_ids": ["e1"]}]}]})
    blocked = blocking_gates(_job("使用 Java 完成查询接口。", contact=""), invented)
    assert any(issue.severity == "blocking" and "18878765786" in issue.message for issue in blocked)
    quoted = Draft.model_validate({"sections": [{"id": "p", "title": "查询", "kind": "project", "items": [
        {"id": "i", "text": "材料中的邮箱 campus-be-001@example.invalid 只是原文。", "fact_ids": ["e1"]}]}]})
    source_with_mail = "使用 Java 完成查询接口。邮箱 campus-be-001@example.invalid。"
    assert blocking_gates(_job(source_with_mail, contact=""), quoted) == []
    assert header_contact("", source_with_mail) == ""
    assert header_contact("18800001111", source_with_mail) == "18800001111"


def test_shortened_school_is_blocked_only_when_the_user_did_not_submit_it():
    from app.gates import blocking_gates
    from app.generation_models import Draft

    draft = Draft.model_validate({"education": [{"id": "edu1", "school": "江城大学", "degree": "本科", "major": "软件工程", "fact_ids": ["e1"]}],
                                  "sections": [{"id": "p", "title": "查询", "kind": "project", "items": [
                                      {"id": "i", "text": "使用 Java 完成查询接口。", "fact_ids": ["e1"]}]}]})
    issues = blocking_gates(_job("就读江城示例理工大学。使用 Java 完成查询接口。"), draft)
    assert any(issue.severity == "blocking" and "全称" in issue.message for issue in issues)


def test_duration_conflict_must_stay_visible_and_unanswered_source_can_keep_its_only_figure():
    from app.gates import blocking_gates, durations_conflict
    from app.generation_models import Draft

    picked = Draft.model_validate({"sections": [{"id": "job", "title": "知南教育", "kind": "work", "items": [
        {"id": "i", "text": "在知南教育实习一个月。", "fact_ids": ["e1"]}]}]})
    conflicted = _job(SAMPLE3, answers="实际是 2025.07–2025.08，两个月。")
    assert durations_conflict(SAMPLE3, "实际是 2025.07–2025.08，两个月。")
    assert any(issue.code == "fact_card_conflict" and issue.severity == "blocking" for issue in blocking_gates(conflicted, picked))
    marked = Draft.model_validate({"sections": [{"id": "job", "title": "知南教育", "kind": "work", "items": [
        {"id": "i", "text": "知南教育实习【待确认：原材料写一个月，补充回答写 2025.07–2025.08 两个月】。", "fact_ids": ["e1"]}]}]})
    assert not any(issue.code == "fact_card_conflict" for issue in blocking_gates(conflicted, marked))
    single = Draft.model_validate({"sections": [
        {"id": "club", "title": "学生会", "kind": "campus", "items": [{"id": "c", "text": "校学生会新媒体部干事，负责公众号排版。", "fact_ids": ["e1"]}]},
        {"id": "job", "title": "知南教育", "kind": "work", "items": [{"id": "i", "text": "暑假在知南教育实习一个月。", "fact_ids": ["e1"]}]},
    ]})
    assert not any(issue.code == "fact_card_conflict" for issue in blocking_gates(_job(SAMPLE3), single))


def test_project_item_cannot_use_another_periods_dates():
    from app.gates import blocking_gates
    from app.generation_models import Draft

    draft = Draft.model_validate({"sections": [{"id": "book", "title": "校园二手书", "kind": "project",
                                               "start_date": "2025-03", "end_date": "2025-06", "items": [
                                                   {"id": "i", "text": "项目时间为 2025.10—2026.01。", "fact_ids": ["e1"]}]}]})
    issues = blocking_gates(_job("校园二手书 2025.03—2025.06。座位项目 2025.10—2026.01。"), draft)
    assert any(issue.code == "conflict" and "时间不一致" in issue.message for issue in issues)


def test_ad_hoc_section_is_blocking_and_gap_markers_hold_formal_export(tmp_path):
    from app.exports import check_export
    from app.gates import blocking_gates
    from app.generation_models import Draft
    from app.models import ExportRequest, Item, ResumeContent, Section
    from app.store import Conflict, ResumeStore

    summary = Draft.model_validate({"sections": [{"id": "s", "title": "个人总结", "kind": "other", "items": [
        {"id": "i", "text": "热爱技术。", "fact_ids": ["e1"]}]}]})
    assert any(issue.code == "structure" and issue.severity == "blocking" for issue in blocking_gates(_job("热爱技术。"), summary))
    assert blocking_gates(_job("热爱技术。", mode="recheck"), summary) == []
    store = ResumeStore(tmp_path / "resumes.sqlite3")
    content = ResumeContent(name="测", contact="a@example.com", target_role="后端", sections=[
        Section(id="p", title="知南教育", kind="work", items=[Item(id="i", text="实习【待确认：一个月还是两个月】")])])
    record = store.create(content, "manual", "实习过一个月")
    store.confirm(record.id, 1)
    with pytest.raises(Conflict, match="待确认"):
        check_export(store.get(record.id), ExportRequest(format="docx", expected_revision=1))
    check_export(store.get(record.id), ExportRequest(format="docx", expected_revision=1, draft=True))


def test_missing_strong_result_asks_for_revision_and_user_school_does_not(tmp_path):
    from test_workflow import PASS, PLAN, request, setup

    source = "就读江城示例理工大学。项目获评优秀。使用 Java 完成课程预约查询接口，编写测试记录。"
    missing = {"sections": [{"id": "projects", "title": "项目经历", "items": [
        {"id": "item1", "text": "使用 Java 完成课程预约查询接口，并编写测试记录。", "fact_ids": ["e1"]}]}]}
    restored = {"sections": [{"id": "projects", "title": "项目经历", "items": [
        {"id": "item1", "text": "使用 Java 完成课程预约查询接口，并编写测试记录。课程获评优秀。", "fact_ids": ["e1"]}]}]}
    runner, jobs, _, _, model = setup(tmp_path, [PLAN, missing, PASS, restored, PASS])
    job = runner.submit(request(source_text=source, education=[{"id": "edu1", "school": "江城大学", "degree": "本科", "major": "软件工程"}]))
    asyncio.run(runner.run_one())
    result = jobs.get(job["id"])
    assert result["state"] == "ready"
    assert [call[0] for call in model.calls] == ["plan", "draft", "review", "revise", "review"]
    assert any("优秀" in issue["message"] for issue in model.calls[3][1]["issues_to_fix"])
    assert result["draft"]["education"][0]["school"] == "江城大学"
    assert result["draft"]["sections"][0]["kind"] == "project"
    school_notes = [issue for issue in result["issues"] if "江城大学" in issue["message"]]
    assert len(school_notes) == 1 and school_notes[0]["severity"] == "warning"


def test_personal_summary_block_is_sent_back_before_writing_review(tmp_path):
    from test_workflow import DRAFT, PASS, PLAN, request, setup

    summary = {"sections": [{"id": "about", "title": "个人总结", "kind": "other", "items": [
        {"id": "item1", "text": "使用 Java 完成课程预约查询接口，并编写测试记录。", "fact_ids": ["e1"]}]}]}
    runner, jobs, _, _, model = setup(tmp_path, [PLAN, summary, DRAFT, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    assert [call[0] for call in model.calls] == ["plan", "draft", "revise", "review"]
    assert jobs.get(job["id"])["state"] == "ready"
    assert any(issue["code"] == "structure" for issue in model.calls[2][1]["issues_to_fix"])


def _sample_copy():
    from app.generation_models import Draft

    return Draft.model_validate({"sections": [
        {"id": "skills", "title": "专业技能", "kind": "skills", "items": [
            {"id": "sk-java", "text": "Java：课程与项目中使用约两年。", "fact_ids": ["e1"]},
            {"id": "sk-docker", "text": "Docker：了解，只在课程实验里跑过官方镜像。", "fact_ids": ["e1"]},
        ]},
        {"id": "seat", "title": "图书馆座位预约", "kind": "project", "items": [
            {"id": "seat-run", "text": "社团组织 2 周试运行，覆盖图书馆一层自习区。试运行结束后因学校统一系统上线而停止，未正式推广。", "fact_ids": ["e1"]},
            {"id": "seat-others", "text": "前端与支付模拟由其他组员完成。", "fact_ids": ["e1"]},
        ]},
        {"id": "honor", "title": "校园与荣誉", "kind": "campus", "items": [
            {"id": "bronze", "text": "省赛铜奖。", "fact_ids": ["e1"]},
        ]},
    ]})


@pytest.mark.parametrize(("contact", "school"), [
    ("", ""),
    ("campus-be-001@example.invalid", "江城大学"),
])
def test_sample1_strips_negatives_marks_skipped_gaps_and_drops_docker_either_way(contact, school):
    from app.generation_models import Draft
    from app.phases import prepare_draft
    from app.resume_layout import education_text, period_text
    from app.skill import build_evidence

    education = [{"id": "edu1", "school": school, "degree": "本科", "major": "软件工程", "start_date": "2023-09", "end_date": "2027-06"}] if school else []
    evidence = [item.model_dump() for item in build_evidence(SAMPLE1)]
    for row in education:
        from app.models import Education
        profile = Education.model_validate(row)
        text = " ".join(filter(None, (education_text(profile), period_text(profile))))
        evidence.extend(item.model_dump() for item in build_evidence(text, prefix=f"profile-{row['id']}-"))
    job = {"answered": True, "answer_context": [], "evidence": evidence,
           "plan": {"questions": [{"id": "q1", "text": "试运行期间大约多少人使用？"},
                                  {"id": "q2", "text": "省赛铜奖是个人赛还是团队赛？"}], "gaps": ["Redis 是否只了解基础用法"]},
           "input": {"source_text": SAMPLE1, "jd": JD, "contact": contact, "education": education, "career_stage": "entry"}}
    polished = prepare_draft(job, _sample_copy())
    body = "\n".join(item.text for section in polished.sections for item in section.items)
    assert "未正式推广" not in body and "试运行结束后" not in body and "其他组员" not in body
    assert "社团组织 2 周试运行，覆盖图书馆一层自习区" in body
    assert "【待补充：使用人数】" in body
    assert "【待补充：个人赛还是团队赛】" in body
    assert "【待补充：Redis" not in body
    assert any("Redis" in note for note in job["coverage_notes"])
    assert "Docker" not in body and "Java" in body
    from app.resume_layout import section_text
    seat = next(section for section in polished.sections if section.id == "seat")
    assert "3 人" in section_text(seat)
    honor = next(section for section in polished.sections if section.kind == "campus")
    assert section_text(honor) == "校 ACM 集训队 · 队员"
    assert "校园与荣誉" not in section_text(honor)
    assert all(section.items for section in polished.sections)
    assert not any(section.kind == "skills" and not section.items for section in polished.sections)
    raw = Draft.model_validate(_sample_copy().model_dump())
    from app.gates import blocking_gates
    blocked = blocking_gates({"mode": "generate", "input": job["input"], "answer_context": []}, raw)
    assert any(issue.severity == "blocking" and "未正式推广" in issue.message for issue in blocked)


def test_ungrounded_skill_claim_is_blocked_with_or_without_contact():
    from app.gates import blocking_gates
    from app.generation_models import Draft
    from app.skill import build_evidence, validate_draft

    claim = "熟悉面向对象基础与集合等常用类库。"
    evidence = build_evidence(SAMPLE1)
    for contact in ("", "campus-be-001@example.invalid"):
        issues = validate_draft(make_draft(claim), evidence)
        assert any(issue.severity == "blocking" and issue.code == "unsupported" and "面向对象" in issue.message for issue in issues)
        draft = Draft.model_validate({"sections": [{"id": "skills", "title": "专业技能", "kind": "skills", "items": [
            {"id": "i", "text": claim, "fact_ids": ["e1"]}]}]})
        same = blocking_gates(_job(SAMPLE1, contact=contact), draft)
        assert all("面向对象" not in issue.message or issue.severity == "blocking" for issue in same)
        assert contact in ("", "campus-be-001@example.invalid")


def test_jd_gaps_stay_out_of_the_body_and_markers_sit_on_their_sentence():
    from app.generation_models import Draft
    from app.phases import prepare_draft

    draft = Draft.model_validate({"sections": [
        {"id": "book", "title": "校园二手书交易平台", "kind": "project", "items": [
            {"id": "b1", "text": "在库存扣减时加入行锁校验，并编写 12 条单元测试。使用 JMeter 在本机压测，50 个并发线程平均响应约 180ms。", "fact_ids": ["e1"]},
        ]},
        {"id": "honor", "title": "校园与荣誉", "kind": "campus", "organization": "校 ACM 集训队", "role": "队员", "items": [
            {"id": "h1", "text": "省赛铜奖。【待补充：没有线上故障排查、容灾降级相关的经历证据，JD 第 3 条职责暂无可写内容】【待补充：没有技术博客或开源项目的证据，JD 优先项之一缺材料】【待补充：无技术博客、开源项目经历（JD 优先项），暂不写入】", "fact_ids": ["e1"]},
        ]},
    ]})
    job = {"answered": True, "answer_context": [], "evidence": [],
           "plan": {"questions": [{"id": "q1", "text": "单元测试覆盖了哪些场景？"}],
                    "gaps": ["没有线上故障排查、容灾降级相关的经历证据，JD 第 3 条职责暂无可写内容"]},
           "input": {"source_text": SAMPLE1, "jd": JD, "contact": "", "education": [], "career_stage": "entry"}}
    polished = prepare_draft(job, draft)
    book = next(section for section in polished.sections if section.id == "book").items[0].text
    honor = next(section for section in polished.sections if section.kind == "campus").items[0].text
    assert book.index("单元测试") < book.index("【待补充：单元测试覆盖范围】") < book.index("JMeter")
    assert "【待补充" not in honor
    assert all("JD" not in item.text for section in polished.sections for item in section.items)
    assert sum(item.text.count("【待补充") for section in polished.sections for item in section.items) <= 4
    assert any("故障排查" in note or "技术博客" in note for note in job["coverage_notes"])
    assert all(item.text.count("【待补充") <= 1 for section in polished.sections for item in section.items)


def test_proficiency_cannot_exceed_the_source_for_any_skill():
    from app.gates import proficiency_violations, soften_proficiency
    from app.skill import build_evidence, validate_draft

    evidence = build_evidence(SAMPLE1)
    for claim in ("掌握 Spring Boot。", "熟悉 Spring Boot。", "Redis：掌握基础用法。"):
        issues = validate_draft(make_draft(claim), evidence)
        assert any(issue.severity == "blocking" and issue.code == "attribution" for issue in issues), claim
        assert proficiency_violations(claim, SAMPLE1)
        softened = soften_proficiency(claim, SAMPLE1)
        assert "掌握" not in softened and "熟悉" not in softened
        assert "Spring Boot" in softened or "Redis" in softened
    assert not proficiency_violations("了解 Docker，只在课程实验里跑过官方镜像。", SAMPLE1)
    assert not validate_draft(make_draft("熟悉 Java，完成查询接口。"), build_evidence("熟悉 Java，完成查询接口。"))


def test_team_size_is_kept_and_identical_model_output_ignores_headers():
    from app.generation_models import Draft
    from app.phases import prepare_draft

    draft = Draft.model_validate({"sections": [
        {"id": "book", "title": "校园二手书交易平台后端", "kind": "project", "items": [
            {"id": "b1", "text": "用 Spring Boot 与 MySQL 实现 3 个订单接口。", "fact_ids": ["e1"]}]},
        {"id": "seat", "title": "图书馆座位预约小程序后端", "kind": "project", "items": [
            {"id": "s1", "text": "用 Spring 定时任务释放座位。", "fact_ids": ["e1"]}]},
    ]})
    from app.gates import missing_team_sizes
    raw = "\n".join(f"{section.title} {item.text}" for section in draft.sections for item in section.items)
    assert missing_team_sizes(raw, SAMPLE1)

    def body(contact, school):
        education = [{"id": "edu1", "school": school, "degree": "本科", "major": "软件工程", "start_date": "2023-09", "end_date": "2027-06"}] if school else []
        job = {"answered": False, "answer_context": [], "evidence": [{"id": "profile-edu1-1", "text": f"{school} 本科", "start": 0, "end": 4}] if school else [],
               "plan": {"questions": [], "gaps": []},
               "input": {"source_text": SAMPLE1, "jd": JD, "contact": contact, "education": education, "career_stage": "entry"}}
        polished = prepare_draft(job, draft)
        return [(section.title, section.role, [item.text for item in section.items]) for section in polished.sections]

    filled = body("campus-be-001@example.invalid", "江城大学")
    empty = body("", "")
    assert filled == empty
    rendered = "\n".join(f"{title} {role} {' '.join(items)}" for title, role, items in filled)
    assert "4 人" in rendered and "3 人" in rendered
    assert not missing_team_sizes(rendered, SAMPLE1)


def test_body_prompts_are_identical_regardless_of_contact_and_school(tmp_path):
    import json
    from copy import deepcopy

    from test_workflow import request, setup

    runner, jobs, _, _, _ = setup(tmp_path, [])
    edu = {"id": "edu1", "school": "江城示例理工大学", "degree": "本科", "major": "软件工程", "start_date": "2023-09", "end_date": "2027-06"}
    job = runner.submit(request(source_text=SAMPLE1, education=[edu], jd=JD).model_copy(update={"contact": "campus-be-001@example.invalid"}))
    stored = jobs.get(job["id"])

    def prompt(contact, school, stage):
        current = deepcopy(stored)
        current["input"]["contact"] = contact
        current["input"]["education"] = [{**edu, "school": school}]
        current["evidence"] = [item for item in current["evidence"] if not str(item["id"]).startswith("profile-")]
        current["evidence"].append({"id": "profile-edu1-1", "text": f"{school} {contact} 本科 软件工程", "start": 0, "end": 8})
        current["plan"] = {"decision": "draft", "selected_fact_ids": ["e1"], "focus": [], "questions": [], "gaps": []}
        current["draft"] = {"summary": None, "education": [{**edu, "school": school, "fact_ids": ["profile-edu1-1"]}],
                            "sections": [{"id": "p", "title": "项目", "kind": "project", "items": [{"id": "i", "text": "完成接口", "fact_ids": ["e1"]}]}]}
        context = runner._context(current, stage)
        return json.dumps(context, ensure_ascii=False, sort_keys=True)

    for stage in ("plan", "draft", "review", "revise"):
        filled = prompt("campus-be-001@example.invalid", "江城大学", stage)
        empty = prompt("", "江城示例理工大学", stage)
        assert filled == empty, stage
        assert "campus-be-001@example.invalid" not in filled
        assert "江城大学" not in filled


def test_resume_dates_render_with_dots():
    from io import BytesIO

    from docx import Document

    from app.models import Education, ResumeContent
    from app.rendering import render_docx, render_html

    content = ResumeContent(name="测", contact="a@example.com", target_role="后端",
                            education=[Education(id="edu1", school="江城示例理工大学", degree="本科", major="软件工程", start_date="2023-09", end_date="2027-06")],
                            sections=[])
    html = render_html(content)
    doc = "\n".join(paragraph.text for paragraph in Document(BytesIO(render_docx(content, False, False))).paragraphs)
    assert "2023.09" in html and "2027.06" in html and "2023-09" not in html
    assert "2023.09" in doc and "2023-09" not in doc


def test_skills_heading_does_not_create_an_empty_claim():
    from app.generation_models import Draft
    from app.skill import build_evidence, validate_draft

    draft = Draft.model_validate({"sections": [{"id": "skills", "title": "专业技能", "kind": "skills", "items": [
        {"id": "sk", "text": "Java：课程与项目中使用约两年。", "fact_ids": ["e1"]}]}]})
    assert draft.metadata_claims(["e1"]) == []
    assert not any(issue.severity == "blocking" for issue in validate_draft(draft, build_evidence(SAMPLE1)))


def test_truncated_and_coverage_markers_leave_the_body():
    from app.gates import marker_label
    from app.generation_models import Draft
    from app.phases import prepare_draft

    assert marker_label("校园二手书交易平台里") is None
    assert marker_label("图书馆座位预约的定时任务") is None
    assert marker_label("ACM 省赛你个人在队内主要承担什么（如算法实现、调试、") == "个人负责的模块"
    assert marker_label("缺少线上/生产环境经验") is None
    draft = Draft.model_validate({"sections": [
        {"id": "seat", "title": "图书馆座位预约小程序后端", "kind": "project", "items": [
            {"id": "s1", "text": "社团组织 2 周试运行，覆盖图书馆一层自习区。【待补充：缺少线上/生产环境经验】【待补充：图书馆座位预约的定时任务】", "fact_ids": ["e1"]},
        ]},
        {"id": "honor", "title": "校园经历", "kind": "campus", "items": [
            {"id": "h1", "text": "省赛铜奖。", "fact_ids": ["e1"]},
        ]},
    ]})
    job = {"answered": True, "answer_context": [], "evidence": [], "plan": {"questions": [
        {"id": "q1", "text": "ACM 省赛你个人在队内主要承担什么（如算法实现、调试、"},
        {"id": "q2", "text": "校园二手书交易平台里"},
    ], "gaps": ["缺少线上/生产环境经验"]}, "input": {"source_text": SAMPLE1, "jd": JD, "contact": "", "education": [], "career_stage": "entry"}}
    polished = prepare_draft(job, draft)
    body = "\n".join(item.text for section in polished.sections for item in section.items)
    assert "缺少线上" not in body and "交易平台里" not in body and "定时任务】" not in body
    assert "【待补充：个人负责的模块】" in body
    assert "…" not in body and body.count("【待补充") == 1
    honor = next(section for section in polished.sections if section.kind == "campus")
    from app.resume_layout import section_text
    assert section_text(honor) == "校 ACM 集训队 · 队员"
    assert "校园经历" not in (honor.title, honor.organization, honor.role)
    assert any("生产环境" in note or "交易平台里" in note for note in job["coverage_notes"])


@pytest.mark.parametrize(("contact", "school"), [("", ""), ("campus-be-001@example.invalid", "江城大学")])
def test_sample1_recorded_draft_reaches_ready_for_both_headers(tmp_path, contact, school):
    from test_workflow import PASS, request, setup
    from test_writing_coach import quality

    plan = {"decision": "draft", "selected_fact_ids": ["e1", "e2"], "focus": ["MySQL"], "questions": [], "gaps": ["缺少线上/生产环境经验"]}
    recorded = {"sections": [
        {"id": "skills", "title": "专业技能", "kind": "skills", "fact_ids": ["e1"], "items": [
            {"id": "sk1", "text": "Java：课程与项目中使用约两年。Spring Boot、MySQL。Redis 基础用法。", "fact_ids": ["e1"]}]},
        {"id": "book", "title": "校园二手书交易平台后端", "kind": "project", "role": "4 人小组", "start_date": "2025-03", "end_date": "2025-06", "fact_ids": ["e1"], "items": [
            {"id": "b1", "text": "用 Spring Boot 与 MySQL 实现下单、取消、超时关单 3 个接口，并编写 12 条单元测试。", "fact_ids": ["e1"]},
            {"id": "b2", "text": "小组课程验收获评优秀，全班 9 组中 2 组。使用 JMeter，50 个并发线程下平均响应约 180ms。", "fact_ids": ["e1"]}]},
        {"id": "seat", "title": "图书馆座位预约小程序后端", "kind": "project", "role": "3 人小组", "start_date": "2025-10", "end_date": "2026-01", "fact_ids": ["e2"], "items": [
            {"id": "s1", "text": "用 Spring 定时任务实现签到超时自动释放座位。社团组织 2 周试运行，覆盖图书馆一层自习区。", "fact_ids": ["e2"]}]},
        {"id": "honor", "title": "校园经历", "kind": "campus", "fact_ids": ["e2"], "items": [
            {"id": "h1", "text": "省赛铜奖。", "fact_ids": ["e2"]}]},
    ]}
    review = {**PASS, "quality": quality("revise")}
    runner, jobs, _, _, model = setup(tmp_path, [plan, recorded, review, recorded, {**PASS, "quality": quality()}])
    education = [{"id": "edu1", "school": school, "degree": "本科", "major": "软件工程", "start_date": "2023-09", "end_date": "2027-06"}]
    submitted = request(source_text=SAMPLE1, jd=JD, education=education, career_stage="entry")
    if contact:
        submitted = submitted.model_copy(update={"contact": contact})
    job = runner.submit(submitted)
    if not contact:
        jobs.mutate(job["id"], lambda current, _: current["input"].update(contact=""))
    asyncio.run(runner.run_one())
    result = jobs.get(job["id"])
    assert result["state"] == "ready", result.get("error")
    assert result["error"] == ""
    assert [call[0] for call in model.calls] == ["plan", "draft", "review", "revise", "review"]
    body = "\n".join(item["text"] for section in result["draft"]["sections"] for item in section["items"])
    assert "专业技能" in [section["title"] for section in result["draft"]["sections"]]
    assert "缺少线上" not in body
    honor = next(section for section in result["draft"]["sections"] if section["kind"] == "campus")
    from app.resume_layout import section_text
    assert section_text(honor) == "校 ACM 集训队 · 队员"


def test_skipped_followup_still_demands_a_full_draft_without_an_empty_block(tmp_path):
    from test_workflow import request, setup

    ask = {"decision": "ask", "selected_fact_ids": ["e1"], "questions": [{"id": "q1", "text": "试运行有多少人使用？"}]}
    runner, jobs, _, _, _ = setup(tmp_path, [ask])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    waiting = jobs.get(job["id"])
    runner.answer(job["id"], {"question_group": waiting["question_group"], "skip": True, "answers": {}})
    context = runner._context(jobs.get(job["id"]), "draft")
    assert context["followup_skipped"] is True
    assert "【待补充" in context["instructions"] and "空板块" in context["instructions"]
    assert "me@example.com" not in context["instructions"]
