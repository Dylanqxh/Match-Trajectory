export type ProgressReason = "appear" | "followup" | "poll" | "ready" | "failed";
export type ProgressFocus = "progress-title" | "draft" | "retry" | "none";

export interface ProgressDecision {
  scroll: boolean;
  focus: ProgressFocus;
  followupUsed: boolean;
  outcomeFocused: "" | "draft" | "retry";
}

export function nextProgressFocus(input: {
  reason: ProgressReason;
  inView: boolean;
  editing: boolean;
  followupUsed: boolean;
  outcomeFocused: "" | "draft" | "retry";
}): ProgressDecision {
  const keep = {
    scroll: false,
    focus: "none" as ProgressFocus,
    followupUsed: input.followupUsed,
    outcomeFocused: input.outcomeFocused,
  };
  if (input.editing || input.reason === "poll") return keep;
  if (input.reason === "appear") return { ...keep, scroll: true, focus: "progress-title" };
  if (input.reason === "followup") {
    if (input.followupUsed || input.inView) return keep;
    return { ...keep, scroll: true, focus: "progress-title", followupUsed: true };
  }
  if (input.reason === "ready" && input.outcomeFocused !== "draft") {
    return { ...keep, focus: "draft", outcomeFocused: "draft" };
  }
  if (input.reason === "failed" && input.outcomeFocused !== "retry") {
    return { ...keep, focus: "retry", outcomeFocused: "retry" };
  }
  return keep;
}

export function isEditingOutside(active: { tagName?: string; isContentEditable?: boolean } | null, insidePanel: boolean): boolean {
  if (!active || insidePanel) return false;
  const tag = (active.tagName || "").toUpperCase();
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || Boolean(active.isContentEditable);
}
