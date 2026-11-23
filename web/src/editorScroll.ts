export function scrollEditorContainer(container: { scrollTop: number } | null) {
  if (!container) return;
  container.scrollTop = 0;
}
