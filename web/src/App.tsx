import { useEffect, useRef, useState } from "react";
import { api, clean, Content, emptyContent, GenerationJob, GenerationSummary, IntakeFields, request, Resume, Summary, unresolvedBlocking } from "./api";
import { ModelSettings } from "./ModelSettings";
import { GenerationPanel } from "./GenerationPanel";
import { ManualReview } from "./ManualReview";
import { EducationFields } from "./EducationFields";
import { ExperienceFields } from "./ExperienceFields";
import { QualityReport } from "./QualityReport";
import { ChatPanel } from "./ChatPanel";
import { MaterialIntake } from "./MaterialIntake";

const roles = ["后端研发", "Agent／RAG 应用开发实习", "推荐算法", "NLP 算法", "数据分析", "产品经理", "内容／用户运营"];

export default function App() {
  const [list, setList] = useState<Summary[]>([]);
  const [record, setRecord] = useState<Resume | null>(null);
  const [content, setContent] = useState<Content>(emptyContent);
  const [source, setSource] = useState("");
  const [jd, setJd] = useState("");
  const [sendMaterials, setSendMaterials] = useState(false);
  const [allowQuestions, setAllowQuestions] = useState(true);
  const [roleDirection, setRoleDirection] = useState<"product" | "backend" | "other">("other");
  const [careerStage, setCareerStage] = useState("unspecified");
  const [careerGap, setCareerGap] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobs, setJobs] = useState<GenerationSummary[]>([]);
  const [modelStatus, setModelStatus] = useState("尚未连接模型");
  const [useSupervisor, setUseSupervisor] = useState(false);
  const generationRequest = useRef<{ key: string; id: string } | null>(null);
  const savedInput = useRef("");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const deletionInFlight = useRef(false);
  const selectedRecordId = useRef<string | null>(null);
  const selectedJobId = useRef<string | null>(null);
  selectedRecordId.current = record?.id ?? null;
  selectedJobId.current = jobId;
  const interactionLocked = busy || Boolean(deleting);
  const [recognized, setRecognized] = useState("");
  const [status, setStatus] = useState("正在连接本地工作台…");
  const [error, setError] = useState("");
  const [settings, setSettings] = useState(false);
  const [resolution, setResolution] = useState<{ record: Resume; issueIndex: number } | null>(null);
  const [history, setHistory] = useState<Resume[] | null>(null);
  const [preview, setPreview] = useState("");
  const [scale, setScale] = useState(0.8);
  const previewBox = useRef<HTMLDivElement>(null);
  const formKey = JSON.stringify({ name: content.name, target_role: content.target_role, contact: content.contact, education: content.education, source, jd, careerStage, careerGap });
  const hasUnsavedChanges = dirty || (!record && Boolean(source.trim() || jd.trim() || content.name.trim() || content.target_role.trim() || content.contact.trim()
    || careerStage !== "unspecified" || careerGap || (content.education || []).some(e => e.school.trim() || e.degree.trim() || e.major.trim() || e.start_date?.trim() || e.end_date?.trim())) && formKey !== savedInput.current);

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
    if (deletionInFlight.current) return;
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
      else { localStorage.removeItem("mt_resume_id"); setStatus("本地工作台已就绪"); }
      const recentJobs = await api<GenerationSummary[]>("/api/generation-jobs"); setJobs(recentJobs);
      const previousJob = localStorage.getItem("mt_job_id");
      if (previousJob && recentJobs.some(row => row.id === previousJob)) setJobId(previousJob);
      else localStorage.removeItem("mt_job_id");
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

  function edit(next: Content) { if (deletionInFlight.current) return; setContent(next); setDirty(true); setStatus("有未保存的修改"); }
  function canSwitch() { return !deletionInFlight.current && (!hasUnsavedChanges || window.confirm("当前修改尚未保存，确定切换？")); }
  async function save(): Promise<Resume> {
    if (!record) throw new Error("请先创建简历");
    if (!dirty) return record;
    const row = await api<Resume>(`/api/resumes/${record.id}`, { expected_revision: record.revision, content: clean(content) }, "PUT");
    adopt(row); await refreshList(); setStatus(`已保存版本 ${row.revision}`); return row;
  }
  function hasEducation(rows: Content["education"]) {
    return (rows || []).some(row => row.school.trim() || row.degree.trim() || row.major.trim());
  }
  async function useResume(text: string) {
    const fields = await api<IntakeFields>("/api/intake/parse", { text, purpose: "resume" });
    setSource(current => current.trim() && !text.includes(current.trim()) && !current.includes(text) ? `${text.trim()}\n${current.trim()}` : text.trim() || current);
    setContent(current => ({ ...current,
      name: current.name.trim() ? current.name : fields.name,
      contact: current.contact.trim() ? current.contact : fields.contact,
      target_role: current.target_role.trim() ? current.target_role : fields.target_role,
      education: hasEducation(current.education) ? current.education : fields.education,
    }));
    const noted = [fields.name && `姓名 ${fields.name}`, fields.contact && "联系方式", fields.education[0]?.school, fields.target_role && `岗位 ${fields.target_role}`].filter(Boolean);
    setRecognized(noted.length ? `已从简历带上：${noted.join("、")}。留空的项不用再填；你改过的以你填的为准。` : "简历已作为材料。下面的栏目都是选填。");
    setStatus("简历材料已放进中间画布");
  }
  async function useJd(text: string) {
    const fields = await api<IntakeFields>("/api/intake/parse", { text, purpose: "jd" });
    setJd(current => current.trim() ? current : text.trim());
    setContent(current => ({ ...current, target_role: current.target_role.trim() ? current.target_role : fields.target_role }));
    setRecognized(fields.target_role ? `已从 JD 带上岗位「${fields.target_role}」。你填过的岗位不会被覆盖。` : "JD 已保存。没有写明岗位也可以直接生成。");
    setStatus("JD 已放进中间画布");
  }
  async function generate() {
    await action(async () => {
      const covered = Boolean(source.trim() || jd.trim() || content.name.trim());
      if (!covered) throw new Error("请先上传一份简历或 JD，或在下面粘贴经历");
      if ((source.trim() || jd.trim()) && !sendMaterials) throw new Error("请先确认将材料和 JD 发送给所选模型服务");
      const payload = { name: content.name, contact: content.contact, target_role: content.target_role,
        role_direction: roleDirection,
        education: clean(content).education, source_text: source, jd, career_stage: careerStage, has_career_gap: careerGap,
        execution_mode: useSupervisor ? "supervisor" : "langgraph", allow_questions: allowQuestions, send_materials: sendMaterials };
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
      await confirmTakeover(row);
    });
  }
  async function confirmTakeover(row: Resume) {
    if (!window.confirm("全部阻断问题已处理。我已自行核对当前正文中的全部个人事实。接管后保留 AI 来源和旧报告，标记为用户自行核对。确定继续？")) {
      setStatus("人工核对结果已保存；准备好后可点击“自行核对并接管”确认"); return;
    }
    adopt(await api<Resume>(`/api/resumes/${row.id}/takeover`, { expected_revision: row.revision, acknowledged: true }));
    await refreshList();
    setStatus("已标记为用户自行核对，可确认并导出当前版本");
  }
  function editIssue(itemId: string) {
    setResolution(null);
    setStatus("请修改或删除问题条目，然后保存并重新审阅，或再次自行核对并接管");
    requestAnimationFrame(() => {
      const section = content.sections.find(s => s.id === itemId || s.items.some(i => i.id === itemId));
      const itemIndex = section?.items.findIndex(i => i.id === itemId) ?? -1;
      const educationIndex = content.education.findIndex(e => e.id === itemId);
      const sectionElement = section ? document.querySelectorAll(".editor-panel .section-heading")[content.sections.indexOf(section)]?.parentElement : null;
      const field = sectionElement ? itemIndex >= 0 ? sectionElement.querySelectorAll<HTMLElement>(".bullet-editor textarea")[itemIndex] : sectionElement.querySelector<HTMLElement>(".section-heading input")
        : educationIndex >= 0 ? document.querySelector<HTMLElement>(`[aria-label="教育${educationIndex + 1}学校"]`) : document.querySelector<HTMLElement>(".editor-panel textarea");
      field?.scrollIntoView({ block: "center", behavior: "smooth" }); field?.focus();
    });
  }
  async function deleteRecord(row: Summary) {
    if (deletionInFlight.current || busy || !canSwitch()) return;
    if (!window.confirm(`确定删除简历“${row.name || "未命名简历"}”？将删除正文、全部版本、关联生成及重审任务和导出文件，此操作无法撤销。`)) return;
    deletionInFlight.current = true; setDeleting(row.id); setError("");
    try {
      const current = record?.id === row.id ? record : await api<Resume>(`/api/resumes/${row.id}`);
      const result = await api<{ cleanup_pending: boolean }>(`/api/resumes/${row.id}`, { expected_revision: current.revision }, "DELETE");
      setResolution(null); setHistory(null);
      if (selectedRecordId.current === row.id) {
        setRecord(null); setContent(emptyContent); setDirty(false); setPreview(""); setSource(""); setJd("");
        setCareerStage("unspecified"); setCareerGap(false); setSendMaterials(false); savedInput.current = ""; generationRequest.current = null;
        localStorage.removeItem("mt_resume_id");
      }
      const remainingJobs = await api<GenerationSummary[]>("/api/generation-jobs"); setJobs(remainingJobs);
      if (selectedJobId.current && !remainingJobs.some(job => job.id === selectedJobId.current)) showJob(null);
      await refreshList();
      setStatus(result.cleanup_pending ? "简历已删除，部分关联文件等待清理" : "简历及关联记录已删除");
    } catch (error) { setError((error as Error).message); }
    finally { deletionInFlight.current = false; setDeleting(null); }
  }
  async function deleteJob(id: string) {
    if (deletionInFlight.current || busy || !canSwitch()) return;
    if (!window.confirm("确定删除此生成任务？执行中的任务会取消，任务记录与检查点将移除。已采用简历仍保留必要的原文来源，直到删除对应简历。此操作无法撤销。")) return;
    deletionInFlight.current = true; setDeleting(id); setError("");
    try {
      const result = await api<{ retained_for_resume: boolean; cleanup_pending: boolean }>(`/api/generation-jobs/${id}`, {}, "DELETE");
      if (selectedJobId.current === id) showJob(null);
      generationRequest.current = null;
      await refreshJobs();
      setStatus(`任务已删除${result.retained_for_resume ? "；已采用简历所需的原文来源仍保留" : ""}${result.cleanup_pending ? "；部分文件等待清理" : ""}`);
    } catch (error) { setError((error as Error).message); }
    finally { deletionInFlight.current = false; setDeleting(null); }
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
    if (deletionInFlight.current) return;
    if (["ready", "failed", "interrupted", "cancelled", "waiting_input"].includes(job.state)) void refreshJobs().catch(() => {});
    if (job.mode === "recheck" && job.state === "ready" && record && !dirty) {
      void api<Resume>(`/api/resumes/${record.id}`).then(row => {
        if (!deletionInFlight.current && selectedRecordId.current === row.id) { setRecord(row); setStatus("当前版本审阅已完成，请查看结果"); }
      }).catch(() => {});
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
      <button className="new-button" disabled={interactionLocked} onClick={() => {
        if (canSwitch()) { setRecord(null); setContent(emptyContent); setSource(""); setJd(""); setCareerStage("unspecified"); setCareerGap(false); setSendMaterials(false); setDirty(false); savedInput.current = ""; generationRequest.current = null; showJob(null); localStorage.removeItem("mt_resume_id"); }
      }}>＋ 新建简历</button>
      <div className="nav-heading">我的简历 <span>{list.length}</span></div>
      <nav aria-label="我的简历">{list.map(row => <div className="record-nav-row" key={row.id}><button className={`resume-link ${record?.id === row.id ? "active" : ""}`} disabled={interactionLocked}
        onClick={() => { if (canSwitch()) void action(async () => adopt(await api<Resume>(`/api/resumes/${row.id}`))); }}>
        <span>{row.name || "未命名简历"}</span><small>{row.target_role || "方向待填写"} · v{row.revision}{row.origin === "demo" ? " · 演示" : ""}</small>
      </button><button className="delete-record" disabled={interactionLocked} aria-label={`删除简历 ${row.name || "未命名简历"}`} onClick={() => void deleteRecord(row)}>删除</button></div>)}</nav>
      {jobs.length > 0 && <><div className="nav-heading">生成任务</div><nav aria-label="生成任务">{jobs.map(job => <div className="record-nav-row" key={job.id}><button className={`resume-link ${jobId === job.id ? "active" : ""}`} disabled={interactionLocked}
        onClick={() => showJob(job.id)}><span>{job.target_role}</span><small>{({ queued: "等待执行", running: "正在生成", waiting_input: "等待补充", ready: "已有结果", failed: "可查看或继续", interrupted: "已中断", cancelled: "已取消" } as Record<string, string>)[job.state]}</small></button><button className="delete-record" disabled={interactionLocked} aria-label={`删除生成任务 ${job.target_role}`} onClick={() => void deleteJob(job.id)}>删除</button></div>)}</nav></>}
      <div className="sidebar-bottom"><button disabled={interactionLocked} onClick={() => setSettings(true)}>⚙ 模型连接</button>
        <div className="local-note"><span className="status-dot"/>资料保存在本机<small>M1.7 · 分阶段生成与可信交付</small></div></div>
    </aside>
    <main className="main-area" inert={resolution ? true : undefined}>
      <header className="topbar"><div><span className="eyebrow">RESUME WORKSPACE</span><h1>简历工作台</h1></div>
        <span className="stage-chip">生成与交付 · M1.7</span></header>
      <div className="feedback" role="status">{interactionLocked ? "正在处理，请稍候…" : status}</div>
      {error && <div className="error" role="alert">{error}<button onClick={() => setError("")} aria-label="关闭错误">×</button></div>}
      {!modelStatus.startsWith("已连接") && <div className="setup-banner">
        <div><strong>先连接模型，再生成简历</strong><p>选择供应商，打开官方页面复制 Key，粘贴并测试。失败时会说明下一步，不会显示 Key。不配置也可以先看虚构示例。</p></div>
        <button className="primary" type="button" onClick={() => setSettings(true)}>配置 Key</button>
      </div>}
      <div className="canvas">
      {jobId && <fieldset disabled={interactionLocked}><GenerationPanel jobId={jobId} onClose={() => showJob(null)} beforeAdopt={canSwitch}
        onAdopt={row => { adopt(row); showJob(null); void refreshList(); }} onFinished={jobUpdated}/></fieldset>}
      {!record ? <section className="start-layout">
        <div className="welcome"><span className="eyebrow">从已有材料开始</span><h2>先放入简历，<br/>缺的再补一句。</h2>
          <p>上传旧简历或 JD 就能生成。材料里已经有的姓名、联系方式、学校和经历不用重填；你手改过的以你填的为准。</p>
          <div className="feature-line"><span>01 放入材料</span><span>02 生成与核对</span><span>03 局部修改</span></div>
          <button className="secondary" disabled={interactionLocked} onClick={() => { if (canSwitch()) void action(async () => {
            adopt(await api<Resume>("/api/demo", {})); await refreshList();
          }); }}>先用虚构示例体验 →</button>
        </div>
        <form className="material-card" onSubmit={event => { event.preventDefault(); void generate(); }}><fieldset disabled={interactionLocked}>
          <h3>放入材料</h3>
          <MaterialIntake busy={interactionLocked} onResume={text => void useResume(text).catch(reason => setError((reason as Error).message))} onJd={text => void useJd(text).catch(reason => setError((reason as Error).message))}/>
          {recognized && <p className="notice">{recognized}</p>}
          <label className="checkbox-label"><input type="checkbox" checked={sendMaterials} onChange={e => setSendMaterials(e.target.checked)}/>确认将材料和可选 JD 发送给所选模型服务</label>
          <p className="fine">姓名和联系方式留在本机字段里；教育会作为事实回填。若正文里写了隐私，也会一并发送。{modelStatus}；模型调用可能计费。</p>
          <button className="primary full" type="submit">用这些材料生成</button>
          <details className="optional-fields"><summary>手改或补充某一项（选填，材料里有的可以留空）</summary>
          <label>姓名<input value={content.name} maxLength={80} onChange={e => setContent({ ...content, name: e.target.value })} placeholder="留空则使用材料中的姓名"/></label>
          <label>简历方向<select aria-label="简历方向" value={roleDirection} onChange={e => setRoleDirection(e.target.value as "product" | "backend" | "other")}><option value="product">产品经理</option><option value="backend">后端</option><option value="other">其他（通用规则）</option></select></label>
          <label>目标岗位<input list="roles" value={content.target_role} maxLength={80} onChange={e => setContent({ ...content, target_role: e.target.value })} placeholder="留空则使用材料或 JD 中的岗位"/><datalist id="roles">{roles.map(role => <option value={role} key={role}/>)}</datalist></label>
          <p className="fine">方向只按你在这里的选择加载，不会从岗位名称猜测。</p>
          <label>联系方式<input value={content.contact} maxLength={300} onChange={e => setContent({ ...content, contact: e.target.value })} placeholder="留空则使用材料中的手机或邮箱"/></label>
          <details><summary>求职背景（可选，用于调整写法）</summary>
            <label>求职阶段<select aria-label="求职阶段" value={careerStage} onChange={e => setCareerStage(e.target.value)}><option value="unspecified">不确定／通用</option><option value="entry">校招／初次求职</option><option value="experienced">社招／已有经验</option><option value="transition">转岗</option></select></label>
            <label className="checkbox-label"><input type="checkbox" checked={careerGap} onChange={e => setCareerGap(e.target.checked)}/>有职业空窗（可选，不必说明私人原因）</label>
          </details>
          <EducationFields rows={content.education || []} onChange={education => setContent({ ...content, education })}/>
          <label>现有材料<textarea aria-label="现有材料" rows={7} maxLength={20000} value={source} onChange={e => setSource(e.target.value)} placeholder="不上传也可以把经历粘贴在这里。上传后的文字会出现在这里，可再改。"/></label>
          <div className="field-help">{source.length.toLocaleString()} / 20,000 字 · 本机保存</div>
          <details><summary>有具体岗位 JD？可选填写</summary><label>岗位 JD<textarea aria-label="岗位 JD" rows={4} maxLength={8000} value={jd} onChange={e => setJd(e.target.value)}/></label></details>
          <label className="checkbox-label"><input type="checkbox" checked={allowQuestions} onChange={e => setAllowQuestions(e.target.checked)}/>允许最多一轮补问（可跳过）</label>
          <details><summary>生成选项</summary>
            <label className="checkbox-label"><input type="checkbox" checked={useSupervisor} onChange={e => setUseSupervisor(e.target.checked)}/>启用智能修正策略（试用）</label>
            <p className="fine">多项问题需要取舍时，由模型安排修正重点。可能增加调用，仍计入8次上限；请先在“模型连接”中测试工具调用能力。</p>
          </details>
          </details>
          <button className="text-button full" type="button" onClick={() => void action(async () => {
            adopt(await api<Resume>("/api/resumes", { name: content.name, contact: content.contact, target_role: content.target_role, education: clean(content).education, source_text: source })); await refreshList();
          })}>进入编辑器 →</button>
        </fieldset></form>
      </section> : <>
        <div className={`document-banner ${record.origin === "demo" ? "demo-banner" : ""}`}>
          {record.origin === "demo" ? "虚构演示材料，不属于你的经历，不可直接投递。" : record.ai ? "AI 整理版本 · 请对照个人经历核对，审阅通过也不能代替事实确认。" : "手工整理版本 · 请核对个人事实，当前未经过 AI 审阅。"}
          <button disabled={interactionLocked} onClick={() => void action(async () => setHistory(await api<Resume[]>(`/api/resumes/${record.id}/history`)))}>版本记录</button>
        </div>
        <div className="editor-grid"><section className="editor-panel"><div className="panel-title"><h2>编辑内容</h2><span>v{record.revision}{dirty ? " · 未保存" : " · 已保存"}</span></div>
          <fieldset disabled={interactionLocked}><div className="two-fields"><label>姓名<input value={content.name} maxLength={80} onChange={e => edit({ ...content, name: e.target.value })}/></label>
          <label>目标岗位<input value={content.target_role} maxLength={80} onChange={e => edit({ ...content, target_role: e.target.value })}/></label></div>
          <label>联系方式<input value={content.contact} maxLength={300} onChange={e => edit({ ...content, contact: e.target.value })}/></label>
          <label>个人简介（可留空）<textarea rows={3} value={content.summary} maxLength={2000} onChange={e => edit({ ...content, summary: e.target.value })}/></label>
          <EducationFields rows={content.education || []} onChange={education => edit({ ...content, education })}/>
          {!content.education?.length && <p className="notice">尚未填写固定教育信息；如正文已有教育段落，请确认后移入此处，避免重复。</p>}
          <ExperienceFields sections={content.sections} onChange={sections => edit({ ...content, sections })}/>
          </fieldset>
          <div className="save-bar"><button className="primary" disabled={interactionLocked || !dirty} onClick={() => void action(async () => { await save(); })}>保存修改</button>
            <button className="text-button" disabled={interactionLocked} onClick={() => { if (canSwitch()) void action(async () => adopt(await api<Resume>(`/api/resumes/${record.id}`))); }}>重新载入</button></div>
        </section>
        <section className="preview-panel"><div className="panel-title"><h2>简历预览</h2><span>A4 · 单栏</span></div>
          <div className="preview-box" ref={previewBox} style={{ height: 1123 * scale }}><iframe title="简历预览" sandbox="allow-same-origin" srcDoc={preview} style={{ transform: `scale(${scale})` }}/></div>
          <div className="export-panel"><strong>确认当前内容后导出</strong><p>点击即表示你已核对当前版本；有修改时会先保存。</p>
            {record.ai && <div className="ai-review-box"><p data-testid="ai-review-state">{dirty ? "内容已修改，需要重新审阅或自行核对" : record.ai.manual_takeover ? "用户自行核对，保留 AI 原报告" : record.ai.review_status === "passed" ? "当前版本事实审阅通过" : record.ai.review_status === "blocked" ? (record.ai.issues.some(unresolvedBlocking) ? "当前有需处理的审阅问题" : "阻断已逐项处理，可自行核对并接管") : "当前版本尚未审阅"}</p>
              <QualityReport report={record.ai.quality} stale={dirty} sections={content.sections} education={content.education}/>
              {record.ai.issues.map((issue, index) => <div className="fine" key={index}><p>{issue.resolution?.action === "deleted" ? "原问题条目已删除：" : issue.resolution?.action === "source_reviewed" ? "已依据原文人工核对：" : issue.severity === "blocking" ? "需修正：" : "建议："}{issue.message}</p>
                {issue.resolution?.explanation && <p>核对说明：{issue.resolution.explanation}</p>}
                {unresolvedBlocking(issue) && <button className="text-button" disabled={interactionLocked} onClick={() => void resolveIssue(index)}>依据原文处理</button>}</div>)}
              <button className="secondary" disabled={interactionLocked} onClick={() => void recheck()}>保存并重新审阅</button>
              <button className="text-button" disabled={interactionLocked} onClick={() => void takeover()}>自行核对并接管</button></div>}
            <div className="button-row"><button className="primary" disabled={interactionLocked || Boolean(record.ai && (dirty || (!record.ai.manual_takeover && record.ai.review_status !== "passed") || record.ai.issues.some(unresolvedBlocking)))} onClick={() => void download("pdf")}>确认并导出 PDF</button><button className="secondary" disabled={interactionLocked || Boolean(record.ai && (dirty || (!record.ai.manual_takeover && record.ai.review_status !== "passed") || record.ai.issues.some(unresolvedBlocking)))} onClick={() => void download("docx")}>确认并导出 Word</button></div>
            <button className="text-button" disabled={interactionLocked} onClick={() => void download("docx", true)}>先下载 Word 草稿</button>
            <p className="fine">Word 中的字体与分页可能不同；PDF 更适合固定排版。</p>
          </div>
        </section></div>
      </>}
      </div>
    </main>
    <ChatPanel modelReady={modelStatus.startsWith("已连接")} onOpenSettings={() => setSettings(true)} onJob={id => showJob(id)}/>
    {settings && <ModelSettings onClose={() => setSettings(false)} onSaved={() => void refreshModel()}/>}
    {resolution && <ManualReview key={`${resolution.record.id}-${resolution.issueIndex}-${resolution.record.revision}`} record={resolution.record} issueIndex={resolution.issueIndex} onClose={() => setResolution(null)} onEdit={editIssue} onDraft={() => { setResolution(null); void download("docx", true); }} onSaved={row => {
      adopt(row);
      const index = row.ai?.issues.findIndex(unresolvedBlocking) ?? -1;
      if (index >= 0) { setResolution({ record: row, issueIndex: index }); setStatus("人工核对已保存，请继续处理下一项问题"); }
      else { setResolution(null); void action(() => confirmTakeover(row)); }
    }}/>}
    {history && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-label="版本记录"><button className="close" onClick={() => setHistory(null)} aria-label="关闭版本记录">×</button><h2>版本记录</h2><p>已保存版本保持不变，当前共 {history.length} 个版本。</p>{history.map(row => <div className="history-row" key={row.revision}><strong>v{row.revision} · {row.content.name || "未命名"}</strong><small>{new Date(row.updated_at).toLocaleString()}</small><p>{row.content.sections[0]?.items[0]?.text || "空白草稿"}</p></div>)}</section></div>}
  </div>;
}
