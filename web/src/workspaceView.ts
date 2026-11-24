import { GenerationSummary } from "./api";

export type WorkspaceView = "intake" | "generation" | "document";

export function resolveWorkspaceView(recordOpen: boolean, job: GenerationSummary | undefined, jobId: string | null): WorkspaceView {
  if (jobId && !(recordOpen && job?.mode === "recheck")) return "generation";
  return recordOpen ? "document" : "intake";
}
