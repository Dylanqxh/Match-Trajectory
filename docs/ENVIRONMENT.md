# 本地开发环境交付记录

配置日期：2026-10-23。操作系统：Windows x64。此记录证明开发环境可用，不表示简历业务功能已开发完成。

## 存放位置

- 项目：工作区内`Match-Trajectory/`。
- 便携运行时、下载、缓存、临时文件、浏览器、OCR、字体、Office和Docker安装包：同一工作区内`.dev-environment/`。
- Python依赖：项目`.venv/`；前端依赖：项目`node_modules/`。
- 使用`Start-DevShell.cmd`或点加载`scripts/Enter-DevEnvironment.ps1`，缓存才会采用本项目的D盘设置；没有修改系统PATH或覆盖旧Node/Python。

## 已配置组件

| 组件 | 本次版本 | 状态 |
| --- | --- | --- |
| Node.js | 22.23.4 | 便携版，React/Vite检查通过 |
| Python | 3.12.15 | uv管理，项目虚拟环境可用 |
| uv | 0.13.5 | 依赖锁定与一致性检查通过 |
| React / Vite / TypeScript | 19.3.1 / 7.3.7 / 5.9.3 | 依赖已安装并锁定 |
| FastAPI / SQLAlchemy | 0.161.1 / 2.1.6 | API与SQLite事务冒烟测试通过 |
| Playwright | 1.64.1 | Python/Node测试包同版本，Chromium已下载 |
| Tesseract | 5.5.3 | chi_sim+eng识别测试通过 |
| Noto Sans CJK SC | 本地字体文件及许可 | Chromium中文PDF通过 |
| LibreOffice | 26.2.4.2 | 便携版，可编辑DOCX转PDF通过 |
| Docker CLI / Compose | 29.9.2 / 5.6.1 | 客户端版本测试通过 |
| Docker Desktop | 已下载官方签名安装包 | 未安装/未启动引擎，缺可用WSL2条件 |

Python完整依赖在`uv.lock`，Node完整依赖在`package-lock.json`。精简机器可读版本记录在`tools/environment-versions.json`。

## 实际验证结果

1. Python关键依赖导入与版本获取：通过。
2. FastAPI TestClient与SQLite真实写入/读取：通过。
3. Node22、React服务端渲染、Vite TypeScript转换：通过。
4. Chromium生成一页中文PDF并回抽取中文与数字：通过，已查看实际PDF页图。
5. 合成图片中文/英文OCR：识别出“环境测试 数据开发 12345”。
6. python-docx生成可编辑段落，LibreOffice转PDF并回抽取中文：通过，已查看实际PDF页图。

另外，`uv pip check`通过，`npm ls --depth=0`通过；本次生产依赖npm audit为0项已报告漏洞。测试中Starlette对httpx的兼容路径有弃用提示，当前API检查通过，未来升级按锁文件重新验证。

## GitHub验证

SSH已认证为仓库所有者账号；既有私钥只交由ssh使用，没有复制到项目。GitHub主机key按官方发布值验证，known_hosts保存在本地环境目录。

测试分支：`chore/environment-bootstrap`。首个测试提交：`904d1d904a25207dce1b6e055066cbcb6d557a6a`；测试文件：`tests/environment/git-push-smoke.txt`。配置文件随后也提交到同一分支。提交后用`git ls-remote`核对远端HEAD，不靠本地commit成功推定上传成功。

## Docker引擎的明确边界

当前可运行Docker/Compose客户端，但没有已验证的Docker服务端。检测到的WSL命令不提供可用的新版本WSL2运行条件；没有为安装Docker而启用Windows功能、安装WSL或重启系统。

用户要求不增加C盘环境占用，因此仅把Desktop安装包下载到D盘并验证Docker官方签名。未来启用引擎需要单独处理Windows/WSL系统组件；应用程序目录及Linux数据盘可指定D盘，但不能承诺系统组件完全不写C盘。原生React/Python开发、OCR和文件转换不依赖本机Docker引擎。

## 重跑检查

```powershell
. .\scripts\Enter-DevEnvironment.ps1
.\scripts\Verify-DevEnvironment.ps1
```

本机详细报告位于`.dev-environment/manifests/runtime-verification.json`，测试产物位于项目`artifacts/environment-smoke/`。产物、安装包、虚拟环境、密钥和缓存都不进入Git。
