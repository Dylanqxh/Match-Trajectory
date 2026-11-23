import { describe, expect, it } from "vitest";
import { Content, Resume } from "./api";
import { describeVersion } from "./versionHistory";

const content: Content = {
  name: "陈亦宁",
  target_role: "Java 后端开发",
  contact: "demo@example.com",
  summary: "课程项目",
  education: [],
  sections: [{ id: "projects", title: "项目经历", items: [{ id: "own", text: "完成预约查询接口。" }] }],
};

function resume(revision: number, text: string, origin: Resume["origin"] = "ai"): Resume {
  return {
    id: "resume-1", revision, confirmed_revision: null, origin, updated_at: "2026-11-15T06:30:00Z", ai: null,
    content: { ...content, sections: [{ ...content.sections[0], items: [{ id: "own", text }] }] },
  };
}

describe("describeVersion", () => {
  it("marks the first saved version and names its source", () => {
    const view = describeVersion(resume(1, "完成预约查询接口。", "demo"), null);

    expect(view.source).toBe("虚构示例");
    expect(view.diffNote).toBe("首个版本");
    expect(view.canViewDiff).toBe(false);
    expect(view.time).toBe("2026-11-15T06:30:00Z");
  });

  it("offers a diff only when the previous version changed", () => {
    const changed = describeVersion(resume(2, "完成预约查询与取消接口。"), resume(1, "完成预约查询接口。"));
    const same = describeVersion(resume(3, "完成预约查询与取消接口。"), resume(2, "完成预约查询与取消接口。"));

    expect(changed.canViewDiff).toBe(true);
    expect(changed.diffNote).toBe("可查看差异");
    expect(changed.changes[0]).toMatchObject({ before: "完成预约查询接口。", after: "完成预约查询与取消接口。" });
    expect(same.canViewDiff).toBe(false);
    expect(same.diffNote).toBe("与上一版正文相同");
    expect(changed.source).toBe("AI 整理");
  });
});
