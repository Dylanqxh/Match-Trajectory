export interface Item { id: string; text: string }
export interface Section { id: string; title: string; items: Item[] }
export interface Content { name: string; target_role: string; contact: string; summary: string; sections: Section[] }
export interface Resume { id: string; revision: number; confirmed_revision: number | null; origin: "manual" | "demo"; content: Content; updated_at: string }
export interface Summary { id: string; revision: number; origin: string; name: string; target_role: string }
export const emptyContent: Content = { name: "", target_role: "", contact: "", summary: "", sections: [] };

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
