import { describe, expect, it } from "vitest";
import { scrollEditorContainer } from "./editorScroll";

describe("scrollEditorContainer", () => {
  it("moves only the editor container back to the top", () => {
    const editor = { scrollTop: 640 };
    const preview = { scrollTop: 20 };
    scrollEditorContainer(editor);
    expect(editor.scrollTop).toBe(0);
    expect(preview.scrollTop).toBe(20);
    scrollEditorContainer(null);
  });
});
