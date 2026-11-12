import { useEffect, useRef, useState } from "react";
import { api, ChatSession, request, UploadPreview } from "./api";

export function ChatPanel({ modelReady, onOpenSettings, onJob }: {
  modelReady: boolean; onOpenSettings: () => void; onJob: (id: string) => void;
}) {
  const [session, setSession] = useState<ChatSession | null>(null);
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<UploadPreview | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const log = useRef<HTMLDivElement>(null);
  const onJobRef = useRef(onJob);
  onJobRef.current = onJob;

  useEffect(() => {
    const saved = localStorage.getItem("mt_chat_id");
    void (async () => {
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
  }, [session?.messages.length]);

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
    if (!session) return;
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
    setBusy(true); setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await request("/api/chat/uploads", { method: "POST", body });
      const preview = await response.json() as UploadPreview;
      setPreview(preview); setDraft(preview.text);
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }

  return <section className="chat-panel" aria-label="简历对话">
    <div className="panel-title"><div><span className="eyebrow">CHAT</span><h2>对话整理</h2></div></div>
    {!modelReady && <p className="notice">还没有连接模型。先<button className="text-button" onClick={onOpenSettings}>配置 Key</button>，或先看右边的虚构示例。</p>}
    <div className="chat-log" ref={log}>
      {session?.messages.map((message, index) => <p className={`chat-bubble ${message.role}`} key={index}>{message.text}</p>)}
    </div>
    {session?.coverage_notes?.length ? <div className="notice chat-gaps"><strong>不写入正文</strong>{session.coverage_notes.map(note => <p key={note}>{note}</p>)}</div> : null}
    {preview && <div className="chat-preview">
      <p>{preview.reliable ? "请核对识别文字，改完再用作材料。" : preview.reason}</p>
      {preview.warnings.map(warning => <p key={warning}>{warning}</p>)}
      <textarea aria-label="识别预览" rows={6} value={draft} onChange={event => setDraft(event.target.value)}/>
      <button className="secondary" disabled={busy || !draft.trim()} onClick={() => void send(text, { upload_id: preview.id, source_text: draft }).then(() => setPreview(null))}>用这段文字</button>
    </div>}
    {error && <p className="error" role="alert">{error}</p>}
    <form className="chat-compose" onSubmit={event => { event.preventDefault(); if (text.trim()) void send(text); }}>
      <textarea aria-label="对话输入" rows={3} value={text} maxLength={20000} disabled={busy} onChange={event => setText(event.target.value)}
        placeholder="例如：目标岗位是 Java 后端。姓名小林，联系方式 job@example.com。然后粘贴简历或 JD。"/>
      <div className="button-row">
        <button className="primary" type="submit" disabled={busy || !text.trim()}>发送</button>
        <label className="secondary chat-upload">上传 DOCX / PDF<input aria-label="上传简历" type="file" accept=".docx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" disabled={busy}
          onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void upload(file); }}/></label>
        <button className="text-button" type="button" disabled={busy} onClick={() => void send("跳过")}>跳过</button>
        <button className="text-button" type="button" disabled={busy} onClick={() => void send("把这段缩短")}>把这段缩短</button>
        <button className="text-button" type="button" disabled={busy} onClick={() => void send("补上人数")}>补上人数</button>
      </div>
      <p className="fine">DOCX、可复制文字的 PDF，最大 8 MB、PDF 最多 12 页。扫描件请改为粘贴。对话不会绕过审阅，也不会把岗位差距写进正文。</p>
    </form>
  </section>;
}
