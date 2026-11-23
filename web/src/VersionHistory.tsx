import { useState } from "react";
import { Resume } from "./api";
import { describeVersion } from "./versionHistory";

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

export function VersionHistory({ rows, onClose }: { rows: Resume[]; onClose: () => void }) {
  const [openRevision, setOpenRevision] = useState<number | null>(null);
  const ordered = [...rows].sort((left, right) => right.revision - left.revision);
  return <div className="modal-backdrop"><section className="modal history-modal" role="dialog" aria-modal="true" aria-label="版本记录">
    <button className="close" onClick={onClose} aria-label="关闭版本记录">×</button>
    <h2>版本记录</h2>
    <p>已保存版本保持不变，当前共 {rows.length} 个。列表含保存时间、来源，以及能否对照上一版查看差异。</p>
    {ordered.map(row => {
      const previous = rows.find(item => item.revision === row.revision - 1) ?? null;
      const view = describeVersion(row, previous);
      const open = openRevision === row.revision;
      return <article className="history-row" key={row.revision}>
        <div className="history-row-head"><strong>v{view.revision} · {view.title}</strong><em>{view.diffNote}</em></div>
        <small>{formatTime(view.time)} · 来源 {view.source}</small>
        <p>{row.content.sections[0]?.items[0]?.text || row.content.summary || "空白草稿"}</p>
        {view.canViewDiff && <button className="text-button" type="button" aria-expanded={open} onClick={() => setOpenRevision(open ? null : row.revision)}>{open ? "收起差异" : "查看差异"}</button>}
        {open && <div className="history-diff">
          {view.changes.slice(0, 6).map(change => <article key={`${change.label}-${change.after}`}>
            <span>{change.label}</span>
            <p className="before">{change.before || "（空）"}</p>
            <p className="after">{change.after || "（已删除）"}</p>
          </article>)}
          {view.changes.length > 6 && <p className="fine">其余 {view.changes.length - 6} 处差异未展开。</p>}
        </div>}
      </article>;
    })}
  </section></div>;
}
