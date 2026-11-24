import { describe, expect, it } from "vitest";
import { recoveryCopy, stageActivity } from "./GenerationPanel";
import { isEditingOutside, modelPreflight, nextProgressFocus } from "./progressPlacement";

describe("progress placement", () => {
  it("scrolls a deep-scrolled submit into view and focuses the title once", () => {
    const first = nextProgressFocus({ reason: "appear", inView: false, editing: false, followupUsed: false, outcomeFocused: "" });
    expect(first).toMatchObject({ scroll: true, focus: "progress-title" });
    const poll = nextProgressFocus({ reason: "poll", inView: false, editing: false, followupUsed: false, outcomeFocused: "" });
    expect(poll).toMatchObject({ scroll: false, focus: "none" });
  });

  it("allows one more position after followup only when the panel is offscreen", () => {
    const hidden = nextProgressFocus({ reason: "followup", inView: false, editing: false, followupUsed: false, outcomeFocused: "" });
    expect(hidden).toMatchObject({ scroll: true, focus: "progress-title", followupUsed: true });
    const again = nextProgressFocus({ ...hidden, reason: "followup", inView: false, editing: false });
    expect(again.scroll).toBe(false);
    const visible = nextProgressFocus({ reason: "followup", inView: true, editing: false, followupUsed: false, outcomeFocused: "" });
    expect(visible.scroll).toBe(false);
  });

  it("does not steal focus while the user is editing, and focuses the outcome once", () => {
    expect(isEditingOutside({ tagName: "TEXTAREA" }, false)).toBe(true);
    expect(isEditingOutside({ tagName: "TEXTAREA" }, true)).toBe(false);
    const editing = nextProgressFocus({ reason: "appear", inView: false, editing: true, followupUsed: false, outcomeFocused: "" });
    expect(editing).toMatchObject({ scroll: false, focus: "none" });
    const ready = nextProgressFocus({ reason: "ready", inView: true, editing: false, followupUsed: false, outcomeFocused: "" });
    expect(ready.focus).toBe("draft");
    const again = nextProgressFocus({ reason: "ready", inView: true, editing: false, followupUsed: false, outcomeFocused: ready.outcomeFocused });
    expect(again.focus).toBe("none");
    const failed = nextProgressFocus({ reason: "failed", inView: true, editing: false, followupUsed: false, outcomeFocused: "" });
    expect(failed.focus).toBe("retry");
    const editingFailure = nextProgressFocus({ reason: "failed", inView: false, editing: true, followupUsed: false, outcomeFocused: "" });
    expect(editingFailure.focus).toBe("none");
  });

  it("does not say the materials are still being read while waiting for a choice", () => {
    expect(stageActivity("waiting_input", "plan")).toBe("正在等待补充");
    expect(stageActivity("running", "review")).toBe("正在事实审阅");
  });

  it("refuses to create a job when the model is not connected", () => {
    expect(modelPreflight(false)).toEqual({ createJob: false, notice: "尚未连接模型，不会创建生成任务。材料仍留在这里。" });
    expect(modelPreflight(true).createJob).toBe(true);
  });

  it("uses stage-specific recovery copy before a draft exists", () => {
    const plan = recoveryCopy({ draft: null, stage: "plan" });
    expect(plan).toContain("材料都还在");
    expect(plan).not.toContain("已经写进正文的内容不会凭空补上缺口");
    expect(recoveryCopy({ draft: null, stage: "review" })).not.toContain("已经写进正文的内容不会凭空补上缺口");
    expect(recoveryCopy({ draft: { summary: null, sections: [] }, stage: "review" })).toContain("已经写进正文的内容不会凭空补上缺口");
  });
});
