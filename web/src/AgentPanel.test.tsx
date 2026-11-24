import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AgentPanel, AgentProposalCard, sameAgentTarget } from "./AgentPanel";
import { activeAgentTarget, preferredAgentCollapsed } from "./App";
import { AgentProposal } from "./api";

const proposal: AgentProposal = {
  id: "proposal-1",
  state: "ready",
  base_revision: 3,
  changes: [{
    item_id: "query",
    before: "使用 Java 完成查询接口。",
    after: "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。",
    reason: "突出原文中的性能结果",
    evidence_ids: ["e1"],
  }],
  issues: [],
};

describe("AgentPanel", () => {
  it("requires a selected resume or generated candidate instead of collecting material", () => {
    const html = renderToStaticMarkup(<AgentPanel target={null} modelReady={true}
      onOpenSettings={() => undefined} onApplied={() => undefined}/>);

    expect(html).toContain("先选择一份简历或生成任务");
    expect(html).not.toContain("上传简历");
    expect(html).not.toContain("收集材料");
  });

  it("shows the exact resume revision the Agent will edit", () => {
    const html = renderToStaticMarkup(<AgentPanel
      target={{ type: "resume", id: "resume-1", label: "林然后端简历", revision: 3 }}
      modelReady={true} onOpenSettings={() => undefined} onApplied={() => undefined}/>);

    expect(html).toContain("林然后端简历");
    expect(html).toContain("v3");
    expect(html).toContain("告诉 Agent 想怎么改");
  });

  it("renders an automatically saved before-after result without confirmation actions", () => {
    const html = renderToStaticMarkup(<AgentProposalCard proposal={{ ...proposal, state: "applied" }}/>);

    expect(html).toContain("修改前");
    expect(html).toContain("修改后");
    expect(html).toContain("已自动保存");
    expect(html).not.toContain("应用为新版本");
    expect(html).not.toContain("放弃提案");
    expect(html).toContain("500ms");
  });

  it("shows presentation-only highlight changes as an applied edit", () => {
    const html = renderToStaticMarkup(<AgentProposalCard proposal={{ ...proposal, state: "applied", changes: [{
      item_id: "query", before: "准确率达到 99.8%", after: "准确率达到 99.8%", reason: "突出量化结果", evidence_ids: [],
      presentation_before: [], presentation_after: ["99.8%"],
    }] }}/>);

    expect(html).toContain("加粗重点");
    expect(html).toContain("99.8%");
  });

  it("explains that a risky change was not saved and allows a new instruction", () => {
    const html = renderToStaticMarkup(<AgentProposalCard proposal={{ ...proposal, state: "blocked", issues: [{
      item_id: "query", severity: "blocking", code: "reference", message: "缺少原文依据",
      suggestion: "补充材料",
    }] }}/>);

    expect(html).toContain("未保存");
    expect(html).toContain("缺少原文依据");
    expect(html).not.toContain("应用为新版本");
  });

  it("rejects a response that belongs to the previously selected target", () => {
    expect(sameAgentTarget(
      { type: "resume", id: "resume-1", label: "A", revision: 1 },
      { type: "resume", id: "resume-2", label: "B", revision: 1 },
    )).toBe(false);
    expect(sameAgentTarget(
      { type: "resume", id: "resume-1", label: "A", revision: 1 },
      { type: "resume", id: "resume-1", label: "A", revision: 1 },
    )).toBe(true);
    expect(sameAgentTarget(
      { type: "job", id: "job-1", label: "后端工程师", revision: 0, state: "queued" },
      { type: "job", id: "job-1", label: "后端工程师", revision: 0, state: "ready" },
    )).toBe(false);
  });

  it("binds an adopted generation task to the materialized resume version", () => {
    const target = activeAgentTarget(
      { id: "job-1", state: "ready", stage: "done", target_role: "后端研发", mode: "generate", adopted_resume_id: "resume-1",
        resume_id: "resume-1", created_at: "2026-11-14T00:00:00Z", updated_at: "2026-11-14T00:00:00Z" },
      null,
      [{ id: "resume-1", revision: 4, origin: "ai", name: "林然", target_role: "后端研发" }],
      false,
    );

    expect(target).toEqual({ type: "resume", id: "resume-1", label: "林然", revision: 4 });
  });

  it("keeps the Agent collapsed by default so the resume workspace stays wide", () => {
    expect(preferredAgentCollapsed(false, null)).toBe(true);
    expect(preferredAgentCollapsed(true, null)).toBe(true);
    expect(preferredAgentCollapsed(true, false)).toBe(false);
    expect(preferredAgentCollapsed(true, true)).toBe(true);

    const collapsed = renderToStaticMarkup(<AgentPanel target={null} collapsed modelReady={false}
      onOpenSettings={() => undefined} onApplied={() => undefined} onToggle={() => undefined}/>);
    expect(collapsed).toContain("未选择目标");
    expect(collapsed).toContain("简历 Agent");
    expect(collapsed).not.toContain("告诉 Agent 想怎么改");
    expect(collapsed).not.toContain("上传简历");

    const expanded = renderToStaticMarkup(<AgentPanel target={null} collapsed={false} modelReady={true}
      onOpenSettings={() => undefined} onApplied={() => undefined}/>);
    expect(expanded).toContain("先选择一份简历或生成任务");
  });

  it("states the real scope-lock boundary and a scope rejection", () => {
    const html = renderToStaticMarkup(<AgentPanel target={{ type: "resume", id: "resume-1", label: "林然", revision: 1 }}
      modelReady={true} onOpenSettings={() => undefined} onApplied={() => undefined}/>);
    expect(html).toContain("只改加粗");
    expect(html).toContain("不能保证任意自然语言修改都会成功");

    const blocked = renderToStaticMarkup(<AgentProposalCard proposal={{ ...proposal, state: "blocked", issues: [{
      item_id: "document", severity: "blocking", code: "scope", message: "只改加粗不能改正文、数字、字段或顺序，因此没有保存。",
    }] }}/>);
    expect(blocked).toContain("超出本次修改范围");
    expect(blocked).toContain("因此没有保存");
  });
});
