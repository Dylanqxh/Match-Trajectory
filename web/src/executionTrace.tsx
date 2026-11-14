export interface StepReceipt {
  step: string;
  step_id?: string;
  next_stage: string;
  state: string;
  calls: number;
}

export interface AgentTraceItem {
  id: string;
  agent: string;
  action: string;
  detail: string;
  status: "done" | "running";
}

const roles: Record<string, { agent: string; action: string }> = {
  supervise: { agent: "调度 Agent", action: "判断下一步与修改范围" },
  plan: { agent: "材料分析 Agent", action: "提取事实并规划简历结构" },
  draft: { agent: "简历写作 Agent", action: "依据原文生成岗位化表达" },
  review: { agent: "事实审阅 Agent", action: "核对引用、事实与写作质量" },
  revise: { agent: "修改优化 Agent", action: "修正审阅发现的问题" },
};

function stageOf(receipt: StepReceipt): string {
  return receipt.step.split(":", 1)[0];
}

export function buildAgentTrace(receipts: StepReceipt[] = [], currentStage = "", jobState = ""): AgentTraceItem[] {
  const seen = new Set<string>();
  const result: AgentTraceItem[] = [];
  for (const receipt of receipts) {
    const id = receipt.step_id || `${receipt.step}:${receipt.next_stage}:${receipt.calls}`;
    if (seen.has(id)) continue;
    seen.add(id);
    const role = roles[stageOf(receipt)];
    if (!role) continue;
    result.push({ id, ...role, detail: `${role.action} · 第 ${receipt.calls} 次模型调用`, status: "done" });
  }
  const current = roles[currentStage];
  if (current && ["queued", "running", "waiting_input"].includes(jobState)) {
    result.push({ id: `current:${currentStage}`, ...current, detail: current.action, status: "running" });
  }
  return result;
}

export function AgentExecutionTrace({ receipts, currentStage, jobState }: {
  receipts?: StepReceipt[]; currentStage: string; jobState: string;
}) {
  const rows = buildAgentTrace(receipts, currentStage, jobState);
  if (!rows.length) return null;
  return <section className="agent-trace" aria-label="多 Agent 执行轨迹">
    <header><div><span>多 Agent 协作</span><strong>本次任务的真实执行轨迹</strong></div><small>{rows.filter(row => row.status === "done").length} 步已完成</small></header>
    <ol>{rows.map(row => <li className={row.status} key={row.id}>
      <i aria-hidden="true"/><div><strong>{row.agent}</strong><span>{row.action}</span></div><em>{row.status === "done" ? "完成" : "进行中"}</em>
    </li>)}</ol>
  </section>;
}
