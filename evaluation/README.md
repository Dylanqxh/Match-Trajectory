# M1.7 本地对照评测入口

这是一条复用现有 `Workflow`、`GenerationInput`、`ModelClient` 的独立入口。每例按固定顺序运行 `langgraph` 基线与 `supervisor`，每个模式使用独立临时数据库与检查点，不访问产品 data、已保存简历或真实配置。候选不采纳进产品。

本次仅使用合成材料及本地 fake HTTP 验证工程行为，**没有真实供应商调用或真实简历质量结论**。示例 JSON 是合成工程夹具，不能作为真实质量证据。

## PowerShell 用法

在项目目录执行。默认只校验格式并冻结本地材料和计划，不读取凭据，不测试连接，不发模型请求：

```powershell
.\.venv\Scripts\python.exe -m tools.evaluate_resumes evaluation/synthetic-example.json --output evaluation/runs/prepare-001
```

默认运行也会创建目录；之后明确选择**另一个新目录**发起付费运行。先将已授权且适当脱敏的材料保存为独立 manifest，固定供应商、地址及模型，再在当前进程环境安全设置 `EVALUATION_API_KEY`（不放入文件或命令历史）。确认输入是允许发送给该供应商的材料后，显式启用：

```powershell
.\.venv\Scripts\python.exe -m tools.evaluate_resumes evaluation/authorized-cases.json --output evaluation/runs/model-001 --run
```

`--run` 表示授权将该 manifest 材料发给配置的供应商，可能计费。工具只读取 `EVALUATION_API_KEY`；报告不保存 Key、headers、完整请求或异常原文。地址遵循产品 HTTPS/本机 HTTP 校验规则。报告、冻结材料与候选含个人信息，只留本地，由材料所有人管理访问与保留期限，不提交到 Git。

## 输入与边界

JSON 顶层字段与示例一致，拒绝未知字段和内嵌 Key。`dataset_label` 只能为 `synthetic` 或 `authorized`；后者是使用者对授权材料的声明。`rules_version` 是人工固定的实验标签。`cases[].input` 直接按产品 `GenerationInput` 验证；runner 固定 request_id、execution_mode 和 send_materials，输入不得覆盖这些字段。每例需 source_text、name、contact、target_role；可使用化名及求职专用联系方式。最多100例，case id 为唯一 ASCII 标识。补问最多一次，由 runner 明确 skip，不补造回答。

`frozen.json` 保存相同输入、模式顺序、模型标识、输出协议、应用源码 SHA256、Skill 完整快照与哈希；两模式复用同一模型配置与输入。版本标签不保证供应商别名背后的权重不变；正式比较应使用供应商可固定版本的模型，并保存执行日期和模型说明。一次小样本不能证明普遍效果，固定顺序也可能受供应商时段变化影响。

`max_calls` 是全评测**实际 HTTP attempt 总上限**，`case_max_calls` 是每个 case/mode 的上限，包含 supervisor 工具能力 probe、所有结构重试、修订与审阅。每个 supervisor case 先用产品 `probe_context()` 调用一次受限工具探测；probe 失败不自动换模式。没有额外不计账的连接测试，也没有工具自身的隐藏重试。产品任务预算仍同时生效，任一预算到达均停止请求。`workflow_calls` 是产品工作流预留计数，可能包含被评测预算拦下的预留；`model_calls`/`attempts` 才是实际发往模型边界的计数。工具probe不在 workflow_calls 中。

`timeout_seconds` 是整个运行墙钟上限，`case_timeout_seconds` 是单个 case/mode 上限。取消或超时后的远端请求可能仍在服务方执行/计费。`attempts.jsonl` 在每次实际模型调用前写 attempt、flush、fsync，随后写 outcome 和供应商实际返回的 token usage；`response_received` 仅表示收到响应，不代表结构或质量通过。无 usage 时记为空/未知，费用为 null，不以零费用或估算替代。逐例 token usage 包括该例的 probe；全局 usage 包括所有已知返回，缺失部分不推算。

## 本地输出与人工评审

- `report.json`：逐例工程状态、stage、模型/工作流调用数、实际 usage、产品 issues、候选文件路径。`finished` 仅表示评测流程结束，应检查逐例 status；`ready` 也不等于人工通过。
- `*-candidate.json`：候选 draft、源 evidence 引用与产品 review，便于逐条比对事实来源。
- `human_review.csv`：独立人工模板，reviewer、日期、严重事实错误、无依据 claim id、source evidence id、写作意见及是否接受均留空。应由了解材料的人阅读冻结输入和候选后填写；不要把模型自评或产品校验当作幻觉率。
- `attempts.jsonl`：调用持久账本，不存提示词、响应正文、Key或错误原文。

人工评审需逐项核对个人归属、数字单位、日期、项目状态和缺失信息；严重事实错误由人标注，不自动计算“幻觉率”或“80%质量达标”。合成与授权真实材料应分开汇报，样本量、失败/超时、缺失 usage、人工标注分歧均保留。

**不支持 resume 或覆盖已有 run 目录。** 崩溃后保留所有已写账本；只有 attempt 没有 outcome 或 outcome=unknown 的调用不能视为未发送，也不能自动重发。先人工核对供应商记录，必要时明确选择新目录新运行，原目录保留；新运行可能重复计费。临时工作区在正常退出时清理，异常终止可能残留系统临时目录；最终候选及引用保存在输出目录。

## 本地验证

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_evaluation.py -q -p no:cacheprovider
```

测试使用 `httpx.MockTransport` 或 fake 外部请求边界，验证默认离线、显式启用、完整两模式任务、probe计账、全局预算、每例预算、超时未知调用、脱敏与拒绝已有目录。它们不是供应商兼容性、真实模型事实准确性或写作质量证据。

此入口面向源码开发环境，未作为便携包内的批量评测界面。真实运行拒绝凭据出现在case标识中，避免经文件名、CSV或调用账本泄露；合成工具probe还须按指定动作和索引完成，不能只凭收到tool_calls就认定通过。
