import { Content, Section } from "./api";

export type EditorSectionKey = "basics" | "education" | "work" | "project" | "other";

export const editorSections: { key: EditorSectionKey; label: string; short: string }[] = [
  { key: "basics", label: "基本信息", short: "基本" },
  { key: "education", label: "教育背景", short: "教育" },
  { key: "work", label: "工作实习", short: "工作" },
  { key: "project", label: "项目经验", short: "项目" },
  { key: "other", label: "技能与其他", short: "其他" },
];

const kinds: Record<EditorSectionKey, string[]> = {
  basics: [], education: [], work: ["work"], project: ["project"],
  other: ["skills", "campus", "research", "other"],
};

export function sectionKindsFor(key: EditorSectionKey): string[] {
  return kinds[key];
}

export function sectionsForEditor(sections: Section[], key: EditorSectionKey): Section[] {
  const allowed = new Set(sectionKindsFor(key));
  return sections.filter(section => allowed.has(section.kind || "other"));
}

export function editorSectionCounts(content: Content): Record<EditorSectionKey, number> {
  return {
    basics: [content.name, content.target_role, content.contact, content.summary].filter(value => value.trim()).length,
    education: content.education.length,
    work: sectionsForEditor(content.sections, "work").length,
    project: sectionsForEditor(content.sections, "project").length,
    other: sectionsForEditor(content.sections, "other").length,
  };
}
