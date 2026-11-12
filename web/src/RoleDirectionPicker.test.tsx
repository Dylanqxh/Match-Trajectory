import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { RoleDirectionPicker } from "./RoleDirectionPicker";

describe("RoleDirectionPicker", () => {
  it("offers every maintained specialist and an explicit general fallback", () => {
    const html = renderToStaticMarkup(<RoleDirectionPicker value="" onChange={() => undefined}/>);

    for (const label of ["产品经理", "后端研发", "算法／Agent", "数据分析", "内容／用户运营", "其他方向"]) {
      expect(html).toContain(label);
    }
    expect(html.match(/type="button"/g)).toHaveLength(6);
    expect(html).toContain("加载专项规则");
    expect(html).toContain("使用通用规则");
    expect(html).toContain("aria-label=" + '"选择简历方向"');
  });
});
