import { Education } from "./api";

export function EducationFields({ rows, onChange }: { rows: Education[]; onChange: (rows: Education[]) => void }) {
  function update(id: string, change: Partial<Education>) {
    onChange(rows.map(row => row.id === id ? { ...row, ...change } : row));
  }
  return <section className="education-fields"><h3>教育经历</h3>
    <p className="fine">学校、学历、专业按事实填写，系统固定呈现。时间可只填年份或年月；未知留空，在读可填“至今”。</p>
    {rows.map((row, index) => <div className="section-card" key={row.id}>
      <div className="two-fields"><label>学校名称<input aria-label={`教育${index + 1}学校`} value={row.school} maxLength={120} onChange={e => update(row.id, { school: e.target.value })}/></label>
        <label>学历与状态<input aria-label={`教育${index + 1}学历`} value={row.degree} maxLength={40} placeholder="如硕士（在读）、本科" onChange={e => update(row.id, { degree: e.target.value })}/></label></div>
      <label>专业<input aria-label={`教育${index + 1}专业`} value={row.major} maxLength={80} onChange={e => update(row.id, { major: e.target.value })}/></label>
      <div className="two-fields"><label>开始时间<input aria-label={`教育${index + 1}开始时间`} value={row.start_date || ""} placeholder="YYYY 或 YYYY-MM" maxLength={7} onChange={e => update(row.id, { start_date: e.target.value })}/></label>
        <label>结束时间<input aria-label={`教育${index + 1}结束时间`} value={row.end_date || ""} placeholder="YYYY-MM 或至今" maxLength={7} onChange={e => update(row.id, { end_date: e.target.value })}/></label></div>
      <button type="button" className="text-button" onClick={() => onChange(rows.filter(e => e.id !== row.id))}>删除这段教育</button>
    </div>)}
    <button type="button" className="secondary" disabled={rows.length >= 8} onClick={() => onChange([...rows, { id: `edu-${crypto.randomUUID()}`, school: "", degree: "", major: "", start_date: "", end_date: "" }])}>＋ 添加教育经历</button>
  </section>;
}
