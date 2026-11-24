import { Education, GenerationIssue, Section } from "./api";

export interface LocatedIssue {
  index: number;
  issue: GenerationIssue;
  place: string;
  sentence: string;
  kind: string;
}

export interface IssueGroup {
  key: string;
  message: string;
  kind: string;
  items: LocatedIssue[];
}

export function issueKind(code: string): string {
  if (code === "conflict") return "与原文冲突";
  if (code === "reference") return "引用没有对上";
  if (code === "attribution") return "范围和原文不一致";
  return "缺少依据";
}

export function locateIssue(issue: GenerationIssue, sections: Section[], education: Education[]): Omit<LocatedIssue, "index"> {
  const section = sections.find(row => row.id === issue.item_id || row.items.some(item => item.id === issue.item_id));
  const item = section?.items.find(row => row.id === issue.item_id);
  const school = education.find(row => row.id === issue.item_id);
  const period = section ? [section.organization, section.role, section.start_date, section.end_date].filter(Boolean).join(" · ") : "";
  const sentence = item?.text || period || section?.items[0]?.text || [school?.school, school?.degree, school?.major].filter(Boolean).join(" · ") || "";
  const place = item && section ? section.title : section ? section.title : school ? "教育经历" : "相关信息";
  return { issue, place, sentence, kind: issueKind(issue.code) };
}

export function groupIssues(issues: GenerationIssue[], sections: Section[] = [], education: Education[] = []): IssueGroup[] {
  const groups = new Map<string, IssueGroup>();
  issues.forEach((issue, index) => {
    const located = locateIssue(issue, sections, education);
    const key = `${issue.code}\n${issue.message}`;
    const group = groups.get(key) || { key, message: issue.message, kind: located.kind, items: [] };
    group.items.push({ ...located, index });
    groups.set(key, group);
  });
  return [...groups.values()];
}

export function ReviewIssues({ issues, sections, education, disabled, onResolve }: {
  issues: GenerationIssue[];
  sections: Section[];
  education: Education[];
  disabled: boolean;
  onResolve: (index: number) => void;
}) {
  const groups = groupIssues(issues, sections, education);
  const blocking = issues.filter(issue => issue.severity === "blocking" && !["deleted", "source_reviewed"].includes(issue.resolution?.action || "")).length;
  return <div className="review-groups" data-groups={groups.length}>
    <p className="review-group-count">{groups.length} 类说明 · {issues.length} 处{blocking ? ` · ${blocking} 处仍需逐项处理` : ""}</p>
    {groups.map((group, index) => <details key={group.key} className="review-group" open={index === 0}>
      <summary>{group.kind} · {group.items.length} 处<span>{group.message}</span></summary>
      <ul>{group.items.map(item => <li key={item.index}>
        <strong>{item.place}</strong>
        {item.sentence && <p>原句：{item.sentence}</p>}
        <p>{item.kind}。{item.issue.message}</p>
        {item.issue.severity === "blocking" && !["deleted", "source_reviewed"].includes(item.issue.resolution?.action || "") &&
          <button type="button" className="text-button" disabled={disabled} onClick={() => onResolve(item.index)}>依据原文处理这一处</button>}
      </li>)}</ul>
    </details>)}
  </div>;
}
