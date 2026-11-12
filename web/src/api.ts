export interface Period { start_date?: string; end_date?: string }
export interface Education extends Period { id: string; school: string; degree: string; major: string }
export interface Item { id: string; text: string; highlights?: string[] }
export interface Section extends Period { id: string; title: string; kind?: string; organization?: string; role?: string; items: Item[] }
export interface Content { name: string; target_role: string; contact: string; summary: string; education: Education[]; sections: Section[] }
export interface WritingQuality {
  status: "ready" | "revise" | "insufficient";
  dimensions: { dimension: "fit" | "contribution" | "evidence" | "readability"; score: number | null; reason: string; item_ids: string[]; evidence_ids: string[]; action: string }[];
  interview_topics: { item_id: string; question: string; evidence_ids: string[] }[];
}
export interface AIInfo { job_id: string; review_job_id: string; review_status: "passed" | "blocked" | "unreviewed"; manual_takeover: boolean; issues: GenerationIssue[]; quality?: WritingQuality | null }
export interface Resume { id: string; revision: number; confirmed_revision: number | null; origin: "manual" | "demo" | "ai"; content: Content; updated_at: string; ai: AIInfo | null }
export interface Summary { id: string; revision: number; origin: string; name: string; target_role: string }
export const emptyContent: Content = { name: "", target_role: "", contact: "", summary: "", education: [], sections: [] };
export interface GenerationIssue { item_id: string; severity: "blocking" | "warning"; code: string; message: string; suggestion?: string; resolution?: { action: string; revision: number; explanation?: string; evidence_ids?: string[] } }
export function unresolvedBlocking(issue: GenerationIssue): boolean {
  return issue.severity === "blocking" && !["deleted", "source_reviewed"].includes(issue.resolution?.action || "");
}
export interface GenerationSummary { id: string; state: string; stage: string; target_role: string; mode: string; adopted_resume_id: string | null }
export interface GenerationJob extends GenerationSummary {
  engine?: string; engine_version?: string; stop_reason?: string;
  budget_policy?: { version: string; max_calls: number; max_revisions: number; total_ms: number };
  step_receipts?: { step: string; next_stage: string; state: string; calls: number }[];
  continuation?: { allowed: boolean; reason: string };
  last_diagnostic?: { category: string; fields: { path: string; type: string; rule?: string }[]; finish_reason?: string };
  service_warning?: string;
  input: { target_role: string; career_stage?: string; has_career_gap?: boolean }; calls: number; revisions: number; error: string; framework: boolean; question_group: string;
  skill?: { role: string; version: string; resources?: string[]; stage_resources?: Record<string, string[]> };
  plan: { questions: { id: string; text: string }[]; gaps: string[] } | null;
  coverage_notes?: string[];
  draft: { summary: { text: string } | null; education?: Education[]; sections: Section[] } | null;
  evidence: { id: string; text: string }[]; issues: GenerationIssue[]; review: { verdict: string; quality?: WritingQuality | null } | null;
}

export async function request(path: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const labels: Record<string, string> = { education: "教育经历", sections: "经历", items: "条目", name: "姓名", contact: "联系方式", school: "学校", degree: "学历", major: "专业", start_date: "开始时间", end_date: "结束时间", highlights: "重点短语", text: "正文" };
    const fields = Array.isArray(error.detail) ? error.detail.slice(0, 3).map((e: { loc?: (string | number)[] }) =>
      (e.loc || []).slice(1).map(k => typeof k === "number" ? `第${k + 1}项` : labels[k] || "输入").join("／")).join("、") : "";
    throw new Error(typeof error.detail === "string" ? error.detail : fields ? `请检查${fields}：日期用 YYYY 或 YYYY-MM；重点须为正文短语，最多2处且不过量。` : `请求失败（${response.status}）`);
  }
  return response;
}
export interface ChatMessage { role: "user" | "assistant"; text: string }
export interface ChatSession {
  id: string;
  messages: ChatMessage[];
  collected: { name: string; contact: string; target_role: string; role_direction: string; source_text: string; jd: string; career_stage: string };
  job_id: string | null;
  job_state: string | null;
  questions: { id: string; text: string }[];
  coverage_notes: string[];
}
export interface UploadPreview { id: string; text: string; reliable: boolean; reason: string; warnings: string[]; pages: number; kind: string; name?: string }
export async function api<T>(path: string, body?: unknown, method = "POST"): Promise<T> {
  const response = await request(path, body === undefined ? {} : { method, body: JSON.stringify(body) });
  return response.json();
}
export function clean(content: Content): Content {
  return { ...content, education: (content.education || []).filter(e => e.school.trim() || e.degree.trim() || e.major.trim()), sections: content.sections.map(section => ({ ...section,
    title: section.title.trim() || "经历与实践", items: section.items.filter(item => item.text.trim()) })) };
}
