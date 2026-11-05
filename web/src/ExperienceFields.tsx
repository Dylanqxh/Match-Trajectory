import { Section } from "./api";

export function ExperienceFields({ sections, onChange }: { sections: Section[]; onChange: (rows: Section[]) => void }) {
  function update(id: string, change: Partial<Section>) {
    onChange(sections.map(s => s.id === id ? { ...s, ...change } : s));
  }
  return <>{sections.map(section => <div className="section-card" key={section.id}>
    <div className="section-heading"><input aria-label="板块名称" value={section.title} maxLength={60} onChange={e => update(section.id, { title: e.target.value })}/>
      <button className="text-button" onClick={() => onChange(sections.filter(s => s.id !== section.id))} aria-label={`删除${section.title}板块`}>删除板块</button></div>
    <div className="two-fields"><label>经历类别<select aria-label={`${section.title}类别`} value={section.kind || "other"} onChange={e => update(section.id, { kind: e.target.value })}>
      <option value="project">项目</option><option value="work">工作 / 实习经历</option><option value="skills">专业技能</option><option value="campus">校园与荣誉</option><option value="research">科研经历（旧稿）</option><option value="other">其他（旧稿）</option></select></label>
      <label>组织／公司<input aria-label={`${section.title}组织`} value={section.organization || ""} maxLength={120} onChange={e => update(section.id, { organization: e.target.value })}/></label></div>
    <label>本人角色<input aria-label={`${section.title}角色`} value={section.role || ""} maxLength={80} onChange={e => update(section.id, { role: e.target.value })}/></label>
    <div className="two-fields"><label>开始时间<input aria-label={`${section.title}开始时间`} value={section.start_date || ""} maxLength={7} placeholder="YYYY 或 YYYY-MM" onChange={e => update(section.id, { start_date: e.target.value })}/></label>
      <label>结束时间<input aria-label={`${section.title}结束时间`} value={section.end_date || ""} maxLength={7} placeholder="YYYY-MM 或至今" onChange={e => update(section.id, { end_date: e.target.value })}/></label></div>
    {section.kind !== "skills" && section.kind !== "campus" && !section.start_date && !section.end_date && <p className="fine">时间未填写；已知时请补充。项目和工作经历按证据强度排列，时间只在强度相同时倒序。没有内容的板块不会出现在预览里。</p>}
    {section.items.map((item, index) => <div className="bullet-editor" key={item.id}><div className="item-row">
      <textarea aria-label={`${section.title}第${index + 1}条`} rows={2} value={item.text} maxLength={4000} onChange={e => update(section.id, { items: section.items.map(i => i.id === item.id ? { ...i, text: e.target.value, highlights: [] } : i) })}/>
      <button className="remove-item" aria-label={`删除第${index + 1}条`} onClick={() => update(section.id, { items: section.items.filter(i => i.id !== item.id) })}>×</button></div>
      <div className="field-help">{item.text.length} 字{item.text.length > 110 ? " · 建议压缩为一个核心贡献" : ""}</div>
      <label className="fine">重点短语（可选）<input aria-label={`${section.title}第${index + 1}条重点`} value={(item.highlights || []).join("；")} placeholder="最多2处，用分号分隔；须是正文原词" onChange={e => update(section.id, { items: section.items.map(i => i.id === item.id ? { ...i, highlights: e.target.value.split(/[；;]/).map(s => s.trim()).filter(Boolean) } : i) })}/></label>
    </div>)}
    <button className="text-button" disabled={section.items.length >= 30} onClick={() => update(section.id, { items: [...section.items, { id: crypto.randomUUID(), text: "", highlights: [] }] })}>＋ 添加一条</button>
  </div>)}<button className="secondary full" disabled={sections.length >= 12} onClick={() => onChange([...sections, { id: crypto.randomUUID(), title: "新增经历", kind: "project", items: [] }])}>＋ 添加板块</button></>;
}
