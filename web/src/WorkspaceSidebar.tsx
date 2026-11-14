import { GenerationSummary, Summary } from "./api";
import { buildWorkspaceTree } from "./workspaceTree";

const stateLabels: Record<string, string> = {
  queued: "等待执行", running: "正在生成", waiting_input: "等待补充", ready: "已有结果",
  failed: "可查看或继续", interrupted: "已中断", cancelled: "已取消",
};
const modeLabels: Record<string, string> = { generate: "生成初稿", recheck: "重新审阅", agent_edit: "Agent 修改" };

export function WorkspaceSidebar({ resumes, jobs, selectedResumeId, selectedJobId, disabled,
  onSelectResume, onDeleteResume, onSelectJob, onDeleteJob }: {
  resumes: Summary[]; jobs: GenerationSummary[]; selectedResumeId: string | null; selectedJobId: string | null; disabled: boolean;
  onSelectResume: (resume: Summary) => void; onDeleteResume: (resume: Summary) => void;
  onSelectJob: (job: GenerationSummary) => void; onDeleteJob: (job: GenerationSummary) => void;
}) {
  const tree = buildWorkspaceTree(resumes, jobs);
  const jobRow = (job: GenerationSummary, nested = false) => <div className={`record-nav-row workspace-job ${nested ? "nested" : ""}`} key={job.id}>
    <button className={`resume-link ${selectedJobId === job.id ? "active" : ""}`} disabled={disabled} onClick={() => onSelectJob(job)}>
      <span>{modeLabels[job.mode] || "生成任务"}</span><small>{job.target_role || "方向待填写"} · {stateLabels[job.state] || "处理中"}</small>
    </button><button className="delete-record" disabled={disabled} aria-label={`删除生成任务 ${job.target_role}`} onClick={() => onDeleteJob(job)}>删除</button>
  </div>;
  return <section className="workspace-tree" aria-label="简历与任务">
    <div className="nav-heading">简历工作区 <span>{resumes.length}</span></div>
    <nav aria-label="简历工作区">{tree.resumes.map(node => <div className="workspace-resume-node" key={node.resume.id}>
      <div className="record-nav-row"><button className={`resume-link ${selectedResumeId === node.resume.id && !selectedJobId ? "active" : ""}`}
        disabled={disabled} onClick={() => onSelectResume(node.resume)}>
        <span>{node.resume.name || "未命名简历"}</span><small>{node.resume.target_role || "方向待填写"} · v{node.resume.revision}{node.resume.origin === "demo" ? " · 演示" : ""}</small>
      </button><button className="delete-record" disabled={disabled} aria-label={`删除简历 ${node.resume.name || "未命名简历"}`} onClick={() => onDeleteResume(node.resume)}>删除</button></div>
      <div className="workspace-job-summary">相关任务 {node.jobs.length}</div>
      {node.jobs.map(job => jobRow(job, true))}
    </div>)}</nav>
    {tree.inbox.length > 0 && <><div className="nav-heading workspace-inbox-heading">未归档任务 <span>{tree.inbox.length}</span></div>
      <nav aria-label="未归档任务">{tree.inbox.map(job => jobRow(job))}</nav></>}
  </section>;
}
