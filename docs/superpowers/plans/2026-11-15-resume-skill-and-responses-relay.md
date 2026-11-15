# Resume Skill 与 Responses 中转站实施计划

**Spec:** `docs/superpowers/specs/2026-11-15-resume-skill-and-responses-relay-design.md`

**Goal:** 在保留现有事实门禁与兼容性的前提下，增强简历贡献表达规则，并让自定义 Responses 中转站贯穿连接测试、生成和 Agent 工具调用。

**Tech Stack:** Python 3.12, Pydantic 2, httpx, pytest, React 19, TypeScript, Vitest.

## Global Constraints

- 不读取后回显、不复制、不提交外部 Key；真实调用只使用合成输入。
- 先写失败测试并确认失败原因，再写实现；每个任务独立提交。
- Chat Completions、Anthropic Messages 和现有官方预设保持回归兼容。
- Skill 资源必须进入运行时 `stage_instructions`，不能只新增静态文档。
- 连接测试与正式模型调用使用同一协议适配器。
- 本轮不做协议自动探测或失败后双发。

## Task 1: 融合贡献表达 Skill

**Interfaces:** `app/skill.py` 产生阶段资源与指令；生成工作流消费 `stage_instructions`。

- [ ] 在 `tests/test_writing_coach.py` 或 `tests/test_skill.py` 增加用例，要求 plan/draft/review/revise 都装入贡献表达资源，并验证产品、运营及强调规则的关键契约。
- [ ] 运行定向测试，确认因资源尚不存在或未装载而失败。
- [ ] 新增 `skills/resume-writing/references/contribution-architecture.md`，更新 `app/skill.py`、产品/运营角色规则与编辑规则。
- [ ] 运行 Skill 与写作教练测试，确认通过并检查 Skill version 随内容变化。
- [ ] 提交 `feat: strengthen resume contribution writing skill`。

## Task 2: 增加 Responses 协议边界

**Interfaces:** `ProviderConfig.protocol` 被 endpoint/request/response adapter、probe 与 `ModelClient` 共同消费。

- [ ] 在 `tests/test_providers.py` 增加 Responses endpoint、request、text decode、function call decode、非 custom 协议校验测试。
- [ ] 在 `tests/test_model_client.py` 增加 Responses 正式结构化生成与工具委派测试。
- [ ] 运行定向测试，确认因 `protocol` 和适配尚不存在而失败。
- [ ] 实现 `ProviderConfig.protocol` 与 `app/provider_protocols.py` 的完整转换，保持现有协议不变。
- [ ] 运行 provider/model client 测试并提交 `feat: support custom OpenAI Responses providers`。

## Task 3: 打通配置、记忆与诊断脚本

**Interfaces:** UI/API 提交 protocol；key store 仅持久化非敏感 protocol；诊断脚本复用 runtime probe。

- [ ] 在 `tests/test_providers.py`、`tests/test_model_connection_tool.py` 与 `web/src/ModelSettings.test.tsx` 增加 protocol 保存/恢复、CLI 参数和 UI 选择测试。
- [ ] 运行定向测试，确认失败。
- [ ] 更新 `app/key_store.py`、`app/main.py`、`tools/test_model_connection.py`、`web/src/ModelSettings.tsx`。
- [ ] 运行后端与前端定向测试、TypeScript 检查并提交 `feat: expose custom provider protocol selection`。

## Task 4: 真实中转站烟测与完整验证

**Interfaces:** 外部本机配置只作为未提交的验证输入；应用 runtime 作为被测对象。

- [ ] 通过项目 `run_probe` 读取外部 Key 文件进行 Responses 合成 JSON 测试，不在命令或输出中出现 Key。
- [ ] 用同一配置执行一个最小结构化生成调用；若工具调用受中转站能力限制，单独记录，不把它误报为基础生成失败。
- [ ] 运行完整 pytest（沙箱外，仅写临时测试目录）、Ruff、22 个前端测试、TypeScript 与 Vite 构建。
- [ ] 按 review package 做全分支独立自审；重要问题用新失败测试修复，次要项记入 ledger。
- [ ] 将通过验证的提交合并回用户当前功能分支，重启本地服务并提供测试地址。

## Review Focus

- Responses 内容块、工具调用 arguments 与 incomplete 状态是否会被错误归一化。
- protocol 是否可能被官方预设误用，或在记住/恢复后丢失。
- Key 是否可能进入 JSON 文件、CLI 参数、测试快照、错误信息或日志。
- Skill 新规则是否与事实门禁冲突、把“优化表达”误写成“允许补事实”。
- 连接探针成功后，正式生成是否确实走同一 endpoint 和 adapter。

