import { describe, expect, it } from "vitest";
import { manualReviewError } from "./exportFlow";

describe("manualReviewError", () => {
  it("explains each missing manual review requirement instead of leaving a dead disabled button", () => {
    expect(manualReviewError([], "", false)).toContain("勾选至少一条");
    expect(manualReviewError(["e1"], "太短", false)).toContain("至少 10 个字");
    expect(manualReviewError(["e1"], "原文明确说明本人负责该模块", false)).toContain("勾选确认");
    expect(manualReviewError(["e1"], "原文明确说明本人负责该模块", true)).toBe("");
  });
});
