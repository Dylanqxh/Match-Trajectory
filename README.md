# Match-Trajectory

开源 AI 简历工作台。当前仓库先完成开发环境与依赖配置，业务功能按实施计划逐步开发。

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
