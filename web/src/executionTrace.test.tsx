import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AgentExecutionTrace, buildExecutionGraph, EXECUTION_EDGES } from "./executionTrace";

describe("execution graph", () => {
  it("uses only the real stage edges, including the plan loop, wait fork, and revise return", () => {
    const edges = EXECUTION_EDGES.map(edge => edge.join(">"));
    expect(edges).toContain("plan>plan");
    expect(edges).toContain("plan>wait");
    expect(edges).toContain("revise>review");
    expect(edges).not.toContain("plan>supervise");
    expect(new Set(edges).size).toBe(edges.length);
  });

  it("marks an unused supervise node skipped and shows the live review status", () => {
    const graph = buildExecutionGraph([
      { step: "plan:0", next_stage: "draft", state: "running", calls: 1 },
      { step: "draft:0", next_stage: "review", state: "running", calls: 2 },
    ], "review", "running");

    expect(graph.statusLine).toBe("正在审阅");
    expect(graph.nodes.find(node => node.id === "review")?.status).toBe("running");
    expect(graph.nodes.find(node => node.id === "supervise")?.status).toBe("skipped");
    expect(graph.nodes.find(node => node.id === "wait")?.status).toBe("skipped");
    expect(graph.successCount).toBe(2);
    expect(JSON.stringify(graph)).not.toContain("%");
  });

  it("keeps the wait fork and the revise loop as real nodes", () => {
    const waiting = buildExecutionGraph([
      { step: "plan:0", next_stage: "plan", state: "waiting_input", calls: 1 },
    ], "plan", "waiting_input");
    expect(waiting.nodes.find(node => node.id === "wait")?.status).toBe("running");
    expect(waiting.nodes.find(node => node.id === "plan")?.status).toBe("success");
    expect(waiting.statusLine).toBe("正在等待补充");

    const loop = buildExecutionGraph([
      { step: "review:0", next_stage: "revise", state: "running", calls: 3 },
      { step: "revise:0", next_stage: "review", state: "running", calls: 4 },
    ], "review", "running");
    expect(loop.nodes.find(node => node.id === "revise")?.status).toBe("success");
    expect(loop.nodes.find(node => node.id === "review")?.status).toBe("running");
  });

  it("renders the status line and node count without a fake collaboration list", () => {
    const html = renderToStaticMarkup(<AgentExecutionTrace receipts={[]} currentStage="review" jobState="running"/>);
    expect(html).toContain("正在审阅");
    expect(html).toContain("已完成 0 个节点");
    expect(html).toContain("data-stage=\"supervise\"");
    expect(html).toContain("data-status=\"skipped\"");
    expect(html).toContain("计划可回到计划");
    expect(html).not.toContain("多 Agent");
    expect(html).not.toContain("剩余");
    expect(html).not.toContain("%");
  });
});
