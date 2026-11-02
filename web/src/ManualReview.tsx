import { useEffect, useRef, useState } from "react";
import { api, GenerationJob, Resume } from "./api";

export function ManualReview({ record, issueIndex, onClose, onSaved }: {
  record: Resume; issueIndex: number; onClose: () => void; onSaved: (row: Resume) => void;
}) {
  const [evidence, setEvidence] = useState<GenerationJob["evidence"]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [explanation, setExplanation] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const dialog = useRef<HTMLElement>(null);
  const issue = record.ai!.issues[issueIndex];
  useEffect(() => {
    let active = true;
    const previousFocus = document.activeElement as HTMLElement | null;
    dialog.current?.focus();
    void api<GenerationJob>(`/api/generation-jobs/${record.ai!.job_id}`).then(job => {
      if (active) { setEvidence(job.evidence); setLoaded(true); }
    }).catch(error => { if (active) setError((error as Error).message); });
    return () => { active = false; previousFocus?.focus(); };
  }, [record.id, record.ai?.job_id]);
  const texts = [...record.content.sections.flatMap(section => [
    { id: section.id, text: section.title }, ...section.items,
  ]), { id: "__summary", text: record.content.summary }];
  const currentText = issue.item_id === "document" ? "本次问题针对整体内容，请核对相关原文。" : texts.find(item => item.id === issue.item_id)?.text;
  async function save() {
    setBusy(true); setError("");
    try {
      const row = await api<Resume>(`/api/resumes/${record.id}/resolve-issue`, {
        expected_revision: record.revision, review_job_id: record.ai!.review_job_id, issue_index: issueIndex,
        evidence_ids: selected, explanation, acknowledged,
      });
      onSaved(row);
    } catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="modal-backdrop"><section ref={dialog} tabIndex={-1} className="modal manual-review-modal" role="dialog" aria-modal="true" aria-label="核对审阅问题">
    <button className="close" aria-label="关闭人工核对" disabled={busy} onClick={onClose}>×</button>
    <h2>核对审阅问题</h2>
    <p>如果原文已支持当前表述，可以选择依据并说明。此操作保存人工核对记录，保留 AI 原始结论；完成后仍需点击“自行核对并接管”。</p>
    <div className="notice"><strong>AI 提出的问题</strong><p>{issue.message}</p><strong>当前表述</strong><p>{currentText || "当前条目已删除，请关闭并重新载入。"}</p></div>
    <fieldset disabled={busy || !loaded}>
      <h3>选择支持这段表述的原文</h3>
      <div className="manual-evidence-list">{evidence.map(item => <label className="manual-evidence" key={item.id}>
        <input type="checkbox" aria-label={`选择材料 ${item.id}`} checked={selected.includes(item.id)} onChange={event => setSelected(
          event.target.checked ? [...selected, item.id] : selected.filter(id => id !== item.id),
        )}/><span><strong>材料 {item.id}</strong><span>{item.text}</span></span></label>)}</div>
      <label>核对说明<textarea aria-label="核对说明" rows={3} minLength={10} maxLength={500} value={explanation} onChange={e => setExplanation(e.target.value)} placeholder="例如：原文说明本人负责该模块，候选保留了这个范围，没有写成独立负责整个项目。"/></label>
      <label className="checkbox-label"><input type="checkbox" checked={acknowledged} onChange={e => setAcknowledged(e.target.checked)}/>我已核对所选原文支持当前表述</label>
      <button className="primary" disabled={busy || !acknowledged || selected.length === 0 || explanation.trim().length < 10} onClick={() => void save()}>保存人工核对结果</button>
    </fieldset>
    {error && <p className="error" role="alert">{error}</p>}
  </section></div>;
}
