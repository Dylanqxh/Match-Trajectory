export type RoleDirection = "product" | "backend" | "frontend" | "testing" | "data-engineering" | "algorithm" | "data-analysis" | "operations" | "other";

export interface RoleDirectionOption {
  value: RoleDirection;
  label: string;
  hint: string;
  specialist: boolean;
}

export const ROLE_DIRECTIONS: RoleDirectionOption[] = [
  { value: "product", label: "产品经理", hint: "用户、取舍、机制与验证", specialist: true },
  { value: "backend", label: "后端研发", hint: "模块、约束、可靠性与交付", specialist: true },
  { value: "frontend", label: "前端研发", hint: "交互、状态、性能、兼容性与交付", specialist: true },
  { value: "testing", label: "测试／质量保障", hint: "风险、用例、自动化、缺陷与质量闭环", specialist: true },
  { value: "data-engineering", label: "数据开发／数据工程", hint: "链路、口径、对账、稳定性与交付", specialist: true },
  { value: "algorithm", label: "算法／Agent", hint: "任务、数据、评测与落地边界", specialist: true },
  { value: "data-analysis", label: "数据分析", hint: "问题、口径、结论与行动", specialist: true },
  { value: "operations", label: "内容／用户运营", hint: "对象、策略、执行与结果", specialist: true },
  { value: "other", label: "其他方向", hint: "使用通用规则，不假装专项验证", specialist: false },
];
