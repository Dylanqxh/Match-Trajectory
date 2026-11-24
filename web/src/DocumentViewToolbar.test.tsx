import { Children, ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DocumentView, DocumentViewToolbar } from "./DocumentViewToolbar";

describe("DocumentViewToolbar", () => {
  it("offers split, preview, and edit views with one current choice", () => {
    for (const view of ["split", "preview", "edit"] as DocumentView[]) {
      const html = renderToStaticMarkup(<DocumentViewToolbar value={view} onChange={() => undefined}/>);
      expect(html).toContain("并排查看");
      expect(html).toContain("专注预览");
      expect(html).toContain("专注编辑");
      expect(html.match(/aria-pressed="true"/g)).toHaveLength(1);
      expect(html).toContain(`data-document-view="${view}"`);
    }
  });

  it("requests the view represented by the selected control", () => {
    let selected: DocumentView = "split";
    const toolbar = DocumentViewToolbar({ value: "split", onChange: view => { selected = view; } });
    const buttons = Children.toArray(toolbar.props.children) as ReactElement<{ onClick: () => void }>[];

    buttons[1].props.onClick();
    expect(selected).toBe("preview");
    buttons[2].props.onClick();
    expect(selected).toBe("edit");
  });
});
