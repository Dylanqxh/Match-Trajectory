# Match-Trajectory

帮助互联网求职者用少量材料，生成、核对并交付简历的开源 AI 工作台。当前为 **M1 开发版**，支持 AI 生成闭环及无需模型的手工编辑。

## 开始使用

1. 双击根目录 `Start-App.cmd`，浏览器打开本机工作台。
2. 点击左下角“模型连接”，选择 DeepSeek，填写 Key，测试并保存。默认模型为 `deepseek-flash`，地址已预设。
3. 填写目标岗位，粘贴已有经历；姓名、联系方式可以稍后补充，JD 可选。不需要公司职级。
4. 确认发送材料后点击“AI 生成简历”；若有补问，可回答，也可跳过。
5. 对照材料查看候选，点击“采用并进入编辑器”。修改后重新审阅，核对当前版本并导出 PDF／Word。

Key 只保留在本次服务内存中，重启需要重新填写。生成可能产生模型费用；失败后继续会保留已用预算。连接测试成功只代表短文本探针通过，不代表完整生成质量得到验证。

姓名与联系方式单独保留在本机；你主动写在材料正文中的隐私也会随正文发送。资料在项目 `data/`，不提交到 Git。

不使用模型时，填写材料后点击“进入编辑器”，仍可编辑、保存、确认和导出。也可使用明确标为虚构的示例体验。

在 PowerShell 中启动：

```powershell
cd D:\AI-VibeCoding\mx_demo\Match-Trajectory
.\scripts\Start-App.ps1
```

运行期间保留终端，按 `Ctrl+C` 停止。当前启动器兼容 Windows 自带 PowerShell；全新克隆先按下文重建环境。便携程序已在开发机验证，仍不是完成干净系统与再分发许可核验的公开发布包。

## 怎样生成与核对

```mermaid
flowchart LR
  A[目标与少量材料] --> B[保存原文与岗位规则]
  B --> C[选材与可跳过的补问]
  C --> D[生成候选]
  D --> E[程序检查与独立审阅]
  E -->|有限修正| D
  E --> F[用户查看并采用]
  F --> G[编辑与重新核对]
  G --> H[确认当前版本并导出]
```

- 五类规则：后端、算法、数据分析、产品、内容／用户运营；其他方向回退通用规则，未声称专项验证。
- 没有 JD 时使用维护的通用画像，不把岗位要求写成个人事实。缺数字或结果时保留已有动作，不编收益。
- 最多一轮三个问题、两轮内容修正、八次模型请求；单请求 45 秒、累计执行 180 秒，等待回答不计时。
- 任务保存在 SQLite。刷新可恢复查看；重启后未完成任务标为中断，不自动重放付费请求。继续需连接原供应商、地址和模型。
- 候选采用为新简历，原简历不覆盖。编辑使 AI 审阅失效；有未解决阻断时只可导出草稿。
- 可以明确选择“自行核对并接管”。已知问题不能直接清空；删除原问题条目会记录解决动作，保留旧报告，复制到新 ID 不算删除解决。复杂误判仍需重审，目前没有填写原文依据的逐问题人工裁决界面。

运行规则位于 [Skill 目录](skills/resume-writing/SKILL.md)，由应用按岗位和阶段加载。模型没有文件、命令或数据库执行权限。

## 当前范围

| 已实现 | 仍需完成或验证 |
| --- | --- |
| 粘贴文字、可选 JD、五方向规则、候选生成与审阅 | 上传解析、个人资料库、原材料修订与全链路失效 |
| 任务状态、补问跳过、取消、明确继续与幂等采用 | 资料删除、备份恢复、完整凭据持久化 |
| 逐版本审阅、用户确认、中文 PDF／可编辑 DOCX | Word／WPS 专项排版与干净系统安装 |
| 本地会话与跨站检查、受限请求、Key 脱敏 | DeepSeek／百炼真实全流程与真实用户效果测试 |

引用存在、规则检查和 AI 审阅不能证明绝对真实；所有事实仍需用户核对。“80% 可用”是待验证目标，当前不宣称达到。

## 开发与验收

```powershell
.\scripts\Test-App.ps1
. .\scripts\Enter-DevEnvironment.ps1
$env:MATCH_TRAJECTORY_FONT_PATH = Join-Path $env:MATCH_TRAJECTORY_ENV_ROOT 'runtimes\fonts\NotoSansCJKsc-Regular.otf'
python tools\smoke_m0.py --output artifacts\manual-smoke
python tools\smoke_m1.py --output artifacts\generation-smoke
.\scripts\Build-Portable.ps1
python tools\smoke_m1.py --executable dist\MatchTrajectory\MatchTrajectory.exe --output artifacts\frozen-generation-smoke
```

2026-11-02：88 项后端测试通过，TypeScript、Vite 和 Ruff 通过。覆盖来源、引用、模型异常、补问、取消迟到结果、重启、存储故障、预算、并发编辑、审阅门禁、旧数据库兼容及文件交付；有一条 Starlette／httpx 上游弃用提示。

浏览器验收中的模型服务为 **本地确定性 HTTP 测试服务**，不会发送到真实供应商；用于检验操作和协议，不能证明真实模型质量。真实供应商全流程、用户试用、干净系统验证目前均为 0。

报告与截图在 `artifacts/`，构建在 `dist/`，均不提交。打包器遇到已有资料目录时拒绝覆盖，可用 `-OutputRoot dist-next` 另选项目内目录。

## 设计与执行

- [产品方案](docs/互联网求职简历Agent产品设计方案.md)
- [Skill 方案](docs/简历Skill设计方案.md)
- [Agent 方案](docs/简历Agent架构设计方案.md)
- [M0 执行记录](docs/superpowers/plans/2026-11-02-resume-m0.md)
- [M1 执行记录](docs/superpowers/plans/2026-11-02-resume-m1.md)

## Windows 开发环境

项目运行时、下载、缓存和临时目录位于工作区旁的 `.dev-environment/`；Python虚拟环境位于本仓库 `.venv/`，npm依赖位于本仓库 `node_modules/`。这些内容都不会提交到Git。

在当前已配置工作区，双击 `Start-DevShell.cmd`，或在PowerShell中执行：

```powershell
. .\scripts\Enter-DevEnvironment.ps1
node --version
python --version
uv --version
npm.cmd run env:verify
```

上述入口只调整当前终端的PATH与缓存变量，不覆盖系统已有Node/Python，不修改全局PowerShell配置。

完整运行时检查：

```powershell
.\scripts\Verify-DevEnvironment.ps1
```

检查覆盖Python依赖、FastAPI/SQLite、React/Vite、Chromium中文PDF、中文/英文OCR、可编辑DOCX与LibreOffice转PDF。产物在忽略的 `artifacts/environment-smoke/`，报告在 `.dev-environment/manifests/runtime-verification.json`。

## 依赖与重建

- Node22、Python3.12、uv；Python依赖由`uv.lock`固定，前端依赖由`package-lock.json`固定。
- Playwright的Python包与Node测试包使用相同版本，浏览器下载到D盘工作区。
- Tesseract与中英数据、Noto中文字体、便携LibreOffice都位于本地环境目录。
- Docker CLI/Compose可独立使用；Docker引擎需要WSL2/系统组件，是否可运行应以本机检查为准。Bootstrap不会自动启用系统功能或重启Windows。

克隆到非C盘目录后，可运行：

```powershell
.\scripts\Bootstrap-DevEnvironment.ps1
```

可选加`-DownloadDockerDesktop`把签名安装包下载到同一环境目录，不执行系统安装。Bootstrap所用便携工具配方位于`tools/bootstrap/`，下载均来自软件官方发布源或其指定发行渠道。

模型API凭据应在后续应用设置中配置，不能提交到仓库。现有SSH私钥仅用于本机Git连接，不复制进项目。
