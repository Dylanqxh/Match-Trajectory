import { describe, expect, it } from "vitest";
import { assistantStartsOpen } from "./ChatPanel";

describe("assistantStartsOpen", () => {
  it("collapses first-time sessions but preserves an explicit open preference", () => {
    expect(assistantStartsOpen(null)).toBe(false);
    expect(assistantStartsOpen("0")).toBe(false);
    expect(assistantStartsOpen("1")).toBe(true);
  });
});
