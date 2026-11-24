import { describe, expect, it } from "vitest";
import { GenerationSummary } from "./api";
import { resolveWorkspaceView } from "./workspaceView";

function job(mode: string): GenerationSummary {
  return {
    id: "job-1", state: "running", stage: "draft", target_role: "后端研发", mode,
    adopted_resume_id: null, resume_id: mode === "recheck" ? "resume-1" : null,
    created_at: "2026-11-24T00:00:00Z", updated_at: "2026-11-24T00:00:00Z",
  };
}

describe("workspace view", () => {
  it("uses intake before a resume or task exists and document after a resume opens", () => {
    expect(resolveWorkspaceView(false, undefined, null)).toBe("intake");
    expect(resolveWorkspaceView(true, undefined, null)).toBe("document");
  });

  it("opens a generate task in its own workspace even while a resume is open", () => {
    expect(resolveWorkspaceView(false, job("generate"), "job-1")).toBe("generation");
    expect(resolveWorkspaceView(true, job("generate"), "job-1")).toBe("generation");
    expect(resolveWorkspaceView(false, undefined, "job-1")).toBe("generation");
  });

  it("keeps a recheck task attached to its document workspace", () => {
    expect(resolveWorkspaceView(true, job("recheck"), "job-1")).toBe("document");
  });
});
