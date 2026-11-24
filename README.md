# Match-Trajectory

一个面向求职者的开源 AI 简历工作台：从旧简历、经历材料和岗位描述中提取证据，生成可编辑简历，并继续修改、核对和导出。

[![Apache-2.0](https://img.shields.io/badge/license-Apache%202.0-173b31)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-245344)](pyproject.toml)
[![Node.js 22](https://img.shields.io/badge/node.js-22-1f5744)](package.json)
[![Docker Compose](https://img.shields.io/badge/docker-compose-2e6249)](compose.yaml)
[![FastAPI](https://img.shields.io/badge/api-FastAPI-36765f)](app/main.py)
[![React 19](https://img.shields.io/badge/web-React%2019-173b31)](package.json)

<p align="center">
  <img src="docs/images/hero.png" alt="Match-Trajectory 工作台：左侧简历列表，中间是编辑与 A4 预览，右侧是简历 Agent。画面使用应用内的虚构示例。" width="960">
</p>

<p align="center">
  <img src="docs/images/workbench-a4.png" alt="虚构示例陈亦宁的简历预览：右侧固定为一整页 A4，没有内嵌滚动条；下载 PDF 和下载 Word 在这一页下方。" width="420">
</p>

## 快速启动

### Docker Compose（推荐）

需要 Docker Engine 与 Compose 插件（Docker Desktop 也可以）。

```bash
git clone https://github.com/Dylanqxh/Match-Trajectory.git
cd Match-Trajectory
docker compose up --build -d
```

打开 [http://127.0.0.1:18765](http://127.0.0.1:18765)。

```bash
docker compose down          # 停止服务，保留数据
docker compose logs -f       # 查看日志
```

简历数据在 Docker 命名卷 `match-trajectory-data` 里。只有 `docker compose down -v` 会删掉它。

### 已配置的 Windows 开发环境

双击 `Start-App.cmd`，或运行 `.\scripts\Start-App.ps1`。

已经有 `web/dist` 时，启动不会重新构建前端。拉到新界面后先显式重建；构建失败会停下来，不会继续打开旧页面：

```powershell
.\scripts\Start-App.ps1 -NoBrowser -RebuildFrontend
```

## 怎么使用

1. 在「模型连接」里选择供应商，或填写自定义中转的 Base URL、协议、模型 ID 和 Key。
2. 选择方向，上传或粘贴旧简历，岗位 JD 可选。
3. 确认发送范围后生成。需要补充时可以回答，也可以跳过。
4. 在编辑器和预览里修改。右侧简历 Agent 可以收成窄条；窄屏幕时它移到画布下方。
5. 核对事实后，从预览旁边导出 PDF 或 Word。

不连接模型时，仍可手工编辑、保存、查看版本和导出。

## 关键能力

- **证据驱动**：数字、技能、责任、时间和结果要能回到你的材料，不从 JD 推断个人事实。
- **分岗位 Skill**：产品、后端、前端、测试、数据开发、算法、数据分析、运营等方向使用不同写作规则。
- **简历 Agent**：压缩、改写、排序和重点标记；修改后重新经过事实检查，并自动保存版本。
- **版本可回看**：手工编辑和 Agent 修改共享历史，能看时间、来源，以及和上一版的差异。
- **同一份正文导出**：页面预览、PDF 和 DOCX 使用同一份结构化内容。
- **本地优先**：简历、任务和导出文件留在本机；服务默认只监听本机回环地址。

## 用户流程

```mermaid
flowchart LR
    A[选择求职方向] --> B[上传或粘贴材料]
    B --> C[解析材料并建立证据]
    C --> D{需要补充信息吗}
    D -->|回答或跳过| E[规划与生成候选]
    D -->|不需要| E
    E --> F[事实检查与写作审阅]
    F --> G[保存为版本化简历]
    G --> H[手工或 Agent 修改]
    H --> F
    G --> I[确认并导出 PDF 或 DOCX]
```

## 系统架构

```mermaid
flowchart TB
    UI[React 简历工作台]
    API[FastAPI 本地 API]
    INTAKE[材料解析与证据切分]
    FLOW[生成工作流]
    AGENT[简历编辑 Agent]
    SKILL[分阶段与分岗位 Skill]
    GATE[事实门禁与质量审阅]
    MODEL[模型协议适配层]
    PROVIDER[官方 API 或自定义中转]
    DATA[(SQLite 与本地文件)]
    EXPORT[PDF 与 DOCX 导出]

    UI --> API
    API --> INTAKE
    API --> FLOW
    API --> AGENT
    INTAKE --> FLOW
    SKILL --> FLOW
    FLOW --> MODEL
    AGENT --> MODEL
    MODEL --> PROVIDER
    FLOW --> GATE
    AGENT --> GATE
    GATE --> DATA
    API <--> DATA
    DATA --> EXPORT
```

![架构分层：工作台、本地 API、材料与生成和 Agent、Skill 与事实门禁、模型、SQLite 与导出](docs/images/architecture.svg)

## 模型连接

内置 OpenAI、Anthropic、DeepSeek 和阿里云百炼，也支持自定义中转：

- OpenAI 兼容的 Chat Completions
- OpenAI Responses
- Anthropic Messages

连接测试只发送合成短文本，不发送简历。Key 不会写入项目文件；勾选「记住 Key」时只尝试保存到操作系统钥匙串，否则仅留在当前服务内存。

第三方接口可先用安全诊断脚本测试：

```powershell
python tools\test_model_connection.py `
  --base-url https://relay.example.com/v1 `
  --model your-model-id `
  --protocol responses
```

### 模型中转（可选）

自定义中转是可选项，不是本项目的官方服务。

如果需要稳定的第三方 API 来调用 GPT 等模型，可联系 QQ：2286141017。

## 数据与安全边界

- 姓名和联系方式由本地应用管理；发送给模型的材料范围由你确认。
- 模型只能返回结构化候选，不能执行文件、命令或数据库操作。
- 引用检查和 AI 审阅不能证明事实绝对真实，最终内容仍需要你核对。
- 模型连接成功只说明接口可调用，不代表生成质量、余额或长期可用性。
- `data/`、构建产物、密钥和测试产物不会提交到 Git。

## 开发与验证

主要环境：Python 3.12、Node.js 22、React、FastAPI、SQLite、Playwright。

```powershell
. .\scripts\Enter-DevEnvironment.ps1

python -m pytest tests -q
npm run test:web
npm run typecheck
npm run build
```

跨平台使用建议优先走 Docker Compose。本机开发环境说明见 [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)。

## 设计文档

- [产品设计](docs/互联网求职简历Agent产品设计方案.md)
- [Agent 架构](docs/简历Agent架构设计方案.md)
- [Skill 设计](docs/简历Skill设计方案.md)

## License

项目采用 [Apache License 2.0](LICENSE)。第三方组件与字体许可见 [NOTICE](NOTICE)。
