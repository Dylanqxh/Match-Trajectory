import { useRef, useState } from "react";
import { request, UploadPreview } from "./api";

export function MaterialIntake({ busy, onResume, onJd }: {
  busy: boolean;
  onResume: (text: string) => void;
  onJd: (text: string) => void;
}) {
  const [kind, setKind] = useState<"resume" | "jd" | null>(null);
  const [preview, setPreview] = useState<UploadPreview | null>(null);
  const [draft, setDraft] = useState("");
  const [drag, setDrag] = useState<"resume" | "jd" | null>(null);
  const [error, setError] = useState("");
  const [reading, setReading] = useState(false);
  const resumeInput = useRef<HTMLInputElement>(null);
  const jdInput = useRef<HTMLInputElement>(null);

  async function read(file: File, next: "resume" | "jd") {
    setReading(true); setError(""); setKind(next);
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await request("/api/chat/uploads", { method: "POST", body });
      const uploaded = await response.json() as UploadPreview;
      setPreview(uploaded);
      setDraft(uploaded.text);
    } catch (reason) {
      setPreview(null);
      setError((reason as Error).message);
    } finally { setReading(false); }
  }

  function accept(next: "resume" | "jd") {
    const text = draft.trim();
    if (!text) return;
    if (next === "jd") onJd(text);
    else onResume(text);
    setPreview(null); setDraft(""); setKind(null);
  }

  return <div className="material-intake">
    <div className="material-drops">
      <Drop label="旧简历" hint="PDF、Word、TXT、Markdown" active={drag === "resume"} disabled={busy || reading}
        onClick={() => resumeInput.current?.click()}
        onDrag={value => setDrag(value ? "resume" : null)}
        onFile={file => void read(file, "resume")}/>
      <Drop label="岗位 JD" hint="没有 JD 也可以，之后再贴" active={drag === "jd"} disabled={busy || reading}
        onClick={() => jdInput.current?.click()}
        onDrag={value => setDrag(value ? "jd" : null)}
        onFile={file => void read(file, "jd")}/>
    </div>
    <input ref={resumeInput} className="file-input" aria-label="上传旧简历" type="file" accept={ACCEPT} disabled={busy || reading} onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void read(file, "resume"); }}/>
    <input ref={jdInput} className="file-input" aria-label="上传岗位 JD" type="file" accept={ACCEPT} disabled={busy || reading} onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void read(file, "jd"); }}/>
    {reading && <p className="chat-empty">正在读取文件…</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {preview && <div className={`chat-preview ${preview.reliable ? "" : "unreliable"}`}>
      <div className="chat-preview-head"><strong>{preview.reliable ? (kind === "jd" ? "核对 JD" : "核对简历文字") : "这份文件没法直接用"}</strong><span>{preview.name || preview.kind.toUpperCase()}</span></div>
      <p>{preview.reliable ? "改完再使用。能识别的姓名、联系方式、学校和岗位会填进下面，已填过的不会被覆盖。" : preview.reason}</p>
      {preview.warnings.map(warning => <p key={warning}>{warning}</p>)}
      {(preview.text || preview.reliable) && <textarea aria-label="材料预览" rows={7} value={draft} onChange={event => setDraft(event.target.value)}/>}
      {!preview.text && !preview.reliable && <p>请改为把文字粘贴到下面的选填材料里。</p>}
      <div className="chat-preview-actions">
        <button className="primary" type="button" disabled={!draft.trim()} onClick={() => accept(kind || "resume")}>{kind === "jd" ? "使用这份 JD" : "使用这份简历"}</button>
        <button className="text-button" type="button" onClick={() => { setPreview(null); setKind(null); }}>取消</button>
        <span>{draft.length.toLocaleString()} 字</span>
      </div>
    </div>}
  </div>;
}

const ACCEPT = ".pdf,.docx,.doc,.txt,.text,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/msword,text/plain,text/markdown";

function Drop({ label, hint, active, disabled, onClick, onDrag, onFile }: {
  label: string; hint: string; active: boolean; disabled: boolean;
  onClick: () => void; onDrag: (active: boolean) => void; onFile: (file: File) => void;
}) {
  return <div className={`drop-zone ${active ? "drag" : ""}`} onDragOver={event => { event.preventDefault(); onDrag(true); }} onDragLeave={() => onDrag(false)}
    onDrop={event => { event.preventDefault(); onDrag(false); const file = event.dataTransfer.files?.[0]; if (file && !disabled) onFile(file); }}>
    <strong>{label}</strong>
    <span>{hint}</span>
    <button className="secondary" type="button" disabled={disabled} onClick={onClick}>选择文件</button>
  </div>;
}
