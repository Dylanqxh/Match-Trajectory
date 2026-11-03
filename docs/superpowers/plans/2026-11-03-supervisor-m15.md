# M1.5 兼容编排升级执行计划

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. 用户已授权直接执行，不再次等待方案确认。

**Goal:** 在 M1 上交付持久化 LangGraph 执行和可选受控 Supervisor，保住旧任务、预算与导出边界。

**Architecture:** 业务库为权威，原阶段执行提取为共享步骤；legacy 和 LangGraph 执行器复用。Supervisor 只处理多项修正取舍，使用受限原生工具调用；默认生成不额外增加主管请求。

**Tech Stack:** Python 3.12、FastAPI、SQLite、LangGraph、SQLite async checkpointer、现有 React。

**Spec:** [Agent方案第9节](../../简历Agent架构设计方案.md#9-m15supervisor-兼容升级方案)。偏好学习是后续独立阶段，本轮不实现。

## Global Constraints

- 最多8次模型请求、累计180秒、最多两轮内容修正；重试和主管请求全部计入。
- 旧任务缺执行器字段时按legacy处理；一次任务固定执行器及协议版本。
- 原UI、内容结构、来源、审阅失效、人工核对和确认导出约定兼容。
- 检查点不保存Key或原文；检查点落后时以业务回执校对，不自动重跑已保存步骤。
- 仅在临时数据上验证，不重启用户服务、不读取真实凭据、不发送用户材料。

## Review Focus

- 检查点落后于业务提交：恢复不重复已保存步骤或扣费。
- 等待补问后刷新、重启、重复回答：原问题只消费一次，预算保留。
- 取消与迟到响应、并发编辑：旧执行结果不覆盖新版本。
- 原生工具能力未知或供应商拒绝：清楚停止，不隐式切换引擎付费重跑。
- 主管越权、选择不存在段落、缺证据意见：程序拒绝，不能改事实或强行扩写。

## Task 1: 双执行器与持久图

Files: `app/execution.py`、`app/workflow.py`、`app/jobs.py`、`app/generation_service.py`、`app/generation_models.py`、`tests/test_graph_workflow.py`、`pyproject.toml`、`uv.lock`。

Interfaces: `execute_step(job, token)` 单步业务推进；`run_engine(workflow, job)` 依任务固定引擎执行。

- [x] 先写测试：新任务图流程与legacy结果一致；旧任务无字段仍可完成；重启补问不重复plan；业务结果领先检查点不重复调用；不支持的引擎版本拒绝恢复。
- [x] 运行新测试，确认因功能缺失失败。
- [x] 共享步骤与异常处理保持原语义，新增持久图、纯引用State、独立等待节点、回执和旧字段缺省。
- [x] 运行新测试及完整pytest；检查Key与原文不进入检查点；提交。

## Task 2: 受控主管与能力探针

Files: `app/supervisor.py`、`app/model_client.py`、`app/model_registry.py`（如无需拆分则沿用现文件）、`app/main.py`、`tests/test_supervisor.py`。

Interfaces: `ModelClient.delegate(config, context)` 返回经Schema验证的修正计划；能力按当前配置版本保存，接口显式测试。

- [x] 先写测试：只有多项可修意见才调主管；缺证据不强改；工具参数越权拒绝；主管失败保留候选；8次预算计入主管并预留审阅；原生工具返回/拒绝/超限与脱敏。
- [x] 运行并观察失败，再实现受限委派工具、版本绑定能力探针、共享计数和可恢复决策。
- [x] 新测试与完整pytest通过，提交。

## Task 3: UI、交付验证与说明

Files: `web/src/App.tsx`、`ModelSettings.tsx`、`GenerationPanel.tsx`、`api.ts`、`README.md`、现有打包配置。

- [x] API测试先覆盖探针权限、执行模式和旧接口输入；观察失败后实现。
- [x] 默认沿用验证通过的图流程，显式开启智能修正策略；能力未验证时提示先测试，不能静默付费探测。
- [x] 显示主管阶段、步骤回执和费用边界；便携打包补入新增依赖。
- [x] pytest、Ruff、TypeScript、Vite、本地HTTP浏览器闭环、冻结包/依赖探针；记录真实模型未验证范围。
- [x] 接收独立评审的六项重要反馈并测试先行修复；最终汇总因额度中断，记录审阅范围限制。更新README并提交，不推送。

## 审阅与收尾记录

独立审阅收到六项重要反馈：探针锁释放丢唤醒、审阅结果与路由分开提交、结构重试耗尽最后审阅额度、意外异常文本进入检查点、条目跨经历移动、缺证据意见被关键词误分类。六项均先用回归测试复现，再集中修复；审阅器在最终汇总时因额度中断，没有获得完整审阅报告，不据此宣称全面审计通过。

实现取舍：沿用用户当前功能分支，源码和独立便携探针均在隔离数据中验收；不推送、不迁移用户运行库。Windows原生命令与账本替代Bash辅助脚本，保持测试和提交门禁。M2偏好学习、真实供应商效果、干净Windows与再分发许可验收后续独立完成。

最终验证：165项后端全部通过；TypeScript／Vite／Ruff通过；源码与最终冻结便携包的M1、Supervisor两套本地HTTP浏览器流程均通过，JS错误0。验证输出保存在忽略的artifacts/m15-final-*，便携探针在dist/m15-validation。真实供应商效果与干净系统仍未验证。
