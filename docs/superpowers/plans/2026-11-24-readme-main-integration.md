# README 与主分支集成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化开源访客的首次阅读与启动体验，并把当前功能分支安全合并到本地默认分支 `main`。

**Architecture:** 只调整 README 的信息结构和文字，不改动应用代码或媒体引用。所有文档修改先提交到 `codex/resume-workflow-ux`，再以 fast-forward 方式集成到 `main`，最后在合并结果上运行完整验证。

**Tech Stack:** Markdown、Git、PowerShell、Node.js 22、Python 3.12、Vitest、TypeScript、Vite、pytest

**Spec:** `docs/superpowers/specs/2026-11-24-readme-main-integration-design.md`

## Global Constraints

- 不查看、不生成、不修改图片、音频或视频资源；现有 README 媒体引用保持原文。
- 不修改产品功能、接口或依赖。
- 不暂存、修改或删除 `docs/项目总体设计与关键实现分析.md`。
- 只合并到本地 `main`，不推送远端。
- 不把自动化测试结果表述为真实用户效果验证。

## Review Focus

- 新访客能否先看到产品定位、适用范围和启动前提，而不是先理解内部架构。
- Windows 命令是否只承诺“已配置环境”，并把首次配置指向真实环境文档。
- Docker 命令、端口、数据卷和删除数据的警告是否与 `compose.yaml` 一致。
- 用户流程是否准确对应材料、生成、文档三个工作区及双材料入口、三种文档视图。
- 所有相对链接、脚本和 npm 命令是否真实存在且能运行。

---

### Task 1: 重构 README 信息层级

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: 当前仓库启动脚本、Compose 配置、界面文案和 2026-11-24 工作流 UX 设计
- Produces: 面向首次访问者的产品说明、启动指南、使用流程、能力边界和开发验证入口

- [ ] **Step 1: 重写 README 文本结构**

保留徽章和三个现有媒体引用原文；重排定位、快速启动、第一次使用、核心能力、边界、模型、安全、开发验证和设计文档。

- [ ] **Step 2: 检查路径、命令与媒体引用边界**

Run: `git diff -- README.md`，并以 `Test-Path` 校验 README 中新增或保留的本地链接。

Expected: 只有文字和章节顺序变化；媒体引用行与修改前完全一致；所有本地目标存在。

- [ ] **Step 3: 提交 README 与过程文档**

Run: `git add README.md docs/superpowers/specs/2026-11-24-readme-main-integration-design.md docs/superpowers/plans/2026-11-24-readme-main-integration.md && git commit -m "docs: improve onboarding and workflow guide"`

Expected: 新提交只包含这三个文件，未跟踪用户文档仍未暂存。

### Task 2: 合并到默认分支并验证

**Files:**
- Modify: Git ref `main`
- Test: `tools/test-document-layout.mjs`
- Test: `web/src/**/*.test.*`
- Test: `tests/**/*.py`

**Interfaces:**
- Consumes: Task 1 的功能分支提交
- Produces: 指向完整功能历史的本地 `main`

- [ ] **Step 1: 使用 fast-forward 合并**

Run: `git switch main`；`git merge --ff-only codex/resume-workflow-ux`

Expected: `main` 快进到功能分支最新提交，不产生额外合并提交。

- [ ] **Step 2: 运行前端与布局验证**

Run: `npm run test:layout`；`npm run test:web`；`npm run typecheck`；`npm run build`

Expected: 布局测试、全部前端测试、类型检查和生产构建通过。

- [ ] **Step 3: 运行后端回归**

Run: 在项目开发环境中执行 `python -m pytest tests -q -p no:cacheprovider --basetemp <repository-local-temp-dir>`。

Expected: 全部后端测试通过。

- [ ] **Step 4: 检查最终分支和工作区**

Run: `git status --short --branch`；`git log -1 --oneline --decorate`；`git diff origin/main..main --stat`

Expected: 当前分支为 `main`，已跟踪文件干净，未跟踪用户文档保持不变，本地领先远端且尚未推送。
