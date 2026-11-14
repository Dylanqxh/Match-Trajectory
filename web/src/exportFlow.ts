export function manualReviewError(selected: string[], explanation: string, acknowledged: boolean): string {
  if (selected.length === 0) return "请先勾选至少一条支持当前表述的原文材料。";
  if (explanation.trim().length < 10) return "请用至少 10 个字说明原文如何支持当前表述。";
  if (!acknowledged) return "请勾选确认，表示你已经核对所选原文。";
  return "";
}
