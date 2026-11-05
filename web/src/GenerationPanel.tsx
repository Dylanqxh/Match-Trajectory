import { useEffect, useRef, useState } from "react";
import { api, GenerationJob, Resume } from "./api";
import { ResumeText } from "./ResumeText";
import { QualityReport } from "./QualityReport";

const stages: Record<string, string> = { plan: "整理材料与选材", draft: "起草简历", review: "独立审阅", revise: "修正事实与表达", supervise: "安排本轮修正重点" };
const states: Record<string, string> = { queued: "等待执行", running: "正在处理", waiting_input: "补充一点信息", ready: "候选已保存", failed: "本次处理未完成", interrupted: "任务已中断", cancelled: "已取消" };

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
  return <section className="generation-panel" aria-label="AI 生成任务">
    <div className="panel-title"><div><span className="eyebrow">AI RESUME</span><h2>{job?.draft ? "AI 候选简历" : "生成任务"}</h2></div>
      <button className="text-button" onClick={onClose}>收起任务</button></div>
    {error && <p className="error" role="alert">{error}<button onClick={() => setRefresh(x => x + 1)}>刷新状态</button></p>}
    {!job && !error && <p>正在恢复任务状态…</p>}
    {job && <>
      <div className="generation-state"><strong>{states[job.state] || job.state}</strong><span>{job.input.target_role} · {stages[job.stage]}</span></div>
      {job.error && <p className="notice">{job.error}</p>}
      {job.stop_reason && <p className="notice">{job.stop_reason}</p>}
      {job.service_warning && <p className="notice">{job.service_warning}</p>}
      {job.framework && <p>目前只有目标，没有可用于起草的个人事实。可以先采用空框架，或补充一段真实材料后重新生成。</p>}
      {job.state === "waiting_input" && <div className="questions"><p>最多补问这一轮；想先看一版，可以直接跳过。</p>
        {job.plan?.questions.map(question => <label key={question.id}>{question.text}<textarea aria-label={question.text} rows={2} maxLength={4000}
          value={answers[question.id] || ""} onChange={e => setAnswers({ ...answers, [question.id]: e.target.value })}/></label>)}
        <div className="button-row"><button className="primary" disabled={busy} onClick={() => void act(() => command("answer", { question_group: job.question_group, answers, skip: false }))}>提交补充并生成</button>
          <button className="secondary" disabled={busy} onClick={() => void act(() => command("answer", { question_group: job.question_group, answers: {}, skip: true }))}>跳过，直接生成</button></div></div>}
      {job.draft && <div className="candidate-content">
        <p className="fine">{job.review?.verdict === "pass" && !job.issues.some(i => i.severity === "blocking") ? "事实审阅通过；写作质量见单独报告，仍需核对个人事实。" : "当前候选尚未通过完整审阅，可先作为草稿使用。"}</p>
        {job.draft.education?.map(row => <p key={row.id}><strong>{[row.school, row.degree, row.major].filter(Boolean).join(" · ")}</strong> {[row.start_date, row.end_date].filter(Boolean).join(" — ")}</p>)}
        {job.draft.summary && <p>{job.draft.summary.text}</p>}
        {job.draft.sections.map(section => <section key={section.id}><h3>{section.title}</h3><p className="fine">{[section.organization, section.role, [section.start_date, section.end_date].filter(Boolean).join(" — ")].filter(Boolean).join(" · ")}</p><ul>{section.items.map(item => <li key={item.id}><ResumeText text={item.text} highlights={item.highlights}/></li>)}</ul></section>)}
      </div>}
      {job.draft && <QualityReport report={job.review?.quality} sections={job.draft.sections} education={job.draft.education}/>}
      {job.skill?.role === "general" && <p className="notice">当前使用通用岗位规则，此方向尚未专项验证。</p>}
      {job.issues.length > 0 && <div className="generation-issues"><h3>需要核对的地方</h3>{job.issues.map((issue, index) => <p key={index}>
        <strong>{issue.severity === "blocking" ? "需修正" : "建议"}：</strong>{issue.message}{issue.suggestion && <small>{issue.suggestion}</small>}</p>)}</div>}
      <div className="button-row generation-actions">
        {canAdopt && <button className="primary" disabled={busy} onClick={() => { if (beforeAdopt()) void act(async () => onAdopt(await api<Resume>(`/api/generation-jobs/${jobId}/adopt`, {}))); }}>
          {job.adopted_resume_id ? "打开已采用的简历" : job.framework ? "采用空框架" : "采用并进入编辑器"}</button>}
        {["failed", "interrupted"].includes(job.state) && <button className="secondary" disabled={busy || job.continuation?.allowed === false} onClick={() => void act(() => command("resume"))}>继续任务（保留已用预算）</button>}
        {["queued", "running", "waiting_input"].includes(job.state) && <button className="text-button" disabled={busy} onClick={() => void act(() => command("cancel"))}>取消任务</button>}
      </div>
      {["failed", "interrupted"].includes(job.state) && job.continuation && <p className="fine">{job.continuation.reason}</p>}
      <details className="generation-details"><summary>查看材料依据与执行记录</summary>
        <p>模型请求 {job.calls} / {job.budget_policy?.max_calls ?? 8} 次；内容修正 {job.revisions} / {job.budget_policy?.max_revisions ?? 2} 轮。费用以模型供应商账单为准。</p>
        <p>执行上限 {(job.budget_policy?.total_ms ?? 180000) / 1000} 秒；策略版本 {job.budget_policy?.version || "兼容默认"}。等待回答不计时；次数限制不等于金额上限。</p>
        <p>生成方式：{job.engine === "supervisor" ? "智能修正策略（试用）" : job.engine === "langgraph" ? "分阶段生成" : "兼容流程"}；已保存步骤 {job.step_receipts?.length || 0}。主管请求也计入总次数。</p>
        <p>引用只表示使用了对应用户陈述，不表示系统已客观核实。</p>
        {job.last_diagnostic && <div><strong>上次输出诊断：{({ schema: "字段结构不符合约定", invalid_json: "JSON 格式不完整", empty: "模型返回空白", truncated: "模型输出被截断", incomplete: "模型未完整输出", response_envelope: "响应封装异常", structure: "结构或引用检查未通过" } as Record<string, string>)[job.last_diagnostic.category] || "输出检查未通过"}</strong>
          {job.last_diagnostic.fields.map((field, index) => <p key={index}>{field.path} · {field.rule ? ({ unique_ids: "段落标识重复", body_length: "正文超过长度限制", summary_id: "简介标识不符合约定", review_verdict: "审阅结论与问题列表不一致", question_decision: "补问决策与问题列表不一致", unique_question_ids: "问题标识重复", quality_status: "质量结论与改进动作不一致", quality_dimensions: "质量维度不完整或重复", quality_evidence: "质量意见缺少定位依据", quality_score: "质量评分与动作不一致" } as Record<string, string>)[field.rule] || field.type : field.type}</p>)}</div>}
        <p>当前岗位规则：{job.skill?.role || "旧版"}；规则版本：{job.skill?.version || "未知"}</p>
        {job.skill?.resources && <p>已加载参考：{job.skill.resources.join("、")}</p>}
        {job.evidence.map(item => <p className="source-evidence" key={item.id}><strong>{item.id}</strong> {item.text}</p>)}
      </details>
    </>}
  </section>;
}
