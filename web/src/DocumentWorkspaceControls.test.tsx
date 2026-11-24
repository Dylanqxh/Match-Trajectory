import { Children, isValidElement, ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DocumentViewToolbar } from "./DocumentViewToolbar";
import { DocumentWorkspaceControls } from "./DocumentWorkspaceControls";

describe("DocumentWorkspaceControls", () => {
  it("keeps view switching and review inside one left-side control region", () => {
    const html = renderToStaticMarkup(<DocumentWorkspaceControls
      title="林然 · 后端研发"
      saveStatus="v3 · 已保存"
      view="split"
      onViewChange={() => undefined}
      review={{ status: "当前有 2 处待逐项处理", onOpen: () => undefined }}
    />);

    expect(html).toContain('class="document-workspace-controls"');
    expect(html).toContain('aria-label="文档工作区控制"');
    expect(html).toContain("林然 · 后端研发");
    expect(html).toContain("v3 · 已保存");
    expect(html).toContain("并排查看");
    expect(html).toContain("专注预览");
    expect(html).toContain("专注编辑");
    expect(html).toContain("逐项核对与修正");
    expect(html).toContain("当前有 2 处待逐项处理");
  });

  it("forwards view and review actions", () => {
    let selected = "";
    let reviewOpened = false;
    const controls = DocumentWorkspaceControls({
      title: "未命名简历",
      saveStatus: "v1 · 未保存",
      view: "split",
      onViewChange: view => { selected = view; },
      review: { status: "当前版本尚未审阅", onOpen: () => { reviewOpened = true; } },
    });
    const children = Children.toArray(controls.props.children).filter(isValidElement) as ReactElement[];
    const toolbar = children.find(child => child.type === DocumentViewToolbar) as ReactElement<{ onChange: (view: "preview") => void }>;
    const review = children.find(child => child.type === "button") as ReactElement<{ onClick: () => void }>;

    toolbar.props.onChange("preview");
    review.props.onClick();

    expect(selected).toBe("preview");
    expect(reviewOpened).toBe(true);
  });

  it("omits the review action for documents without AI review data", () => {
    const html = renderToStaticMarkup(<DocumentWorkspaceControls
      title="手工简历"
      saveStatus="v1 · 已保存"
      view="preview"
      onViewChange={() => undefined}
    />);

    expect(html).toContain("专注预览");
    expect(html).not.toContain("逐项核对与修正");
  });
});
