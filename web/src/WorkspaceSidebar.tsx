import { GenerationSummary, Summary } from "./api";
import { buildWorkspaceTree } from "./workspaceTree";

const stateLabels: Record<string, string> = {
  queued: "等待执行", running: "正在生成", waiting_input: "等待补充", ready: "已有结果",
  failed: "生成失败", interrupted: "已中断", cancelled: "已取消",
};
const modeLabels: Record<string, string> = { generate: "生成初稿", recheck: "重新审阅", agent_edit: "Agent 修改" };
const originLabels: Record<string, string> = { ai: "AI", manual: "手工", demo: "演示" };

export interface SidebarVersion { revision: number; origin: string; updated_at?: string }

export function WorkspaceSidebar({ resumes, jobs, versions, selectedResumeId, selectedJobId, selectedVersion, disabled,
  onSelectResume, onDeleteResume, onSelectJob, onDeleteJob, onSelectVersion }: {
  resumes: Summary[]; jobs: GenerationSummary[]; versions?: Record<string, SidebarVersion[]>;
  selectedResumeId: string | null; selectedJobId: string | null;
  selectedVersion?: { resumeId: string; revision: number } | null; disabled: boolean;
  onSelectResume: (resume: Summary) => void; onDeleteResume: (resume: Summary) => void;
  onSelectJob: (job: GenerationSummary) => void; onDeleteJob: (job: GenerationSummary) => void;
  onSelectVersion?: (resumeId: string, revision: number) => void;
}) {
  const tree = buildWorkspaceTree(resumes, jobs);
  const jobRow = (job: GenerationSummary) => <div className="record-nav-row workspace-job nested" key={job.id}>
    <button className={`job-link ${selectedJobId === job.id ? "active" : ""}`} disabled={disabled} onClick={() => onSelectJob(job)}>
      <span>{modeLabels[job.mode] || "生成任务"}</span><small>{job.target_role || "方向待填写"} · {stateLabels[job.state] || "处理中"}</small>
    </button><button className="delete-record" disabled={disabled} aria-label={`删除生成任务 ${job.target_role}`} title="删除任务" onClick={() => onDeleteJob(job)}>×</button>
  </div>;
  const versionRows = (resumeId: string) => {
    const rows = versions?.[resumeId];
    if (!rows?.length) return null;
    return <div className="version-layer" aria-label="版本">
      <div className="workspace-job-summary">版本 {rows.length}</div>
      {rows.map(row => <button type="button" className={`version-link ${selectedVersion?.resumeId === resumeId && selectedVersion.revision === row.revision ? "active" : ""}`}
        key={row.revision} disabled={disabled} onClick={() => onSelectVersion?.(resumeId, row.revision)}>
        v{row.revision} · {originLabels[row.origin] || "版本"}
      </button>)}
    </div>;
  };
  return <section className="workspace-tree" aria-label="简历与任务">
    <div className="nav-heading">简历工作区 <span>{resumes.length}</span></div>
    <nav aria-label="简历工作区">{tree.resumes.map(node => <div className="workspace-resume-node" key={node.resume.id}>
      <div className="record-nav-row"><button className={`resume-link ${selectedResumeId === node.resume.id && !selectedJobId && selectedVersion?.resumeId !== node.resume.id ? "active" : ""}`}
        disabled={disabled} onClick={() => onSelectResume(node.resume)}>
        <span>{node.resume.name || "未命名简历"}</span><small>{node.resume.target_role || "方向待填写"} · v{node.resume.revision}{node.resume.origin === "demo" ? " · 演示" : ""}</small>
      </button><button className="delete-record" disabled={disabled} aria-label={`删除简历 ${node.resume.name || "未命名简历"}`} title="删除简历" onClick={() => onDeleteResume(node.resume)}>×</button></div>
      <div className="workspace-job-summary">相关任务 {node.jobs.length}</div>
      {node.jobs.map(job => jobRow(job))}
      {versionRows(node.resume.id)}
    </div>)}</nav>
    {tree.batches.length > 0 && <nav aria-label="这次生成">{tree.batches.map(batch => <div className="workspace-batch" key={batch.id}>
      <div className="workspace-batch-label">这次生成</div>
      {batch.jobs.map(job => jobRow(job))}
    </div>)}</nav>}
  </section>;
}
