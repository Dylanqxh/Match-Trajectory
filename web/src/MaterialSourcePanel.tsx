import { Content } from "./api";
import { EditorSectionKey } from "./editorSections";
import { MaterialIntake } from "./MaterialIntake";
import { ResumeEditor } from "./ResumeEditor";

export type MaterialPath = "upload" | "form";

export interface MaterialSourcePanelProps {
  path: MaterialPath;
  busy: boolean;
  content: Content;
  source: string;
  jd: string;
  recognized: string;
  editorSection: EditorSectionKey;
  onPathChange: (path: MaterialPath) => void;
  onContentChange: (content: Content) => void;
  onSourceChange: (value: string) => void;
  onJdChange: (value: string) => void;
  onEditorSectionChange: (section: EditorSectionKey) => void;
  onResume: (text: string) => void;
  onJd: (text: string) => void;
}

export function MaterialSourcePanel({ path, busy, content, source, jd, recognized, editorSection,
  onPathChange, onContentChange, onSourceChange, onJdChange, onEditorSectionChange, onResume, onJd }: MaterialSourcePanelProps) {
  return <div className="material-source-panel">
    <div className="material-path-heading">
      <div><span className="step-label">步骤 2 · 提供经历材料</span><h4>选择更顺手的起点</h4></div>
      <span>两边内容都会保留，可以组合使用</span>
    </div>
    <div className="material-paths" role="group" aria-label="材料填写方式">
      <button type="button" className={path === "upload" ? "selected" : ""} aria-pressed={path === "upload"}
        onClick={() => onPathChange("upload")} disabled={busy}>
        <span className="material-path-icon" aria-hidden="true">⇧</span>
        <strong>上传已有简历</strong>
        <small>上传文件，或直接粘贴现有材料</small>
      </button>
      <button type="button" className={path === "form" ? "selected" : ""} aria-pressed={path === "form"}
        onClick={() => onPathChange("form")} disabled={busy}>
        <span className="material-path-icon" aria-hidden="true">▤</span>
        <strong>从空白表单填写</strong>
        <small>按教育、工作、项目和技能逐项整理</small>
      </button>
    </div>

    {path === "upload" ? <div className="material-path-content upload-material-path">
      <MaterialIntake busy={busy} onResume={onResume} onJd={onJd}/>
      <label>或直接粘贴经历<textarea aria-label="现有材料" rows={7} maxLength={20000} value={source}
        onChange={event => onSourceChange(event.target.value)} placeholder="把旧简历或真实经历粘贴在这里。上传后的文字也会出现在这里，可继续修改。"/></label>
      <div className="field-help">{source.length.toLocaleString()} / 20,000 字 · 本机保存</div>
      {recognized && <p className="notice material-recognized">{recognized}</p>}
    </div> : <div className="material-path-content form-material-path">
      <div className="structured-material-note"><strong>不需要先写成长文</strong><span>按板块填写即可；生成时会和上传材料一起整理，不会清空另一条路径。</span></div>
      <ResumeEditor content={content} activeSection={editorSection} disabled={busy}
        onActiveSectionChange={onEditorSectionChange} onChange={onContentChange}/>
    </div>}

    <div className="jd-material-block">
      <label>岗位 JD（可选）<textarea aria-label="岗位 JD" rows={4} maxLength={8000} value={jd}
        onChange={event => onJdChange(event.target.value)} placeholder="没有具体岗位可以留空；也可以在上传入口选择 JD 文件。"/></label>
    </div>
  </div>;
}
