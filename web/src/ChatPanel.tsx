import { useEffect, useRef, useState } from "react";
import { api, ChatSession, request, UploadPreview } from "./api";

const stateLabel: Record<string, string> = {
  queued: "正在生成", running: "正在生成", waiting_input: "等待补充",
  ready: "初稿在左侧", failed: "可以继续", interrupted: "已中断", cancelled: "已取消",
};

export function ChatPanel({ modelReady, onOpenSettings, onJob }: {
  modelReady: boolean; onOpenSettings: () => void; onJob: (id: string) => void;
}) {
  const [session, setSession] = useState<ChatSession | null>(null);
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<UploadPreview | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(() => localStorage.getItem("mt_assistant_open") !== "0");
  const log = useRef<HTMLDivElement>(null);
  const onJobRef = useRef(onJob);
  onJobRef.current = onJob;
  const waiting = session?.job_state === "waiting_input" && (session.questions?.length ?? 0) > 0;

  useEffect(() => { localStorage.setItem("mt_assistant_open", open ? "1" : "0"); }, [open]);
  useEffect(() => { if (waiting) setOpen(true); }, [waiting]);

  useEffect(() => {
    const saved = localStorage.getItem("mt_chat_id");
    void (async () => {
      await api("/api/session");
      try {
        if (saved) {
          const row = await api<ChatSession>(`/api/chat/sessions/${saved}`);
          setSession(row);
          if (row.job_id) onJobRef.current(row.job_id);
          return;
        }
      } catch { localStorage.removeItem("mt_chat_id"); }
      const row = await api<ChatSession>("/api/chat/sessions", {});
      localStorage.setItem("mt_chat_id", row.id);
      setSession(row);
    })().catch(reason => setError((reason as Error).message));
  }, []);

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [session?.messages.length, open]);

  useEffect(() => {
    if (!session?.job_id || !session.job_state || !["queued", "running", "waiting_input"].includes(session.job_state)) return;
    const timer = setInterval(() => {
      void api<ChatSession>(`/api/chat/sessions/${session.id}`).then(row => {
        setSession(row);
        if (row.job_id) onJobRef.current(row.job_id);
      }).catch(() => {});
    }, 800);
    return () => clearInterval(timer);
  }, [session?.id, session?.job_id, session?.job_state]);

  async function send(message: string, extra?: { upload_id?: string; source_text?: string }) {
    if (!session || busy) return;
    setBusy(true); setError("");
    try {
      const row = await api<ChatSession>(`/api/chat/sessions/${session.id}/messages`, {
        text: message, upload_id: extra?.upload_id || "", source_text: extra?.source_text ?? null,
      });
      setSession(row); setText("");
      if (row.job_id) onJobRef.current(row.job_id);
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }

  async function upload(file: File) {
    setBusy(true); setError(""); setOpen(true);
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await request("/api/chat/uploads", { method: "POST", body });
      const next = await response.json() as UploadPreview;
      setPreview(next); setDraft(next.text);
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }

  const label = session?.job_state ? stateLabel[session.job_state] || "助手" : "待命";

  return <aside className={`assistant-rail ${open ? "open" : "collapsed"}`} aria-label="简历助手">
    <header className="assistant-head">
      {open ? <>
        <div><span className="eyebrow">助手</span><strong>收集材料</strong><small>不改写正文</small></div>
        <span className={`assistant-state ${session?.job_state || "idle"}`}>{session ? label : "正在准备"}</span>
      </> : <span className="assistant-tab">助手</span>}
      <button className="text-button" type="button" aria-expanded={open} aria-label={open ? "收起助手" : "展开助手"} onClick={() => setOpen(value => !value)}>{open ? "收起" : "展开"}</button>
    </header>
    {open && <div className="assistant-body">
      {!modelReady && <div className="notice assistant-setup">生成前请先<button className="text-button" type="button" onClick={onOpenSettings}>连接模型</button>。也可以先在左侧看虚构示例。</div>}
      <div className="chat-log" ref={log}>
        {!session && <p className="chat-empty">正在准备助手…</p>}
        {session?.messages.map((message, index) => index === 0 && message.role === "assistant"
          ? <details className="chat-intro" key={index}><summary>可以这样开始</summary><p>{message.text}</p></details>
          : <p className={`chat-bubble ${message.role}`} key={index}>{message.text}</p>)}
      </div>
      {session?.coverage_notes?.length ? <div className="notice chat-gaps"><strong>不写入正文</strong>{session.coverage_notes.map(note => <p key={note}>{note}</p>)}</div> : null}
      {waiting && <div className="chat-questions">
        <p>这一轮最多三个问题。回答后发送，或先看完整初稿。</p>
        <ol>{session?.questions.map((question, index) => <li key={question.id}>{index + 1}. {question.text}</li>)}</ol>
        <button className="secondary" type="button" disabled={busy} onClick={() => void send("跳过")}>跳过，先看初稿</button>
      </div>}
      {preview && <div className="chat-preview">
        <div className="chat-preview-head"><strong>{preview.reliable ? "识别预览" : "需要改为粘贴"}</strong><span>{preview.kind.toUpperCase()}{preview.pages ? ` · ${preview.pages} 页` : ""}</span></div>
        <p>{preview.reliable ? "改完再用作材料。姓名和学校请写在对话里，不要只留在正文。" : preview.reason}</p>
        {preview.warnings.map(warning => <p key={warning}>{warning}</p>)}
        <textarea aria-label="识别预览" rows={5} value={draft} onChange={event => setDraft(event.target.value)}/>
        <div className="chat-preview-actions">
          <button className="primary" type="button" disabled={busy || !draft.trim()} onClick={() => void send(text, { upload_id: preview.id, source_text: draft }).then(() => setPreview(null))}>用作简历材料</button>
          <button className="text-button" type="button" onClick={() => setPreview(null)}>取消</button>
          <span>{draft.length.toLocaleString()} 字</span>
        </div>
      </div>}
      {error && <p className="error" role="alert">{error}</p>}
      <form className="chat-compose" onSubmit={event => { event.preventDefault(); if (text.trim()) void send(text); }}>
        <textarea aria-label="对话输入" rows={3} value={text} maxLength={20000} disabled={busy} onChange={event => setText(event.target.value)}
          placeholder={waiting ? "回答上面的问题，或点跳过" : "目标岗位、姓名、联系方式，或粘贴一段经历 / JD"}/>
        <div className="chat-actions">
          <button className="primary" type="submit" disabled={busy || !text.trim()}>{busy ? "处理中…" : "发送"}</button>
          <label className="secondary chat-upload">上传<input aria-label="上传简历" type="file" accept=".docx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" disabled={busy}
            onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void upload(file); }}/></label>
          <button className="text-button" type="button" disabled={busy} onClick={() => void send("跳过")}>跳过</button>
          <button className="text-button" type="button" disabled={busy} onClick={() => void send("把这段缩短")}>缩短</button>
          <button className="text-button" type="button" disabled={busy} onClick={() => void send("补上人数")}>补人数</button>
        </div>
        <p className="fine">DOCX 或可复制文字的 PDF，8 MB 以内，PDF 最多 12 页。扫描件请粘贴。</p>
      </form>
    </div>}
  </aside>;
}
