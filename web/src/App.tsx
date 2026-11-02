import { useEffect, useRef, useState } from "react";
import { api, clean, Content, emptyContent, GenerationJob, GenerationSummary, request, Resume, Summary, unresolvedBlocking } from "./api";
import { ModelSettings } from "./ModelSettings";
import { GenerationPanel } from "./GenerationPanel";
import { ManualReview } from "./ManualReview";
import { EducationFields } from "./EducationFields";
import { ExperienceFields } from "./ExperienceFields";

const roles = ["后端研发", "Agent／RAG 应用开发实习", "推荐算法", "NLP 算法", "数据分析", "产品经理", "内容／用户运营"];

export default function App() {
  const [list, setList] = useState<Summary[]>([]);
  const [record, setRecord] = useState<Resume | null>(null);
  const [content, setContent] = useState<Content>(emptyContent);
  const [source, setSource] = useState("");
  const [jd, setJd] = useState("");
  const [sendMaterials, setSendMaterials] = useState(false);
  const [allowQuestions, setAllowQuestions] = useState(true);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobs, setJobs] = useState<GenerationSummary[]>([]);
  const [modelStatus, setModelStatus] = useState("尚未连接模型");
  const generationRequest = useRef<{ key: string; id: string } | null>(null);
  const savedInput = useRef("");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("正在连接本地工作台…");
  const [error, setError] = useState("");
  const [settings, setSettings] = useState(false);
  const [resolution, setResolution] = useState<{ record: Resume; issueIndex: number } | null>(null);
  const [history, setHistory] = useState<Resume[] | null>(null);
  const [preview, setPreview] = useState("");
  const [scale, setScale] = useState(0.8);
  const previewBox = useRef<HTMLDivElement>(null);
  const formKey = JSON.stringify({ name: content.name, target_role: content.target_role, contact: content.contact, education: content.education, source, jd });
  const hasUnsavedChanges = dirty || (!record && Boolean(source.trim() || jd.trim() || content.name.trim() || content.target_role.trim() || content.contact.trim()
    || (content.education || []).some(e => e.school.trim() || e.degree.trim() || e.major.trim() || e.start_date?.trim() || e.end_date?.trim())) && formKey !== savedInput.current);

  function adopt(row: Resume) {
    setRecord(row); setContent(row.content); setDirty(false); setError("");
    localStorage.setItem("mt_resume_id", row.id);
    setStatus(`已载入版本 ${row.revision}`);
  }
  async function refreshList() { setList(await api<Summary[]>("/api/resumes")); }
  async function refreshJobs() { setJobs(await api<GenerationSummary[]>("/api/generation-jobs")); }
  async function refreshModel() {
    const value = await api<{ configured: boolean; model?: string }>("/api/model-settings");
    setModelStatus(value.configured ? `已连接 ${value.model}` : "尚未连接模型");
  }
  function showJob(id: string | null) {
    setJobId(id);
    if (id) localStorage.setItem("mt_job_id", id); else localStorage.removeItem("mt_job_id");
  }
  async function action(work: () => Promise<void>) {
    setBusy(true); setError("");
    try { await work(); } catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  }
  useEffect(() => {
    void action(async () => {
      await api("/api/session");
      const rows = await api<Summary[]>("/api/resumes"); setList(rows);
      const previous = localStorage.getItem("mt_resume_id");
      if (previous && rows.some(row => row.id === previous)) adopt(await api<Resume>(`/api/resumes/${previous}`));
      else setStatus("本地工作台已就绪");
      const recentJobs = await api<GenerationSummary[]>("/api/generation-jobs"); setJobs(recentJobs);
      const previousJob = localStorage.getItem("mt_job_id");
      if (previousJob && recentJobs.some(row => row.id === previousJob)) setJobId(previousJob);
      await refreshModel();
    });
  }, []);
  useEffect(() => {
    if (!record) { setPreview(""); return; }
    const abort = new AbortController();
    const timer = setTimeout(() => {
      void request(`/api/preview?demo=${record.origin === "demo"}`, {
        method: "POST", body: JSON.stringify(clean(content)), signal: abort.signal,
      }).then(r => r.text()).then(html => setPreview(html)).catch(() => {});
    }, 250);
    return () => { clearTimeout(timer); abort.abort(); };
  }, [content, record?.id, record?.origin]);
  useEffect(() => {
    const element = previewBox.current;
    if (!element) return;
    const observer = new ResizeObserver(entries => setScale(Math.min(1, entries[0].contentRect.width / 794)));
    observer.observe(element); return () => observer.disconnect();
  }, [record?.id]);
  useEffect(() => {
    function guard(event: BeforeUnloadEvent) { if (hasUnsavedChanges) event.preventDefault(); }
    window.addEventListener("beforeunload", guard); return () => window.removeEventListener("beforeunload", guard);
  }, [hasUnsavedChanges]);

  function edit(next: Content) { setContent(next); setDirty(true); setStatus("有未保存的修改"); }
  function canSwitch() { return !hasUnsavedChanges || window.confirm("当前修改尚未保存，确定切换？"); }
  async function save(): Promise<Resume> {
    if (!record) throw new Error("请先创建简历");
    if (!dirty) return record;
    const row = await api<Resume>(`/api/resumes/${record.id}`, { expected_revision: record.revision, content: clean(content) }, "PUT");
    adopt(row); await refreshList(); setStatus(`已保存版本 ${row.revision}`); return row;
  }
  async function generate() {
    await action(async () => {
      if (!content.name.trim() || !content.contact.trim() || !content.target_role.trim()) throw new Error("请先填写姓名、联系方式和目标岗位");
      if ((source.trim() || jd.trim()) && !sendMaterials) throw new Error("请先确认将材料和 JD 发送给所选模型服务");
      const payload = { name: content.name, contact: content.contact, target_role: content.target_role,
        education: clean(content).education, source_text: source, jd, allow_questions: allowQuestions, send_materials: sendMaterials };
      const key = JSON.stringify(payload);
      if (generationRequest.current?.key !== key) generationRequest.current = { key, id: crypto.randomUUID() };
      const job = await api<GenerationJob>("/api/generation-jobs", { ...payload, request_id: generationRequest.current.id });
      savedInput.current = formKey; showJob(job.id); await refreshJobs(); setStatus("材料已保存到生成任务，可以刷新后继续查看");
    });
  }
  async function recheck() {
    await action(async () => {
      const row = await save();
      const job = await api<GenerationJob>(`/api/resumes/${row.id}/review`, { expected_revision: row.revision, request_id: crypto.randomUUID() });
      showJob(job.id); await refreshJobs(); setStatus("已提交当前版本审阅，原文保留");
    });
  }
  async function takeover() {
    await action(async () => {
      const row = await save();
      const index = row.ai?.issues.findIndex(unresolvedBlocking) ?? -1;
      if (index >= 0) { setResolution({ record: row, issueIndex: index }); return; }
      if (!window.confirm("我已自行核对当前正文中的全部个人事实。接管后保留 AI 来源和旧报告，标记为用户自行核对。确定继续？")) return;
      adopt(await api<Resume>(`/api/resumes/${row.id}/takeover`, { expected_revision: row.revision, acknowledged: true }));
      setStatus("已标记为用户自行核对，导出前仍需确认当前版本");
    });
  }
  async function resolveIssue(index: number) {
    await action(async () => {
      const row = await save();
      const issue = row.ai?.issues[index];
      if (!issue || !unresolvedBlocking(issue)) { setStatus("这项问题已处理，请查看当前版本"); return; }
      setResolution({ record: row, issueIndex: index });
    });
  }
  function jobUpdated(job: GenerationJob) {
    if (["ready", "failed", "interrupted", "cancelled", "waiting_input"].includes(job.state)) void refreshJobs().catch(() => {});
    if (job.mode === "recheck" && job.state === "ready" && record && !dirty) {
      void api<Resume>(`/api/resumes/${record.id}`).then(row => { setRecord(row); setStatus("当前版本审阅已完成，请查看结果"); }).catch(() => {});
    }
  }
  async function download(format: "pdf" | "docx", draft = false) {
    await action(async () => {
      let row = await save();
      if (!draft) row = await api<Resume>(`/api/resumes/${row.id}/confirm`, { expected_revision: row.revision });
      setRecord(row);
      const response = await request(`/api/resumes/${row.id}/exports`, {
        method: "POST", body: JSON.stringify({ format, expected_revision: row.revision, draft }),
      });
      const blob = await response.blob(); const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a"); anchor.href = url;
      anchor.download = `resume-r${row.revision}${draft ? "-draft" : ""}.${format}`;
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      setStatus(`${format.toUpperCase()} 已导出 · 版本 ${row.revision}`);
    });
  }
  return <div className="app-shell">
    <aside className="sidebar" inert={resolution ? true : undefined}>
      <div className="brand"><span className="brand-icon">M</span><div>Match-Trajectory<small>求职简历工作台</small></div></div>
      <button className="new-button" disabled={busy} onClick={() => {
        if (canSwitch()) { setRecord(null); setContent(emptyContent); setSource(""); setJd(""); setSendMaterials(false); setDirty(false); savedInput.current = ""; generationRequest.current = null; showJob(null); localStorage.removeItem("mt_resume_id"); }
      }}>＋ 新建简历</button>
      <div className="nav-heading">我的简历 <span>{list.length}</span></div>
      <nav aria-label="我的简历">{list.map(row => <button key={row.id} className={`resume-link ${record?.id === row.id ? "active" : ""}`} disabled={busy}
        onClick={() => { if (canSwitch()) void action(async () => adopt(await api<Resume>(`/api/resumes/${row.id}`))); }}>
        <span>{row.name || "未命名简历"}</span><small>{row.target_role || "方向待填写"} · v{row.revision}{row.origin === "demo" ? " · 演示" : ""}</small>
      </button>)}</nav>
      {jobs.length > 0 && <><div className="nav-heading">生成任务</div><nav aria-label="生成任务">{jobs.slice(0, 6).map(job => <button className={`resume-link ${jobId === job.id ? "active" : ""}`} key={job.id}
        onClick={() => showJob(job.id)}><span>{job.target_role}</span><small>{({ queued: "等待执行", running: "正在生成", waiting_input: "等待补充", ready: "已有结果", failed: "可查看或继续", interrupted: "已中断", cancelled: "已取消" } as Record<string, string>)[job.state]}</small></button>)}</nav></>}
      <div className="sidebar-bottom"><button disabled={busy} onClick={() => setSettings(true)}>⚙ 模型连接</button>
        <div className="local-note"><span className="status-dot"/>资料保存在本机<small>M1 · AI 生成与核对交付</small></div></div>
    </aside>
    <main className="main-area" inert={resolution ? true : undefined}>
      <header className="topbar"><div><span className="eyebrow">RESUME WORKSPACE</span><h1>简历工作台</h1></div>
        <span className="stage-chip">生成与交付 · M1</span></header>
      <div className="feedback" role="status">{busy ? "正在处理，请稍候…" : status}</div>
      {error && <div className="error" role="alert">{error}<button onClick={() => setError("")} aria-label="关闭错误">×</button></div>}
      {jobId && <GenerationPanel jobId={jobId} onClose={() => showJob(null)} beforeAdopt={canSwitch}
        onAdopt={row => { adopt(row); showJob(null); void refreshList(); }} onFinished={jobUpdated}/>}
      {!record ? <section className="start-layout">
        <div className="welcome"><span className="eyebrow">从你已经做过的事开始</span><h2>把经历写清楚，<br/>让价值被看见。</h2>
          <p>说清想投什么岗位，放入已有经历。AI 帮你选重点、整理表达，你来核对事实。</p>
          <div className="feature-line"><span>01 提供线索</span><span>02 生成与核对</span><span>03 编辑导出</span></div>
          <button className="secondary" disabled={busy} onClick={() => { if (canSwitch()) void action(async () => {
            adopt(await api<Resume>("/api/demo", {})); await refreshList();
          }); }}>先用虚构示例体验 →</button>
          <p className="fine">不用准备完整档案，也不用提供 JD。材料少时可以先生成草稿，缺少的经历不会凭空补造。</p>
        </div>
        <form className="material-card" onSubmit={event => { event.preventDefault(); void generate(); }}><fieldset disabled={busy}>
          <h3>开始整理你的简历</h3><label>姓名<input required value={content.name} maxLength={80} onChange={e => setContent({ ...content, name: e.target.value })} placeholder="如何称呼你"/></label>
          <label>目标岗位<input required list="roles" value={content.target_role} maxLength={80} onChange={e => setContent({ ...content, target_role: e.target.value })} placeholder="例如 Java 后端、算法、产品经理"/><datalist id="roles">{roles.map(role => <option value={role} key={role}/>)}</datalist></label>
          <label>联系方式<input required value={content.contact} maxLength={300} onChange={e => setContent({ ...content, contact: e.target.value })} placeholder="必填：手机号或邮箱，可用求职专用联系方式"/></label>
          <p className="fine">姓名、联系方式和目标岗位必填；学校与经历时间按事实填写，未知留空。</p>
          <EducationFields rows={content.education || []} onChange={education => setContent({ ...content, education })}/>
          <label>现有材料<textarea aria-label="现有材料" rows={7} maxLength={20000} value={source} onChange={e => setSource(e.target.value)} placeholder="课程、项目、工作、作品或活动都可以。写自己做了什么、用什么方法、有何交付或验证；不完整也可以。"/></label>
          <div className="field-help">{source.length.toLocaleString()} / 20,000 字 · 本机保存</div>
          <details><summary>有具体岗位 JD？可选填写</summary><label>岗位 JD<textarea aria-label="岗位 JD" rows={4} maxLength={8000} value={jd} onChange={e => setJd(e.target.value)}/></label></details>
          <label className="checkbox-label"><input type="checkbox" checked={allowQuestions} onChange={e => setAllowQuestions(e.target.checked)}/>允许最多一轮补问（可跳过）</label>
          <label className="checkbox-label"><input type="checkbox" checked={sendMaterials} onChange={e => setSendMaterials(e.target.checked)}/>确认将材料和可选 JD 发送给所选模型服务</label>
          <p className="fine">姓名和联系方式单独留在本机；教育信息会作为材料发送。若正文里写了隐私，也会一并发送。{modelStatus}；模型调用可能计费。</p>
          <button className="primary full" type="submit">AI 生成简历</button>
          <button className="text-button full" type="button" onClick={() => void action(async () => {
            adopt(await api<Resume>("/api/resumes", { name: content.name, contact: content.contact, target_role: content.target_role, education: clean(content).education, source_text: source })); await refreshList();
          })}>进入编辑器 →</button>
        </fieldset></form>
      </section> : <>
        <div className={`document-banner ${record.origin === "demo" ? "demo-banner" : ""}`}>
          {record.origin === "demo" ? "虚构演示材料，不属于你的经历，不可直接投递。" : record.ai ? "AI 整理版本 · 请对照个人经历核对，审阅通过也不能代替事实确认。" : "手工整理版本 · 请核对个人事实，当前未经过 AI 审阅。"}
          <button disabled={busy} onClick={() => void action(async () => setHistory(await api<Resume[]>(`/api/resumes/${record.id}/history`)))}>版本记录</button>
        </div>
        <div className="editor-grid"><section className="editor-panel"><div className="panel-title"><h2>编辑内容</h2><span>v{record.revision}{dirty ? " · 未保存" : " · 已保存"}</span></div>
          <fieldset disabled={busy}><div className="two-fields"><label>姓名<input value={content.name} maxLength={80} onChange={e => edit({ ...content, name: e.target.value })}/></label>
          <label>目标岗位<input value={content.target_role} maxLength={80} onChange={e => edit({ ...content, target_role: e.target.value })}/></label></div>
          <label>联系方式<input value={content.contact} maxLength={300} onChange={e => edit({ ...content, contact: e.target.value })}/></label>
          <label>个人简介（可留空）<textarea rows={3} value={content.summary} maxLength={2000} onChange={e => edit({ ...content, summary: e.target.value })}/></label>
          <EducationFields rows={content.education || []} onChange={education => edit({ ...content, education })}/>
          {!content.education?.length && <p className="notice">尚未填写固定教育信息；如正文已有教育段落，请确认后移入此处，避免重复。</p>}
          <ExperienceFields sections={content.sections} onChange={sections => edit({ ...content, sections })}/>
          </fieldset>
          <div className="save-bar"><button className="primary" disabled={busy || !dirty} onClick={() => void action(async () => { await save(); })}>保存修改</button>
            <button className="text-button" disabled={busy} onClick={() => { if (canSwitch()) void action(async () => adopt(await api<Resume>(`/api/resumes/${record.id}`))); }}>重新载入</button></div>
        </section>
        <section className="preview-panel"><div className="panel-title"><h2>简历预览</h2><span>A4 · 单栏</span></div>
          <div className="preview-box" ref={previewBox} style={{ height: 1123 * scale }}><iframe title="简历预览" sandbox="allow-same-origin" srcDoc={preview} style={{ transform: `scale(${scale})` }}/></div>
          <div className="export-panel"><strong>确认当前内容后导出</strong><p>点击即表示你已核对当前版本；有修改时会先保存。</p>
            {record.ai && <div className="ai-review-box"><p data-testid="ai-review-state">{dirty ? "内容已修改，需要重新审阅或自行核对" : record.ai.manual_takeover ? "用户自行核对，未经 AI 审阅" : record.ai.review_status === "passed" ? "当前版本 AI 审阅通过" : record.ai.review_status === "blocked" ? (record.ai.issues.some(unresolvedBlocking) ? "当前有需处理的审阅问题" : "阻断已逐项处理，可自行核对并接管") : "当前版本尚未审阅"}</p>
              {record.ai.issues.map((issue, index) => <div className="fine" key={index}><p>{issue.resolution?.action === "deleted" ? "原问题条目已删除：" : issue.resolution?.action === "source_reviewed" ? "已依据原文人工核对：" : issue.severity === "blocking" ? "需修正：" : "建议："}{issue.message}</p>
                {issue.resolution?.explanation && <p>核对说明：{issue.resolution.explanation}</p>}
                {unresolvedBlocking(issue) && <button className="text-button" disabled={busy} onClick={() => void resolveIssue(index)}>依据原文处理</button>}</div>)}
              <button className="secondary" disabled={busy} onClick={() => void recheck()}>保存并重新审阅</button>
              <button className="text-button" disabled={busy} onClick={() => void takeover()}>自行核对并接管</button></div>}
            <div className="button-row"><button className="primary" disabled={busy || Boolean(record.ai && (dirty || (!record.ai.manual_takeover && record.ai.review_status !== "passed") || record.ai.issues.some(unresolvedBlocking)))} onClick={() => void download("pdf")}>确认并导出 PDF</button><button className="secondary" disabled={busy || Boolean(record.ai && (dirty || (!record.ai.manual_takeover && record.ai.review_status !== "passed") || record.ai.issues.some(unresolvedBlocking)))} onClick={() => void download("docx")}>确认并导出 Word</button></div>
            <button className="text-button" disabled={busy} onClick={() => void download("docx", true)}>先下载 Word 草稿</button>
            <p className="fine">Word 中的字体与分页可能不同；PDF 更适合固定排版。</p>
          </div>
        </section></div>
      </>}
    </main>
    {settings && <ModelSettings onClose={() => setSettings(false)} onSaved={() => void refreshModel()}/>}
    {resolution && <ManualReview record={resolution.record} issueIndex={resolution.issueIndex} onClose={() => setResolution(null)} onSaved={row => {
      adopt(row); setResolution(null); setStatus("已保存原文人工核对结果；处理完其他问题后可自行核对并接管");
    }}/>}
    {history && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-label="版本记录"><button className="close" onClick={() => setHistory(null)} aria-label="关闭版本记录">×</button><h2>版本记录</h2><p>已保存版本保持不变，当前共 {history.length} 个版本。</p>{history.map(row => <div className="history-row" key={row.revision}><strong>v{row.revision} · {row.content.name || "未命名"}</strong><small>{new Date(row.updated_at).toLocaleString()}</small><p>{row.content.sections[0]?.items[0]?.text || "空白草稿"}</p></div>)}</section></div>}
  </div>;
}
