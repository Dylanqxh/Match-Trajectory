import { describe, expect, it } from "vitest";
import { Content } from "./api";
import { editorSectionCounts, sectionsForEditor, sectionKindsFor } from "./editorSections";

const content: Content = {
  name: "林然",
  target_role: "后端研发",
  contact: "lin@example.com",
  summary: "后端开发",
  education: [{ id: "edu", school: "海岚大学", degree: "本科", major: "软件工程" }],
  sections: [
    { id: "work", title: "实习经历", kind: "work", items: [] },
    { id: "project", title: "项目经历", kind: "project", items: [] },
    { id: "skill", title: "专业技能", kind: "skills", items: [] },
    { id: "campus", title: "校园经历", kind: "campus", items: [] },
    { id: "legacy", title: "其他经历", kind: "other", items: [] },
  ],
};

describe("editor section grouping", () => {
  it("maps every resume block to one stable editor group", () => {
    expect(sectionKindsFor("work")).toEqual(["work"]);
    expect(sectionKindsFor("project")).toEqual(["project"]);
    expect(sectionKindsFor("other")).toEqual(["skills", "campus", "research", "other"]);
    expect(editorSectionCounts(content)).toEqual({ basics: 4, education: 1, work: 1, project: 1, other: 3 });
  });

  it("moves a section between groups without changing its identity", () => {
    const moved = { ...content, sections: content.sections.map(row => row.id === "project" ? { ...row, kind: "work" } : row) };

    expect(sectionsForEditor(moved.sections, "project")).toEqual([]);
    expect(sectionsForEditor(moved.sections, "work").map(row => row.id)).toEqual(["work", "project"]);
  });
});
