from app.generation_models import AnswerInput, Plan, Question


def test_old_open_questions_still_validate_and_new_choices_need_one_recommendation():
    old = Question.model_validate({"id": "q1", "text": "本人交付了什么？"})
    assert old.kind == "note" and old.options == []
    plan = Plan.model_validate({"decision": "ask", "selected_fact_ids": ["e1"], "questions": [
        {"id": "q1", "kind": "choice", "text": "先突出哪段已有经历？", "options": [
            {"id": "a", "label": "先写材料里的离线对照", "recommended": True, "fact_ids": ["e1"]},
            {"id": "b", "label": "先写材料里的课程论文", "recommended": False, "fact_ids": ["e1"]},
        ]},
    ]})
    assert plan.questions[0].options[0].recommended is True
    try:
        Question.model_validate({"id": "q2", "kind": "choice", "text": "怎么排？", "options": [
            {"id": "a", "label": "甲", "recommended": True, "fact_ids": ["e1"]},
            {"id": "b", "label": "乙", "recommended": True, "fact_ids": ["e1"]},
        ]})
    except ValueError as error:
        assert "一个推荐" in str(error)
    else:
        raise AssertionError("两个推荐项不应通过")


def test_choice_cannot_invent_a_number_and_skip_does_not_confirm_it():
    from app.gates import ungrounded_choice
    from app.generation_service import collect_answer_context

    evidence = [{"id": "e1", "text": "离线 Recall@50 从 0.31 到 0.36。"}]
    invented = Plan.model_validate({"decision": "ask", "questions": [{"id": "q1", "kind": "choice", "text": "先看哪段？", "options": [
        {"id": "a", "label": "先写点击率提升 20%", "recommended": True, "fact_ids": ["e1"]},
        {"id": "b", "label": "先写已有离线对照", "recommended": False, "fact_ids": ["e1"]},
    ]}]})
    assert "没有的数字" in ungrounded_choice(invented, evidence)
    grounded = Plan.model_validate({"decision": "ask", "questions": [{"id": "q1", "kind": "choice", "text": "先看哪段？", "options": [
        {"id": "a", "label": "先写已有的离线 Recall 对照", "recommended": True, "fact_ids": ["e1"]},
        {"id": "b", "label": "保持材料原有顺序", "recommended": False, "fact_ids": ["e1"]},
    ]}]})
    assert ungrounded_choice(grounded, evidence) == ""
    job = {"plan": grounded.model_dump(), "evidence": evidence}
    try:
        AnswerInput.model_validate({"question_group": "g", "skip": True, "choices": {"q1": "a"}, "answers": {"q1": "点击率提升 20%"}})
    except ValueError as error:
        assert "跳过时不能提交回答" in str(error)
    else:
        raise AssertionError("跳过不能同时提交选项或补充")
    added, context = collect_answer_context(job, AnswerInput.model_validate({"question_group": "g", "skip": True}))
    assert added == [] and context == []
    added, context = collect_answer_context(job, AnswerInput.model_validate({"question_group": "g", "choices": {"q1": "a"}}))
    assert added == []
    assert context[0]["editorial"] is True and context[0]["fact_ids"] == ["e1"]
    assert "20%" not in context[0]["answer"]
