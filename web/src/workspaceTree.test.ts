import { describe, expect, it } from "vitest";
import { GenerationSummary, Summary } from "./api";
import { buildWorkspaceTree } from "./workspaceTree";

const resumes: Summary[] = [
  { id: "r1", revision: 3, origin: "ai", name: "林然", target_role: "后端研发" },
  { id: "r2", revision: 1, origin: "manual", name: "周宁", target_role: "产品经理" },
];

function job(id: string, resume_id: string | null, group_id = id, state = "ready"): GenerationSummary {
  return { id, resume_id, group_id, state, stage: state === "failed" ? "plan" : "done", target_role: "后端研发",
    mode: "generate", adopted_resume_id: resume_id, created_at: "2026-11-14T00:00:00Z", updated_at: "2026-11-14T00:00:00Z" };
}

describe("workspace tree", () => {
  it("groups jobs under a resume and keeps later jobs in the same generation", () => {
    const tree = buildWorkspaceTree(resumes, [
      job("j1", "r1", "batch-1"),
      job("j2", null, "batch-1", "running"),
    ]);

    expect(tree.resumes.map(node => [node.resume.id, node.jobs.map(row => row.id)])).toEqual([
      ["r1", ["j1", "j2"]], ["r2", []],
    ]);
    expect(tree.batches).toEqual([]);
  });

  it("keeps in-flight and failed jobs under a durable generation parent", () => {
    const tree = buildWorkspaceTree(resumes, [
      job("j1", null, "batch-1", "failed"),
      job("j2", null, "batch-1", "running"),
      job("j3", "deleted-resume", "batch-2", "failed"),
    ]);

    expect(tree.batches.map(batch => [batch.label, batch.jobs.map(row => row.id)])).toEqual([
      ["这次生成", ["j1", "j2"]],
      ["这次生成", ["j3"]],
    ]);
    expect(tree.resumes.every(node => node.resume.name)).toBe(true);
  });
});
