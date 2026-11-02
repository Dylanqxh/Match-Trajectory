export interface Item { id: string; text: string }
export interface Section { id: string; title: string; items: Item[] }
export interface Content { name: string; target_role: string; contact: string; summary: string; sections: Section[] }
export interface AIInfo { job_id: string; review_job_id: string; review_status: "passed" | "blocked" | "unreviewed"; manual_takeover: boolean; issues: GenerationIssue[] }
export interface Resume { id: string; revision: number; confirmed_revision: number | null; origin: "manual" | "demo" | "ai"; content: Content; updated_at: string; ai: AIInfo | null }
export interface Summary { id: string; revision: number; origin: string; name: string; target_role: string }
export const emptyContent: Content = { name: "", target_role: "", contact: "", summary: "", sections: [] };
export interface GenerationIssue { item_id: string; severity: "blocking" | "warning"; code: string; message: string; suggestion?: string; resolution?: { action: string; revision: number } }
export interface GenerationSummary { id: string; state: string; stage: string; target_role: string; mode: string; adopted_resume_id: string | null }
export interface GenerationJob extends GenerationSummary {
  service_warning?: string;
  input: { target_role: string }; calls: number; revisions: number; error: string; framework: boolean; question_group: string;
  plan: { questions: { id: string; text: string }[]; gaps: string[] } | null;
  draft: { summary: { text: string } | null; sections: { id: string; title: string; items: { id: string; text: string; fact_ids: string[] }[] }[] } | null;
  evidence: { id: string; text: string }[]; issues: GenerationIssue[]; review: { verdict: string } | null;
}

export async function request(path: string, options: RequestInit = {}): Promise<Response> {
  const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json", ...options.headers } });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : `请求失败（${response.status}）`);
  }
  return response;
}
export async function api<T>(path: string, body?: unknown, method = "POST"): Promise<T> {
  const response = await request(path, body === undefined ? {} : { method, body: JSON.stringify(body) });
  return response.json();
}
export function clean(content: Content): Content {
  return { ...content, sections: content.sections.map(section => ({ ...section,
    title: section.title.trim() || "经历与实践", items: section.items.filter(item => item.text.trim()) })) };
}
