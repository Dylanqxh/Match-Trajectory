import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Section } from "./api";
import { ReviewIssues, groupIssues } from "./reviewIssues";

const sections: Section[] = [{
  id: "project", title: "项目经历", items: [
    { id: "query", text: "使用 Java 完成查询接口。" },
    { id: "tests", text: "编写测试记录，未上线。" },
  ],
}];

describe("review issues", () => {
  it("groups duplicate reasons and still names each sentence", () => {
    const issues = [
      { item_id: "query", severity: "blocking" as const, code: "unsupported", message: "段落出现了引用原文中没有的数字或数量口径，请删除或补充依据。" },
      { item_id: "tests", severity: "blocking" as const, code: "unsupported", message: "段落出现了引用原文中没有的数字或数量口径，请删除或补充依据。" },
      { item_id: "project", severity: "blocking" as const, code: "unsupported", message: "经历时间未在引用原文中出现，请删除推测日期或补充依据。" },
    ];
    const groups = groupIssues(issues, sections, []);
    expect(groups).toHaveLength(2);
    expect(groups[0].items.map(item => item.sentence)).toEqual(["使用 Java 完成查询接口。", "编写测试记录，未上线。"]);
    expect(groups[0].kind).toBe("缺少依据");

    const html = renderToStaticMarkup(<ReviewIssues issues={issues} sections={sections} education={[]} disabled={false} onResolve={() => undefined}/>);
    expect(html).toContain("2 类说明");
    expect(html).toContain("原句：使用 Java 完成查询接口。");
    expect(html).toContain("依据原文处理这一处");
    expect(html).not.toContain("自行核对并接管");
  });
});