import { Content, Resume } from "./api";

const originLabels: Record<Resume["origin"], string> = {
  demo: "虚构示例",
  ai: "AI 整理",
  manual: "手工编辑",
};

export interface VersionChange {
  label: string;
  before: string;
  after: string;
}

export interface VersionView {
  revision: number;
  title: string;
  time: string;
  source: string;
  canViewDiff: boolean;
  diffNote: string;
  changes: VersionChange[];
}

function lines(content: Content): { label: string; text: string }[] {
  const rows = [
    { label: "姓名", text: content.name.trim() },
    { label: "目标岗位", text: content.target_role.trim() },
    { label: "联系方式", text: content.contact.trim() },
    { label: "简介", text: content.summary.trim() },
  ];
  for (const [index, row] of content.education.entries()) {
    rows.push({
      label: `教育 ${index + 1}`,
      text: [row.school, row.degree, row.major, row.start_date, row.end_date].map(value => value?.trim() || "").filter(Boolean).join(" · "),
    });
  }
  for (const section of content.sections) {
    const title = section.title.trim() || "经历";
    rows.push({
      label: title,
      text: [section.organization, section.role, section.start_date, section.end_date].map(value => value?.trim() || "").filter(Boolean).join(" · "),
    });
    section.items.forEach((item, index) => rows.push({ label: `${title} · 第 ${index + 1} 条`, text: item.text.trim() }));
  }
  return rows;
}

export function describeVersion(row: Resume, previous: Resume | null): VersionView {
  const current = lines(row.content);
  const prior = previous ? lines(previous.content) : [];
  const changes: VersionChange[] = [];
  for (let index = 0; index < Math.max(current.length, prior.length); index += 1) {
    const before = prior[index]?.text || "";
    const after = current[index]?.text || "";
    if (before !== after) changes.push({ label: current[index]?.label || prior[index]?.label || "内容", before, after });
  }
  const canViewDiff = Boolean(previous) && changes.length > 0;
  return {
    revision: row.revision,
    title: row.content.name.trim() || "未命名",
    time: row.updated_at,
    source: originLabels[row.origin] || "已保存版本",
    canViewDiff,
    diffNote: !previous ? "首个版本" : canViewDiff ? "可查看差异" : "与上一版正文相同",
    changes,
  };
}
