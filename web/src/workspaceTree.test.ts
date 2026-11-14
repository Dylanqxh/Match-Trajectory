import { describe, expect, it } from "vitest";
import { GenerationSummary, Summary } from "./api";
import { buildWorkspaceTree } from "./workspaceTree";

const resumes: Summary[] = [
  { id: "r1", revision: 3, origin: "ai", name: "林然", target_role: "后端研发" },
  { id: "r2", revision: 1, origin: "manual", name: "周宁", target_role: "产品经理" },
];

function job(id: string, resume_id: string | null): GenerationSummary {
  return { id, resume_id, state: "ready", stage: "done", target_role: "后端研发", mode: "generate",
    adopted_resume_id: resume_id, created_at: `2026-11-14T00:00:0${id.slice(-1)}Z`, updated_at: "2026-11-14T00:00:00Z" };
}

describe("workspace tree", () => {
  it("groups multiple jobs under one resume and keeps empty resumes", () => {
    const tree = buildWorkspaceTree(resumes, [job("j1", "r1"), job("j2", "r1")]);

    expect(tree.resumes.map(node => [node.resume.id, node.jobs.map(row => row.id)])).toEqual([
      ["r1", ["j1", "j2"]], ["r2", []],
    ]);
    expect(tree.inbox).toEqual([]);
  });

  it("keeps unmatched and legacy-parent jobs in a visible inbox", () => {
    const tree = buildWorkspaceTree(resumes, [job("j1", null), job("j2", "deleted-resume")]);

    expect(tree.inbox.map(row => row.id)).toEqual(["j1", "j2"]);
  });
});
