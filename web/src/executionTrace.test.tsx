import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AgentExecutionTrace, EXECUTION_EDGES, WAIT_RESUME_EDGES, buildExecutionGraph } from "./executionTrace";

const allowed = [
  "plan>plan", "plan>draft", "plan>wait",
  "draft>draft", "draft>review",
  "review>review", "review>revise", "review>supervise", "review>done",
  "revise>revise", "revise>review",
  "supervise>supervise", "supervise>revise", "supervise>done",
];

describe("execution graph", () => {
  it("draws every allowed relationship, including supervise to done and the plan loop", () => {
    expect(EXECUTION_EDGES.map(edge => edge.join(">")).sort()).toEqual([...allowed].sort());
    expect(WAIT_RESUME_EDGES.map(edge => edge[2])).toEqual(["回答后进入起草", "取消或中断时结束"]);
    expect(WAIT_RESUME_EDGES.some(edge => edge[0] === "wait" && edge[1] === "draft" && edge[2].includes("回答后"))).toBe(true);
  });

  it("names the real roles and keeps an unused supervisor secondary", () => {
    const graph = buildExecutionGraph([
      { step: "plan:0", next_stage: "draft", state: "running", calls: 1 },
      { step: "draft:0", next_stage: "review", state: "running", calls: 2 },
    ], "review", "running");
    expect(graph.statusLine).toBe("正在事实审阅");
    expect(graph.nodes.find(node => node.id === "plan")?.label).toBe("材料分析");
    expect(graph.nodes.find(node => node.id === "draft")?.label).toBe("简历写作");
    expect(graph.nodes.find(node => node.id === "review")?.label).toBe("事实审阅");
    expect(graph.nodes.find(node => node.id === "supervise")?.status).toBe("skipped");

    const html = renderToStaticMarkup(<AgentExecutionTrace receipts={[]} currentStage="review" jobState="running"/>);
    expect(html).toContain("正在事实审阅");
    expect(html).toContain("data-edge=\"plan-plan\"");
    expect(html).toContain("data-edge=\"supervise-done\"");
    expect(html).toContain("data-edge=\"revise-review\"");
    expect(html).toContain("data-edge=\"plan-wait\"");
    expect(html).toContain("data-edge=\"wait-draft\"");
    expect(html).toContain("回答后进入起草");
    expect(html).toContain("主管未启用");
    expect(html).toContain("<svg");
    expect(html).not.toContain("🔎");
    expect(html).not.toContain("多 Agent");
    expect(html).not.toContain("%");
    expect(html).toContain("edge-row branch");
  });
});
