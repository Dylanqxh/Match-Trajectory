# Match-Trajectory

开源 AI 简历工作台。当前已实现 M0：可以录入材料、编辑预览、保存修订、核对并导出中文 PDF／可编辑 DOCX。

**当前不是完整 AI 简历生成产品。** 演示内容为虚构；手工材料按原意进入编辑器，不会自动扩写。模型设置只提供连接探针，尚未验证真实供应商和完整 Agent 流程。

## 在当前工作区启动

双击根目录的 `Start-App.cmd`，或在 PowerShell 执行：

```powershell
.\scripts\Start-App.ps1
```

浏览器会打开本机页面。资料位于项目 `data/`，不进入 Git；关闭服务窗口或按 `Ctrl+C` 停止。保存后可刷新恢复，未保存的编辑应先点击“保存修改”。

该入口使用下文已配置的开发环境；全新克隆需先完成环境重建。便携包目前是本机探针产物，尚未完成干净 Windows 和第三方再分发许可核验，不能视为公开发布版。

## 当前能力与验证边界

| 已实现 | 尚待完成或验证 |
| --- | --- |
| 手工材料与明确标识的虚构示例 | 五方向 Skill、岗位画像与 AI 自动生成 |
| 直接编辑、实时预览、保存、历史记录 | 完整任务中断恢复、资料删除与备份界面 |
| 版本冲突检测，修改后确认失效 | Agent 独立审阅、事实依赖全链路失效 |
| 中文 PDF、可编辑 Word、草稿标识 | 干净 Windows／Docker、Word／WPS 版式专项验证 |
| 本地会话、跨站限制、Key 掩码与会话保存 | 两种供应商的真实模型调用及真实用户试用 |

## 开发验证

```powershell
.\scripts\Test-App.ps1
```

真实浏览器与文件探针（先加载开发环境）：

```powershell
. .\scripts\Enter-DevEnvironment.ps1
$env:MATCH_TRAJECTORY_FONT_PATH = Join-Path $env:MATCH_TRAJECTORY_ENV_ROOT 'runtimes\fonts\NotoSansCJKsc-Regular.otf'
python tools\smoke_m0.py --output artifacts\m0-source-smoke
.\scripts\Build-Portable.ps1
python tools\smoke_m0.py --executable dist\MatchTrajectory\MatchTrajectory.exe --output artifacts\m0-frozen-smoke
```

本地报告与截图位于 `artifacts/`，构建产物位于 `dist/`，均不提交。探针只用构造材料；模拟传输测试不代表真实供应商验证。

2026-11-02 验证记录：35 项后端测试通过（包含实际中文 PDF），TypeScript、Vite 构建和 Ruff 检查通过。已修复未保存材料切换保护、短 Key 掩码、连接探针响应大小／总耗时限制，以及重复导出覆盖旧文件。测试存在一条 Starlette／httpx 上游弃用提示。

最终源码与重新构建的 Windows `.exe` 均通过真实浏览器流程：材料保护、编辑、保存后刷新恢复、PDF／DOCX 下载、模型设置界面和未授权资料访问检查，页面脚本错误为 0。报告分别位于 `artifacts/m0-delivery-source/report.json` 与 `artifacts/m0-delivery-frozen/report.json`。这是当前开发机上的验证；真实模型调用与干净系统验证仍为 0。

## 设计与执行方案

当前设计分为三份，所列业务能力尚待实现：

- [产品方案](docs/互联网求职简历Agent产品设计方案.md)：目标用户、首版范围、交互与验收。
- [Skill 设计](docs/简历Skill设计方案.md)：好简历的标准、选材、写作与岗位差异。
- [Agent 架构](docs/简历Agent架构设计方案.md)：执行流程、工具、版本、恢复与部署。
- [M0 执行方案](docs/superpowers/plans/2026-11-02-resume-m0.md)：本轮任务、测试与后续阶段。

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
