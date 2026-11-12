import { useEffect, useRef, useState } from "react";
import { api, GenerationJob, Resume } from "./api";
import { ResumeText } from "./ResumeText";
import { QualityReport } from "./QualityReport";

const stages: Record<string, string> = { plan: "正在阅读材料", draft: "正在写初稿", review: "正在核对", revise: "正在修改措辞", supervise: "正在决定改哪里" };
const states: Record<string, string> = { queued: "排队中", running: "正在生成", waiting_input: "想再问你一句", ready: "初稿好了", failed: "还没有生成完", interrupted: "中途停了", cancelled: "已取消" };

function calmError(job: GenerationJob): string {
  const raw = job.error || "";
  if (/\/[A-Za-z0-9_<>]+|结构不匹配|脱敏|脱散|JSON|schema/i.test(raw)) {
    return "这次没能把草稿整理成一份完整简历。材料都还在，没有把缺口写进正文。";
  }
  return raw;
}
function resumeDate(value?: string) {
  return (value || "").replace(/((?:19|20|21)\d{2})-(0[1-9]|1[0-2])/g, "$1.$2");
}

export function GenerationPanel({ jobId, onClose, onAdopt, beforeAdopt, onFinished }: {
  jobId: string; onClose: () => void; onAdopt: (row: Resume) => void; beforeAdopt: () => boolean;
  onFinished: (job: GenerationJob) => void;
}) {
  const [job, setJob] = useState<GenerationJob | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [refresh, setRefresh] = useState(0);
  const callbacks = useRef({ onFinished }); callbacks.current = { onFinished };
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    setJob(null); setError(""); setAnswers({});
    async function poll() {
      try {
        const row = await api<GenerationJob>(`/api/generation-jobs/${jobId}`);
        if (stopped) return;
        setJob(row); setError("");
        callbacks.current.onFinished(row);
        if (["queued", "running"].includes(row.state)) timer = setTimeout(() => void poll(), 800);
      } catch (error) { if (!stopped) setError((error as Error).message); }
    }
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [jobId, refresh]);
  async function act(work: () => Promise<void>) {
    setBusy(true); setError("");
    try { await work(); } catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  }
  async function command(action: string, body = {}) {
    await api(`/api/generation-jobs/${jobId}/${action}`, body); setRefresh(x => x + 1);
  }
  const canAdopt = job?.mode === "generate" && ["ready", "failed", "interrupted"].includes(job.state) && (job.draft || job.framework);
  const gaps = job ? [...(job.coverage_notes || []), ...(job.plan?.gaps || [])].filter((note, index, all) => note && all.indexOf(note) === index) : [];
  const failure = job && ["failed", "interrupted"].includes(job.state) ? calmError(job) : "";
  return <section className="generation-panel" aria-label="AI 生成任务">
    <div className="panel-title"><div><span className="eyebrow">初稿</span><h2>{job?.draft ? "看看这版简历" : job?.state === "failed" ? "还没生成完" : "正在生成"}</h2></div>
      <button className="text-button" onClick={onClose}>收起</button></div>
    {error && <p className="error" role="alert">{error}<button onClick={() => setRefresh(x => x + 1)}>刷新</button></p>}
    {!job && !error && <p className="chat-empty">正在打开这次生成…</p>}
    {job && <>
      <div className="generation-state"><strong>{states[job.state] || "处理中"}</strong><span>{job.input.target_role} · {stages[job.stage] || "整理材料"}</span></div>
      {failure && <div className="generation-recover"><strong>{failure}</strong><p>可以回到材料区改一改再生成，也可以再试一次。已经写进正文的内容不会凭空补上缺口。</p></div>}
      {job.stop_reason && !failure && <p className="notice">{job.stop_reason}</p>}
      {job.service_warning && <p className="notice">{job.service_warning}</p>}
      {job.framework && <p>目前只有目标岗位，还没有可以写进简历的经历。可以先进入编辑器自己写，或补充一段真实材料后再生成。</p>}
      {job.state === "waiting_input" && <div className="questions"><p>最多再问这一轮。可以直接回答，也可以跳过，先看完整初稿。</p>
        {job.plan?.questions.map(question => <label key={question.id}>{question.text}<textarea aria-label={question.text} rows={2} maxLength={4000}
          value={answers[question.id] || ""} onChange={e => setAnswers({ ...answers, [question.id]: e.target.value })}/></label>)}
        <div className="button-row"><button className="primary" disabled={busy} onClick={() => void act(() => command("answer", { question_group: job.question_group, answers, skip: false }))}>提交并继续</button>
          <button className="secondary" disabled={busy} onClick={() => void act(() => command("answer", { question_group: job.question_group, answers: {}, skip: true }))}>跳过，先看初稿</button></div></div>}
      {gaps.length > 0 && <div className="gap-notes"><h3>这些先别写进简历</h3><p>材料里还没写清的地方，只放在这里提醒你。不会自动补进正文。</p>
        {gaps.map(note => <p key={note}>{note}</p>)}</div>}
      {job.draft && <div className="candidate-content">
        <p className="fine">{job.review?.verdict === "pass" && !job.issues.some(i => i.severity === "blocking") ? "事实审阅通过；写作质量见单独报告，仍需核对个人事实。" : "当前候选尚未通过完整审阅，可先作为草稿使用。"}</p>
        {job.draft.education?.map(row => <p key={row.id}><strong>{[row.school, row.degree, row.major].filter(Boolean).join(" · ")}</strong> {[resumeDate(row.start_date), resumeDate(row.end_date)].filter(Boolean).join(" — ")}</p>)}
        {job.draft.summary && <p>{resumeDate(job.draft.summary.text)}</p>}
        {job.draft.sections.map(section => <section key={section.id}><h3>{section.title}</h3><p className="fine">{[section.organization, section.role, [resumeDate(section.start_date), resumeDate(section.end_date)].filter(Boolean).join(" — ")].filter(Boolean).join(" · ")}</p><ul>{section.items.map(item => <li key={item.id}><ResumeText text={resumeDate(item.text)} highlights={(item.highlights || []).map(resumeDate)}/></li>)}</ul></section>)}
      </div>}
      {job.draft && <QualityReport report={job.review?.quality} sections={job.draft.sections} education={job.draft.education}/>}
      {job.skill?.role === "general" && <p className="notice">当前使用通用岗位规则，此方向尚未专项验证。</p>}
      {job.issues.length > 0 && <div className="generation-issues"><h3>需要核对的地方</h3>{job.issues.map((issue, index) => <p key={index}>
        <strong>{issue.severity === "blocking" ? "需修正" : "建议"}：</strong>{issue.message}{issue.suggestion && <small>{issue.suggestion}</small>}</p>)}</div>}
      <div className="button-row generation-actions">
        {canAdopt && <button className="primary" disabled={busy} onClick={() => { if (beforeAdopt()) void act(async () => onAdopt(await api<Resume>(`/api/generation-jobs/${jobId}/adopt`, {}))); }}>
          {job.adopted_resume_id ? "打开已采用的简历" : job.framework ? "采用空框架" : "采用并进入编辑器"}</button>}
        {["failed", "interrupted"].includes(job.state) && job.continuation?.allowed !== false && <button className="secondary" disabled={busy} onClick={() => void act(() => command("resume"))}>再试一次</button>}
        {["queued", "running", "waiting_input"].includes(job.state) && <button className="text-button" disabled={busy} onClick={() => void act(() => command("cancel"))}>取消任务</button>}
      </div>
      {["failed", "interrupted"].includes(job.state) && job.continuation && <p className="fine">{job.continuation.reason}</p>}
      <details className="generation-details"><summary>查看用到的原文</summary>
        <p>已请求模型 {job.calls} 次。费用以你选择的模型服务商账单为准。</p>
        <p>这里的引用只说明用了你提供的哪句话，并不表示已经核实过。</p>
        {job.evidence.map(item => <p className="source-evidence" key={item.id}>{item.text}</p>)}
      </details>
    </>}
  </section>;
}
