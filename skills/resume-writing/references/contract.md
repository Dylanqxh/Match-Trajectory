# 宿主契约

宿主注入 target_role、target_basis、candidate_context、evidence、fixed_education、reference_date 和阶段资料。JD 是选择依据，evidence 是个人陈述，两者不能混用。
plan 输出 decision、selected_fact_ids、focus、questions、gaps；最多3问，decision=ask 才有问题。补问额度由宿主管理，跳过后不再问。
draft/revise 输出 education、summary、sections。姓名和联系信息本地回填；fixed_education 非空时教育由宿主固定。简介 id=__summary；经历和条目 ID 稳定且唯一；每条正文和经历元数据有 fact_ids。
日期用 YYYY 或 YYYY-MM；未知为空，明确仍在进行时才可填至今。highlights 最多2处、必须为正文已有短语，不输出 HTML 或 Markdown 标记。
review 输出 verdict、issues、strengths、quality。verdict 只表示事实：pass/blocked；blocking 必须有具体事实问题。quality 独立给出 status 和4项 dimensions：fit、contribution、evidence、readability。
每项质量包含 score（0/1/2 或不适用 null）、reason、item_ids、evidence_ids 和 action（keep/revise/need_input/not_applicable）。status 根据动作：有 revise 为 revise，否则有 need_input 为 insufficient，其余 ready。revise 必须定位当前内容及可用原文，不能在无证据时要求补写事实。
interview_topics 可选最多3项，只输出当前段落对应的面试追问与依据；不加入投递正文、不先编回答。
具体字段、长度、类型以本轮 JSON Schema 为准；只有 JSON 对象，无附加思维过程。旧报告缺 quality 表示未评估，不能据事实 pass 推断质量 ready。
