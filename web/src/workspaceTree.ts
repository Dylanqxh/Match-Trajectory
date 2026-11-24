import { GenerationSummary, Summary } from "./api";

export interface ResumeNode {
  resume: Summary;
  jobs: GenerationSummary[];
}

export interface BatchNode {
  id: string;
  label: "这次生成";
  jobs: GenerationSummary[];
}

export interface WorkspaceTree {
  resumes: ResumeNode[];
  batches: BatchNode[];
}

export function buildWorkspaceTree(resumes: Summary[], jobs: GenerationSummary[]): WorkspaceTree {
  const nodes = resumes.map(resume => ({ resume, jobs: [] as GenerationSummary[] }));
  const byResume = new Map(nodes.map(node => [node.resume.id, node]));
  const groups = new Map<string, GenerationSummary[]>();
  for (const job of jobs) {
    const key = job.group_id || job.id;
    groups.set(key, [...(groups.get(key) || []), job]);
  }
  const batches: BatchNode[] = [];
  for (const [key, group] of groups) {
    const resumeIds = [...new Set(group.map(job => job.resume_id).filter((id): id is string => Boolean(id && byResume.has(id))))];
    if (resumeIds.length === 1) {
      const parent = byResume.get(resumeIds[0]);
      if (parent) parent.jobs.push(...group);
      continue;
    }
    if (resumeIds.length > 1) {
      for (const job of group) {
        const parent = job.resume_id ? byResume.get(job.resume_id) : undefined;
        if (parent) parent.jobs.push(job);
        else batches.push({ id: `${key}:${job.id}`, label: "这次生成", jobs: [job] });
      }
      continue;
    }
    batches.push({ id: key, label: "这次生成", jobs: group });
  }
  return { resumes: nodes, batches };
}
