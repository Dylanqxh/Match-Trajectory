import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { WorkspaceSidebar } from "./WorkspaceSidebar";

describe("WorkspaceSidebar", () => {
  it("renders generation history beneath its resume instead of as a peer list", () => {
    const html = renderToStaticMarkup(<WorkspaceSidebar
      resumes={[{ id: "r1", revision: 2, origin: "ai", name: "林然后端简历", target_role: "后端研发" }]}
      jobs={[{ id: "j1", resume_id: "r1", state: "ready", stage: "done", target_role: "后端研发", mode: "generate",
        adopted_resume_id: "r1", created_at: "2026-11-14T00:00:00Z", updated_at: "2026-11-14T00:00:00Z" }]}
      selectedResumeId="r1" selectedJobId={null} disabled={false}
      onSelectResume={() => undefined} onDeleteResume={() => undefined}
      onSelectJob={() => undefined} onDeleteJob={() => undefined}/>);

    expect(html).toContain("林然后端简历");
    expect(html).toContain("删除简历 林然后端简历");
    expect(html).not.toContain(">删除<");
    expect(html).toContain("相关任务 1");
    expect(html.indexOf("林然后端简历")).toBeLessThan(html.indexOf("生成初稿"));
    expect(html).not.toContain("我的简历");
  });
});
