export interface StepReceipt {
  step: string;
  step_id?: string;
  next_stage: string;
  state: string;
  calls: number;
}

export type NodeStatus = "pending" | "running" | "success" | "failed" | "skipped";

export interface ExecutionNode {
  id: string;
  label: string;
  status: NodeStatus;
}

export interface ExecutionGraph {
  nodes: ExecutionNode[];
  successCount: number;
  statusLine: string;
}

const order = ["plan", "wait", "draft", "review", "revise", "supervise", "done"] as const;
const labels: Record<(typeof order)[number], string> = {
  plan: "计划", wait: "补问", draft: "起草", review: "审阅", revise: "修正", supervise: "主管", done: "完成",
};
const runningLine: Record<string, string> = {
  plan: "正在阅读材料", wait: "正在等待补充", draft: "正在写初稿", review: "正在审阅",
  revise: "正在修改措辞", supervise: "正在决定是否修正", done: "已完成",
};
const statusText: Record<NodeStatus, string> = {
  pending: "待进行", running: "进行中", success: "已完成", failed: "未通过", skipped: "未使用",
};

/** Edges that exist in phases.ALLOWED, plus the wait fork the plan stage can take. */
export const EXECUTION_EDGES: ReadonlyArray<readonly [string, string]> = [
  ["plan", "plan"], ["plan", "draft"], ["plan", "wait"],
  ["draft", "draft"], ["draft", "review"],
  ["review", "review"], ["review", "revise"], ["review", "supervise"], ["review", "done"],
  ["revise", "revise"], ["revise", "review"],
  ["supervise", "supervise"], ["supervise", "revise"], ["supervise", "done"],
];

function stageOf(receipt: StepReceipt): string {
  return receipt.step.split(":", 1)[0];
}

export function buildExecutionGraph(receipts: StepReceipt[] = [], currentStage = "", jobState = ""): ExecutionGraph {
  const completed = new Set<string>();
  let sawWait = false;
  let sawSupervise = false;
  for (const receipt of receipts) {
    const stage = stageOf(receipt);
    if (stage === "supervise") sawSupervise = true;
    if (receipt.state === "waiting_input" || receipt.next_stage === "wait") sawWait = true;
    if (stage && (receipt.next_stage !== stage || receipt.state === "waiting_input" || receipt.state === "ready")) {
      completed.add(stage);
    }
    if (receipt.state === "ready") completed.add("done");
  }
  if (sawWait && jobState !== "waiting_input") completed.add("wait");

  const status = Object.fromEntries(order.map(id => [id, "pending"])) as Record<string, NodeStatus>;
  if (jobState === "waiting_input") {
    status.wait = "running";
    status.plan = "success";
  } else if (jobState === "queued" || jobState === "running") {
    if (currentStage in status) status[currentStage] = "running";
  } else if (jobState === "failed" || jobState === "interrupted") {
    if (currentStage in status && currentStage !== "done") status[currentStage] = "failed";
  } else if (jobState === "ready") {
    status.done = "success";
  }
  for (const id of completed) {
    if (status[id] === "pending") status[id] = "success";
  }
  if ((jobState === "queued" || jobState === "running") && currentStage in status) status[currentStage] = "running";
  if (!sawSupervise && status.supervise !== "running" && status.supervise !== "failed") status.supervise = "skipped";
  if (!sawWait && status.wait === "pending") {
    const movedOn = ["draft", "review", "revise", "supervise", "done"].some(id => status[id] !== "pending");
    if (movedOn) status.wait = "skipped";
  }

  const nodes = order.map(id => ({ id, label: labels[id], status: status[id] }));
  const successCount = nodes.filter(node => node.status === "success").length;
  let statusLine = "正在准备";
  if (jobState === "ready") statusLine = "已完成";
  else if (jobState === "waiting_input") statusLine = runningLine.wait;
  else if (jobState === "failed" || jobState === "interrupted") statusLine = `停在${labels[currentStage as keyof typeof labels] || "当前步骤"}，材料仍在`;
  else if (jobState === "queued") statusLine = "排队中";
  else if (currentStage in runningLine) statusLine = runningLine[currentStage];
  return { nodes, successCount, statusLine };
}

export function AgentExecutionTrace({ receipts, currentStage, jobState }: {
  receipts?: StepReceipt[]; currentStage: string; jobState: string;
}) {
  const graph = buildExecutionGraph(receipts, currentStage, jobState);
  return <section className="execution-graph" aria-label="生成阶段">
    <header>
      <div><span>当前状态</span><strong className="execution-status">{graph.statusLine}</strong></div>
      <small>已完成 {graph.successCount} 个节点</small>
    </header>
    <ol className="execution-nodes">{graph.nodes.map(node => <li key={node.id} data-stage={node.id} data-status={node.status} className={node.status}>
      <strong>{node.label}</strong><em>{statusText[node.status]}</em>
    </li>)}</ol>
    <p className="execution-edges">阶段关系：计划可回到计划，也可进入起草或补问；修正会回到审阅。没有用到的主管保持未使用。</p>
  </section>;
}
