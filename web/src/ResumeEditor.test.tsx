import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Content } from "./api";
import { ResumeEditor } from "./ResumeEditor";

const content: Content = {
  name: "林然",
  target_role: "后端研发",
  contact: "lin@example.com",
  summary: "个人简介",
  education: [{ id: "edu", school: "海岚大学", degree: "本科", major: "软件工程" }],
  sections: [
    { id: "work", title: "星河科技实习", kind: "work", items: [{ id: "w1", text: "完成接口开发" }] },
    { id: "project", title: "预约系统项目", kind: "project", items: [{ id: "p1", text: "完成预约流程" }] },
  ],
};

describe("ResumeEditor", () => {
  it("renders only the selected experience group while keeping all navigation tabs", () => {
    const html = renderToStaticMarkup(<ResumeEditor content={content} activeSection="work" disabled={false}
      onActiveSectionChange={() => undefined} onChange={() => undefined}/>);

    expect(html).toContain("基本信息");
    expect(html).toContain("教育背景");
    expect(html).toContain("工作实习");
    expect(html).toContain("项目经验");
    expect(html).toContain("星河科技实习");
    expect(html).not.toContain("预约系统项目");
  });

  it("renders education without leaking work and project fields into the form", () => {
    const html = renderToStaticMarkup(<ResumeEditor content={content} activeSection="education" disabled={false}
      onActiveSectionChange={() => undefined} onChange={() => undefined}/>);

    expect(html).toContain("海岚大学");
    expect(html).not.toContain("星河科技实习");
    expect(html).not.toContain("预约系统项目");
  });
});
