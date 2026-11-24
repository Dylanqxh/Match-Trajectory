import { DocumentView, DocumentViewToolbar } from "./DocumentViewToolbar";

type ReviewAction = {
  status: string;
  onOpen: () => void;
};

type DocumentWorkspaceControlsProps = {
  title: string;
  saveStatus: string;
  view: DocumentView;
  onViewChange: (view: DocumentView) => void;
  review?: ReviewAction;
};

export function DocumentWorkspaceControls({ title, saveStatus, view, onViewChange, review }: DocumentWorkspaceControlsProps) {
  return <aside className="document-workspace-controls" aria-label="文档工作区控制">
    <div className="document-workspace-summary"><strong>{title}</strong><span>{saveStatus}</span></div>
    <DocumentViewToolbar value={view} onChange={onViewChange}/>
    {review && <button type="button" className="review-entry" onClick={review.onOpen}>
      <span>逐项核对与修正</span>
      <strong data-testid="ai-review-state">{review.status}</strong>
      <em>打开</em>
    </button>}
  </aside>;
}
