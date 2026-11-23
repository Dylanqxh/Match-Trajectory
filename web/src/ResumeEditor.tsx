import { Content } from "./api";
import { EducationFields } from "./EducationFields";
import { ExperienceFields } from "./ExperienceFields";
import { EditorSectionKey, editorSectionCounts, editorSections, sectionKindsFor } from "./editorSections";
import { scrollEditorContainer } from "./editorScroll";

export interface ResumeEditorProps {
  content: Content;
  activeSection: EditorSectionKey;
  disabled: boolean;
  onActiveSectionChange: (section: EditorSectionKey) => void;
  onChange: (content: Content) => void;
}

const defaults: Record<Exclude<EditorSectionKey, "basics" | "education">, { kind: string; title: string }> = {
  work: { kind: "work", title: "工作 / 实习经历" },
  project: { kind: "project", title: "项目经历" },
  other: { kind: "skills", title: "专业技能" },
};

export function ResumeEditor({ content, activeSection, disabled, onActiveSectionChange, onChange }: ResumeEditorProps) {
  const counts = editorSectionCounts(content);
  const activeLabel = editorSections.find(row => row.key === activeSection)?.label || "简历内容";
  return <div className="resume-editor-workspace">
    <nav className="editor-section-nav" aria-label="简历填写板块">
      {editorSections.map(section => <button type="button" key={section.key}
        className={activeSection === section.key ? "active" : ""}
        aria-current={activeSection === section.key ? "page" : undefined}
        onClick={event => {
          onActiveSectionChange(section.key);
          const panel = event.currentTarget.closest(".editor-panel");
          if (panel instanceof HTMLElement) scrollEditorContainer(panel);
        }} disabled={disabled}>
        <span>{section.label}</span><small>{counts[section.key]}</small>
      </button>)}
    </nav>
    <fieldset className="editor-section-content" disabled={disabled}>
      {activeSection === "basics" && <section aria-label="基本信息表单">
        <div className="editor-section-heading"><h3>基本信息</h3><p>姓名与联系方式只保存在本机字段中。</p></div>
        <div className="two-fields"><label>姓名<input aria-label="姓名" value={content.name} maxLength={80} onChange={e => onChange({ ...content, name: e.target.value })}/></label>
          <label>目标岗位<input aria-label="目标岗位" value={content.target_role} maxLength={80} onChange={e => onChange({ ...content, target_role: e.target.value })}/></label></div>
        <label>联系方式<input aria-label="联系方式" value={content.contact} maxLength={300} onChange={e => onChange({ ...content, contact: e.target.value })}/></label>
        <label>个人简介（可留空）<textarea aria-label="个人简介" rows={4} value={content.summary} maxLength={2000} onChange={e => onChange({ ...content, summary: e.target.value })}/></label>
      </section>}
      {activeSection === "education" && <section aria-label="教育背景表单">
        <div className="editor-section-heading"><h3>教育背景</h3><p>学校、学历、专业与时间按事实填写。</p></div>
        <EducationFields rows={content.education || []} onChange={education => onChange({ ...content, education })}/>
        {!content.education?.length && <p className="notice">尚未填写固定教育信息；如正文已有教育段落，请确认后移入此处，避免重复。</p>}
      </section>}
      {activeSection !== "basics" && activeSection !== "education" && <section aria-label={`${activeLabel}表单`}>
        <div className="editor-section-heading"><h3>{activeLabel}</h3><p>当前只显示这个板块，切换不会丢失未保存内容。</p></div>
        <ExperienceFields sections={content.sections} visibleKinds={sectionKindsFor(activeSection)}
          defaultKind={defaults[activeSection].kind} defaultTitle={defaults[activeSection].title}
          onChange={sections => onChange({ ...content, sections })}/>
      </section>}
    </fieldset>
  </div>;
}
