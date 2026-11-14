import { ROLE_DIRECTIONS, RoleDirection } from "./roleDirections";

export function RoleDirectionPicker({ value, onChange }: {
  value: RoleDirection | "";
  onChange: (value: RoleDirection) => void;
}) {
  return <fieldset className="direction-picker" aria-label="选择简历方向">
    <legend>这份简历准备投什么方向？</legend>
    <p>先选方向，Skill 才知道该优先找哪类证据。不会从岗位名称偷偷猜测。</p>
    <div className="direction-grid">
      {ROLE_DIRECTIONS.map(option => <button type="button" key={option.value}
        className={`direction-option ${value === option.value ? "selected" : ""}`}
        aria-pressed={value === option.value}
        onClick={() => onChange(option.value)}>
        <span>{option.label}</span>
        <small>{option.hint}</small>
        <em>{option.specialist ? "加载专项规则" : "使用通用规则"}</em>
      </button>)}
    </div>
  </fieldset>;
}
