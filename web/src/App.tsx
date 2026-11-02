import { useEffect, useRef, useState } from "react";
import { api, clean, Content, emptyContent, request, Resume, Summary } from "./api";
import { ModelSettings } from "./ModelSettings";

const roles = ["后端研发", "算法", "数据分析", "产品经理", "内容／用户运营"];

export default function App() {
  const [list, setList] = useState<Summary[]>([]);
  const [record, setRecord] = useState<Resume | null>(null);
  const [content, setContent] = useState<Content>(emptyContent);
  const [source, setSource] = useState("");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("正在连接本地工作台…");
  const [error, setError] = useState("");
  const [settings, setSettings] = useState(false);
  const [history, setHistory] = useState<Resume[] | null>(null);
  const [preview, setPreview] = useState("");
  const [scale, setScale] = useState(0.8);
  const previewBox = useRef<HTMLDivElement>(null);
  const hasUnsavedChanges = dirty || (!record && Boolean(source.trim() || content.name.trim() || content.target_role.trim() || content.contact.trim()));

  function adopt(row: Resume) {
    setRecord(row); setContent(row.content); setDirty(false); setError("");
    localStorage.setItem("mt_resume_id", row.id);
    setStatus(`已载入版本 ${row.revision}`);
  }
  async function refreshList() { setList(await api<Summary[]>("/api/resumes")); }
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
  function editItem(sectionId: string, itemId: string, text: string) {
    edit({ ...content, sections: content.sections.map(section => section.id !== sectionId ? section : {
      ...section, items: section.items.map(item => item.id === itemId ? { ...item, text } : item),
    }) });
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-icon">M</span><div>Match-Trajectory<small>求职简历工作台</small></div></div>
      <button className="new-button" disabled={busy} onClick={() => {
        if (canSwitch()) { setRecord(null); setContent(emptyContent); setSource(""); setDirty(false); localStorage.removeItem("mt_resume_id"); }
      }}>＋ 新建简历</button>
      <div className="nav-heading">我的简历 <span>{list.length}</span></div>
      <nav aria-label="我的简历">{list.map(row => <button key={row.id} className={`resume-link ${record?.id === row.id ? "active" : ""}`} disabled={busy}
        onClick={() => { if (canSwitch()) void action(async () => adopt(await api<Resume>(`/api/resumes/${row.id}`))); }}>
        <span>{row.name || "未命名简历"}</span><small>{row.target_role || "方向待填写"} · v{row.revision}{row.origin === "demo" ? " · 演示" : ""}</small>
      </button>)}</nav>
      <div className="sidebar-bottom"><button disabled={busy} onClick={() => setSettings(true)}>⚙ 模型连接</button>
        <div className="local-note"><span className="status-dot"/>资料保存在本机<small>M0 · 手工编辑与文件交付</small></div></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><div><span className="eyebrow">RESUME WORKSPACE</span><h1>简历工作台</h1></div>
        <span className="stage-chip">编辑与导出 · M0</span></header>
      <div className="feedback" role="status">{busy ? "正在处理，请稍候…" : status}</div>
      {error && <div className="error" role="alert">{error}<button onClick={() => setError("")} aria-label="关闭错误">×</button></div>}
      {!record ? <section className="start-layout">
        <div className="welcome"><span className="eyebrow">从你已经做过的事开始</span><h2>把经历写清楚，<br/>让价值被看见。</h2>
          <p>选择求职方向，放入现有材料，再逐段整理成自己的简历。</p>
          <div className="feature-line"><span>01 录入材料</span><span>02 编辑预览</span><span>03 核对导出</span></div>
          <button className="secondary" disabled={busy} onClick={() => { if (canSwitch()) void action(async () => {
            adopt(await api<Resume>("/api/demo", {})); await refreshList();
          }); }}>先用虚构示例体验 →</button>
          <p className="fine">当前不会自动扩写经历；AI 生成与岗位适配将在后续阶段接入。</p>
        </div>
        <form className="material-card" onSubmit={event => { event.preventDefault(); void action(async () => {
          adopt(await api<Resume>("/api/resumes", { name: content.name, contact: content.contact, target_role: content.target_role, source_text: source }));
          await refreshList();
        }); }}><fieldset disabled={busy}>
          <h3>开始整理你的简历</h3><label>姓名<input value={content.name} maxLength={80} onChange={e => setContent({ ...content, name: e.target.value })} placeholder="如何称呼你"/></label>
          <label>目标岗位<input list="roles" value={content.target_role} maxLength={80} onChange={e => setContent({ ...content, target_role: e.target.value })} placeholder="例如 Java 后端、算法、产品经理"/><datalist id="roles">{roles.map(role => <option value={role} key={role}/>)}</datalist></label>
          <label>联系方式<input value={content.contact} maxLength={300} onChange={e => setContent({ ...content, contact: e.target.value })} placeholder="邮箱或手机号，可稍后补充"/></label>
          <label>现有材料<textarea rows={9} maxLength={20000} value={source} onChange={e => setSource(e.target.value)} placeholder="粘贴已经写过的经历、项目描述或实践记录。这里会原样放入编辑器，不会自动编写新经历。"/></label>
          <div className="field-help">{source.length.toLocaleString()} / 20,000 字 · 本机保存</div>
          <button className="primary full" type="submit">进入编辑器 →</button>
        </fieldset></form>
      </section> : <>
        <div className={`document-banner ${record.origin === "demo" ? "demo-banner" : ""}`}>
          {record.origin === "demo" ? "虚构演示材料，不属于你的经历，不可直接投递。" : "手工整理版本 · 请核对个人事实，当前未经过 AI 审阅。"}
          <button disabled={busy} onClick={() => void action(async () => setHistory(await api<Resume[]>(`/api/resumes/${record.id}/history`)))}>版本记录</button>
        </div>
        <div className="editor-grid"><section className="editor-panel"><div className="panel-title"><h2>编辑内容</h2><span>v{record.revision}{dirty ? " · 未保存" : " · 已保存"}</span></div>
          <fieldset disabled={busy}><div className="two-fields"><label>姓名<input value={content.name} maxLength={80} onChange={e => edit({ ...content, name: e.target.value })}/></label>
          <label>目标岗位<input value={content.target_role} maxLength={80} onChange={e => edit({ ...content, target_role: e.target.value })}/></label></div>
          <label>联系方式<input value={content.contact} maxLength={300} onChange={e => edit({ ...content, contact: e.target.value })}/></label>
          <label>个人简介（可留空）<textarea rows={3} value={content.summary} maxLength={2000} onChange={e => edit({ ...content, summary: e.target.value })}/></label>
          {content.sections.map(section => <div className="section-card" key={section.id}>
            <div className="section-heading"><input aria-label="板块名称" value={section.title} maxLength={60} onChange={e => edit({ ...content, sections: content.sections.map(s => s.id === section.id ? { ...s, title: e.target.value } : s) })}/>
              <button className="text-button" onClick={() => edit({ ...content, sections: content.sections.filter(s => s.id !== section.id) })} aria-label={`删除${section.title}板块`}>删除板块</button></div>
            {section.items.map((item, index) => <div className="item-row" key={item.id}><textarea aria-label={`${section.title}第${index + 1}条`} rows={3} value={item.text} maxLength={4000} onChange={e => editItem(section.id, item.id, e.target.value)}/>
              <button className="remove-item" aria-label={`删除第${index + 1}条`} onClick={() => edit({ ...content, sections: content.sections.map(s => s.id === section.id ? { ...s, items: s.items.filter(i => i.id !== item.id) } : s) })}>×</button></div>)}
            <button className="text-button" onClick={() => edit({ ...content, sections: content.sections.map(s => s.id === section.id ? { ...s, items: [...s.items, { id: crypto.randomUUID(), text: "" }] } : s) })}>＋ 添加一条</button>
          </div>)}
          <button className="secondary full" onClick={() => edit({ ...content, sections: [...content.sections, { id: crypto.randomUUID(), title: "新增经历", items: [] }] })}>＋ 添加板块</button>
          </fieldset>
          <div className="save-bar"><button className="primary" disabled={busy || !dirty} onClick={() => void action(async () => { await save(); })}>保存修改</button>
            <button className="text-button" disabled={busy} onClick={() => { if (canSwitch()) void action(async () => adopt(await api<Resume>(`/api/resumes/${record.id}`))); }}>重新载入</button></div>
        </section>
        <section className="preview-panel"><div className="panel-title"><h2>简历预览</h2><span>A4 · 单栏</span></div>
          <div className="preview-box" ref={previewBox} style={{ height: 1123 * scale }}><iframe title="简历预览" sandbox="allow-same-origin" srcDoc={preview} style={{ transform: `scale(${scale})` }}/></div>
          <div className="export-panel"><strong>确认当前内容后导出</strong><p>点击即表示你已核对当前版本；有修改时会先保存。</p>
            <div className="button-row"><button className="primary" disabled={busy} onClick={() => void download("pdf")}>确认并导出 PDF</button><button className="secondary" disabled={busy} onClick={() => void download("docx")}>确认并导出 Word</button></div>
            <button className="text-button" disabled={busy} onClick={() => void download("docx", true)}>先下载 Word 草稿</button>
            <p className="fine">Word 中的字体与分页可能不同；PDF 更适合固定排版。</p>
          </div>
        </section></div>
      </>}
    </main>
    {settings && <ModelSettings onClose={() => setSettings(false)}/>}
    {history && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-label="版本记录"><button className="close" onClick={() => setHistory(null)} aria-label="关闭版本记录">×</button><h2>版本记录</h2><p>已保存版本保持不变，当前共 {history.length} 个版本。</p>{history.map(row => <div className="history-row" key={row.revision}><strong>v{row.revision} · {row.content.name || "未命名"}</strong><small>{new Date(row.updated_at).toLocaleString()}</small><p>{row.content.sections[0]?.items[0]?.text || "空白草稿"}</p></div>)}</section></div>}
  </div>;
}
