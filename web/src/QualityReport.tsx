import { Education, Section, WritingQuality } from "./api";

const labels = { fit: "岗位适配", contribution: "个人贡献", evidence: "亮点证据", readability: "易读性" };
const actions: Record<string, string> = { keep: "保留", revise: "依据原文改进", need_input: "材料待补充", not_applicable: "不适用" };

export function QualityReport({ report, stale = false, sections = [], education = [] }: { report?: WritingQuality | null; stale?: boolean; sections?: Section[]; education?: Education[] }) {
  function location(id: string) {
    if (id === "document") return "整体";
    const row = sections.find(s => s.id === id);
    if (row) return row.title;
    for (const section of sections) {
      const item = section.items.find(i => i.id === id);
      if (item) return `${section.title}：${item.text.slice(0, 36)}${item.text.length > 36 ? "…" : ""}`;
    }
    const school = education.find(e => e.id === id);
    return school ? `教育经历：${[school.school, school.degree, school.major].filter(Boolean).join(" · ")}` : "相关信息";
  }
  return <section className="quality-report" aria-label="写作质量报告"><h3>写作质量</h3>
    {stale ? <p className="fine">正文已修改，上一版写作质量结论已失效，请保存并重新审阅。</p> : !report ? <p className="fine">尚未评估。旧版事实审阅通过不代表写作质量通过，可重新审阅当前版本。</p> : <>
      <p data-testid="writing-quality-state">{({ ready: "当前表达达到写作检查要求", revise: "当前表达仍需改进", insufficient: "材料存在缺口，按已有证据表达" })[report.status]}</p>
      <p className="fine">评分只辅助定位改进，不代表录用概率或“80%可用”。事实结论单独显示。</p>
      <dl>{report.dimensions.map(row => <div key={row.dimension}><dt><strong>{labels[row.dimension]}</strong> · {row.score === null ? "不适用" : `${row.score}/2`} · {actions[row.action] || row.action}</dt>
        <dd>{row.reason}<small>对应：{row.item_ids.map(location).join("；") || "整体"}</small>
          <details><summary>查看依据</summary>引用材料：{row.evidence_ids.join("、") || "暂无依据"}</details></dd></div>)}</dl>
      {report.interview_topics.length > 0 && <details><summary>面试可能追问什么（不写入简历）</summary><ul>{report.interview_topics.map((topic, index) =>
        <li key={index}>{topic.question}<small>对应 {location(topic.item_id)}</small></li>)}</ul></details>}
    </>}
  </section>;
}
