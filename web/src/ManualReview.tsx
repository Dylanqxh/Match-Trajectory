import { useEffect, useRef, useState } from "react";
import { api, GenerationJob, Resume } from "./api";
import { manualReviewError } from "./exportFlow";

export function ManualReview({ record, issueIndex, onClose, onSaved, onEdit, onDraft }: {
  record: Resume; issueIndex: number; onClose: () => void; onSaved: (row: Resume) => void;
  onEdit: (itemId: string) => void; onDraft: () => void;
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
    void api<Pick<GenerationJob, "evidence">>(`/api/resumes/${record.id}/evidence`).then(job => {
      if (active) { setEvidence(job.evidence); setLoaded(true); }
    }).catch(error => { if (active) setError((error as Error).message); });
    return () => { active = false; previousFocus?.focus(); };
  }, [record.id, record.ai?.job_id]);
  const texts = [...record.content.sections.flatMap(section => [
    { id: section.id, text: [section.title, section.organization, section.role, section.start_date, section.end_date].filter(Boolean).join(" · ") }, ...section.items,
  ]), ...(record.content.education || []).map(e => ({ id: e.id, text: [e.school, e.degree, e.major, e.start_date, e.end_date].filter(Boolean).join(" · ") })), { id: "__summary", text: record.content.summary }];
  const currentText = issue.item_id === "document" ? "本次问题针对整体内容，请核对相关原文。" : texts.find(item => item.id === issue.item_id)?.text;
  async function save() {
    const validation = manualReviewError(selected, explanation, acknowledged);
    if (validation) { setError(validation); return; }
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
    <p>逐项选择适合的处理方式。原文支持时保存人工依据；内容不对时返回编辑修改或删除条目；不确定时先导出草稿。保存后继续下一项，全部处理后请明确确认接管。</p>
    <div className="notice"><strong>AI 提出的问题</strong><p>{issue.message}</p><strong>当前表述</strong><p>{currentText || "当前条目已删除，请关闭并重新载入。"}</p></div>
    <fieldset disabled={busy || !loaded}>
      <h3>原文支持：选择依据并保存人工核对</h3>
      <div className="manual-evidence-list">{evidence.map(item => <label className="manual-evidence" key={item.id}>
        <input type="checkbox" aria-label={`选择材料 ${item.id}`} checked={selected.includes(item.id)} onChange={event => setSelected(
          event.target.checked ? [...selected, item.id] : selected.filter(id => id !== item.id),
        )}/><span><strong>材料 {item.id}</strong><span>{item.text}</span></span></label>)}</div>
      <label>核对说明<textarea aria-label="核对说明" rows={3} minLength={10} maxLength={500} value={explanation} onChange={e => setExplanation(e.target.value)} placeholder="例如：原文说明本人负责该模块，候选保留了这个范围，没有写成独立负责整个项目。"/></label>
      <label className="checkbox-label"><input type="checkbox" checked={acknowledged} onChange={e => setAcknowledged(e.target.checked)}/>我已核对所选原文支持当前表述</label>
      <button className="primary" disabled={busy || !loaded} onClick={() => void save()}>保存人工核对结果</button>
      <p className="fine">保存需要：勾选原文、填写至少 10 个字的核对说明，并勾选确认。缺少内容时会明确提示，不会再显示为无法点击。</p>
    </fieldset>
    <div className="button-row"><button className="secondary" disabled={busy} onClick={() => onEdit(issue.item_id)}>内容不对，返回编辑</button>
      <button className="text-button" disabled={busy} onClick={onDraft}>不确定，先下载 Word 草稿</button></div>
    <p className="fine">修改后可重新审阅，或依据原文逐项核对。返回编辑和导出草稿均不会将事实问题标记为已解决。</p>
    {error && <p className="error" role="alert">{error}</p>}
  </section></div>;
}
