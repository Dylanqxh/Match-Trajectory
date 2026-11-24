import { Content } from "./api";

function period(start?: string, end?: string): string {
  return [start?.trim(), end?.trim()].filter(Boolean).join(" — ");
}

function structuredMaterial(content: Content): string {
  const blocks: string[] = [];
  const summary = content.summary.trim();
  if (summary) blocks.push(`个人简介\n${summary}`);

  const education = (content.education || []).flatMap(row => {
    const line = [row.school.trim(), row.degree.trim(), row.major.trim(), period(row.start_date, row.end_date)]
      .filter(Boolean).join(" · ");
    return line ? [line] : [];
  });
  if (education.length) blocks.push(`教育背景\n${education.join("\n")}`);

  for (const section of content.sections || []) {
    const items = section.items.flatMap(item => item.text.trim() ? [`- ${item.text.trim()}`] : []);
    const meta = [section.organization?.trim(), section.role?.trim(), period(section.start_date, section.end_date)]
      .filter(Boolean).join(" · ");
    if (!meta && !items.length) continue;
    const title = section.title.trim() || "经历与实践";
    blocks.push([title, meta, ...items].filter(Boolean).join("\n"));
  }
  return blocks.join("\n\n");
}

export function buildGenerationSource(uploadedText: string, content: Content): string {
  const blocks: string[] = [];
  const uploaded = uploadedText.trim();
  const structured = structuredMaterial(content);
  if (uploaded) blocks.push(`已有简历 / 粘贴材料\n${uploaded}`);
  if (structured) blocks.push(`结构化填写\n${structured}`);
  return blocks.join("\n\n");
}

