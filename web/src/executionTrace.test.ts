import { describe, expect, it } from "vitest";
import { buildAgentTrace } from "./executionTrace";

describe("buildAgentTrace", () => {
  it("turns engine receipts into role-oriented multi-Agent steps", () => {
    const result = buildAgentTrace([
      { step: "plan:0", step_id: "plan:0", next_stage: "draft", state: "running", calls: 1 },
      { step: "draft:0", step_id: "draft:0", next_stage: "review", state: "running", calls: 2 },
      { step: "review:0", step_id: "review:0", next_stage: "done", state: "ready", calls: 3 },
    ], "done", "ready");

    expect(result.map(row => row.agent)).toEqual(["材料分析 Agent", "简历写作 Agent", "事实审阅 Agent"]);
    expect(result.every(row => row.status === "done")).toBe(true);
    expect(result[2].detail).toContain("第 3 次模型调用");
  });

  it("deduplicates persisted receipts and exposes the currently running role", () => {
    const result = buildAgentTrace([
      { step: "plan:0", step_id: "plan:0", next_stage: "draft", state: "running", calls: 1 },
      { step: "plan:0", step_id: "plan:0", next_stage: "draft", state: "running", calls: 1 },
    ], "draft", "running");

    expect(result).toHaveLength(2);
    expect(result[0].status).toBe("done");
    expect(result[1]).toMatchObject({ agent: "简历写作 Agent", status: "running" });
  });
});
