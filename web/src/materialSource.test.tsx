import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Content } from "./api";
import { MaterialSourcePanel } from "./MaterialSourcePanel";
import { buildGenerationSource } from "./materialSource";

const content: Content = {
  name: "林然",
  target_role: "后端研发",
  contact: "lin@example.com",
  summary: "关注可靠交付",
  education: [{ id: "edu-1", school: "海岚大学", degree: "本科", major: "软件工程", start_date: "2022-09", end_date: "2026-06" }],
  sections: [{
    id: "work-1",
    title: "工作 / 实习经历",
    kind: "work",
    organization: "星河科技",
    role: "后端实习生",
    start_date: "2025-06",
    end_date: "2025-09",
    items: [
      { id: "item-1", text: "完成订单查询接口", highlights: [] },
      { id: "item-empty", text: "   ", highlights: [] },
    ],
  }],
};

describe("material source", () => {
  it("combines uploaded text and structured facts without local identity fields", () => {
    const text = buildGenerationSource("旧简历原文：负责接口联调。", content);

    expect(text).toContain("已有简历 / 粘贴材料\n旧简历原文：负责接口联调。");
    expect(text).toContain("结构化填写");
    expect(text).toContain("海岚大学 · 本科 · 软件工程 · 2022-09 — 2026-06");
    expect(text).toContain("星河科技 · 后端实习生 · 2025-06 — 2025-09");
    expect(text).toContain("- 完成订单查询接口");
    expect(text).toContain("个人简介\n关注可靠交付");
    expect(text).not.toContain("lin@example.com");
    expect(text).not.toContain("item-empty");
  });

  it("makes upload and blank-form routes equal choices while showing the selected editor", () => {
    const shared = {
      busy: false,
      content,
      source: "",
      jd: "",
      recognized: "",
      editorSection: "basics" as const,
      onPathChange: () => undefined,
      onContentChange: () => undefined,
      onSourceChange: () => undefined,
      onJdChange: () => undefined,
      onEditorSectionChange: () => undefined,
      onResume: () => undefined,
      onJd: () => undefined,
    };
    const upload = renderToStaticMarkup(<MaterialSourcePanel {...shared} path="upload"/>);
    const form = renderToStaticMarkup(<MaterialSourcePanel {...shared} path="form"/>);

    for (const html of [upload, form]) {
      expect(html).toContain("上传已有简历");
      expect(html).toContain("从空白表单填写");
      expect(html).toContain("可以组合使用");
    }
    expect(upload).toContain("上传旧简历");
    expect(upload).toContain("或直接粘贴经历");
    expect(upload).not.toContain("aria-label=\"简历填写板块\"");
    expect(form).toContain("aria-label=\"简历填写板块\"");
    expect(form).not.toContain("或直接粘贴经历");
  });
});
