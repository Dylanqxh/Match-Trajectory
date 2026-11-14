import { GenerationSummary, Summary } from "./api";

export interface ResumeNode {
  resume: Summary;
  jobs: GenerationSummary[];
}

export interface WorkspaceTree {
  resumes: ResumeNode[];
  inbox: GenerationSummary[];
}

export function buildWorkspaceTree(resumes: Summary[], jobs: GenerationSummary[]): WorkspaceTree {
  const nodes = resumes.map(resume => ({ resume, jobs: [] as GenerationSummary[] }));
  const byId = new Map(nodes.map(node => [node.resume.id, node]));
  const inbox: GenerationSummary[] = [];
  for (const job of jobs) {
    const parent = job.resume_id ? byId.get(job.resume_id) : undefined;
    if (parent) parent.jobs.push(job);
    else inbox.push(job);
  }
  return { resumes: nodes, inbox };
}
