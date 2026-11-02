export function ResumeText({ text, highlights = [] }: { text: string; highlights?: string[] }) {
  const phrases = [...new Set(highlights)].filter(h => h && text.includes(h)).sort((a, b) => b.length - a.length);
  const runs: { text: string; bold: boolean }[] = [];
  let cursor = 0;
  while (cursor < text.length) {
    const phrase = phrases.find(h => text.startsWith(h, cursor));
    if (phrase) { runs.push({ text: phrase, bold: true }); cursor += phrase.length; }
    else { runs.push({ text: text[cursor], bold: false }); cursor++; }
  }
  return <>{runs.map((run, index) => run.bold ? <strong key={index}>{run.text}</strong> : run.text)}</>;
}
