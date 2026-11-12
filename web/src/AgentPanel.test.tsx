import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AgentPanel, AgentProposalCard, sameAgentTarget } from "./AgentPanel";
import { activeAgentTarget } from "./App";
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

  it("renders a before-after proposal with explicit apply and discard actions", () => {
    const html = renderToStaticMarkup(<AgentProposalCard proposal={proposal} busy={false}
      onApply={() => undefined} onDiscard={() => undefined}/>);

    expect(html).toContain("修改前");
    expect(html).toContain("修改后");
    expect(html).toContain("应用为新版本");
    expect(html).toContain("放弃提案");
    expect(html).toContain("500ms");
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
      { id: "job-1", state: "ready", stage: "done", target_role: "后端研发", mode: "generate", adopted_resume_id: "resume-1" },
      null,
      [{ id: "resume-1", revision: 4, origin: "ai", name: "林然", target_role: "后端研发" }],
      false,
    );

    expect(target).toEqual({ type: "resume", id: "resume-1", label: "林然", revision: 4 });
  });
});
