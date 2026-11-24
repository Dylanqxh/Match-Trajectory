export type DocumentView = "split" | "preview" | "edit";

const options: { value: DocumentView; label: string; hint: string }[] = [
  { value: "split", label: "并排查看", hint: "边改边看" },
  { value: "preview", label: "专注预览", hint: "放大整页" },
  { value: "edit", label: "专注编辑", hint: "集中填写" },
];

function ViewIcon({ view }: { view: DocumentView }) {
  const pen = { fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  if (view === "preview") return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3.5h8l3 3V20.5H7z" {...pen}/><path d="M15 3.5v3h3M9.5 11h6M9.5 14.5h6" {...pen}/></svg>;
  if (view === "edit") return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19l1.1-4 9.8-9.8a1.6 1.6 0 0 1 2.3 0l.6.6a1.6 1.6 0 0 1 0 2.3L9 17.9 5 19z" {...pen}/></svg>;
  return <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="5" width="7" height="14" rx="1.5" {...pen}/><rect x="13.5" y="5" width="7" height="14" rx="1.5" {...pen}/></svg>;
}

export function DocumentViewToolbar({ value, onChange }: { value: DocumentView; onChange: (view: DocumentView) => void }) {
  return <div className="document-view-toolbar" role="group" aria-label="文档工作区视图" data-document-view={value}>
    {options.map(option => <button type="button" key={option.value} aria-pressed={value === option.value}
      className={value === option.value ? "active" : ""} onClick={() => onChange(option.value)}>
      <ViewIcon view={option.value}/><span><strong>{option.label}</strong><small>{option.hint}</small></span>
    </button>)}
  </div>;
}
