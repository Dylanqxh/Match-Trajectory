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
  plan: "材料分析", wait: "补问", draft: "简历写作", review: "事实审阅", revise: "修正", supervise: "主管", done: "完成",
};
const runningLine: Record<string, string> = {
  plan: "正在材料分析", wait: "正在等待补充", draft: "正在简历写作", review: "正在事实审阅",
  revise: "正在修正", supervise: "正在主管判断", done: "已完成",
};
const statusText: Record<NodeStatus, string> = {
  pending: "待进行", running: "进行中", success: "已完成", failed: "未通过", skipped: "未使用",
};

/** Edges from phases.ALLOWED. Wait is not a stored stage. */
export const EXECUTION_EDGES: ReadonlyArray<readonly [string, string]> = [
  ["plan", "plan"], ["plan", "draft"], ["plan", "wait"],
  ["draft", "draft"], ["draft", "review"],
  ["review", "review"], ["review", "revise"], ["review", "supervise"], ["review", "done"],
  ["revise", "revise"], ["revise", "review"],
  ["supervise", "supervise"], ["supervise", "revise"], ["supervise", "done"],
];

/** Compiled graph after a real wait. Not an ALLOWED source, and not a shortcut around plan. */
export const WAIT_RESUME_EDGES: ReadonlyArray<readonly [string, string, string]> = [
  ["wait", "draft", "回答后进入起草"],
  ["wait", "done", "取消或中断时结束"],
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
    status.supervise = "skipped";
    const nodes = order.map(id => ({ id, label: labels[id], status: status[id] }));
    return { nodes, successCount: 1, statusLine: runningLine.wait };
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

function traversed(receipts: StepReceipt[] = []): Set<string> {
  const edges = new Set<string>();
  let answeredWait = false;
  for (const receipt of receipts) {
    const from = stageOf(receipt);
    if (receipt.state === "waiting_input") {
      edges.add("plan>wait");
      answeredWait = true;
    }
    if (answeredWait && (from === "draft" || receipt.next_stage === "draft")) edges.add("wait>draft");
    if (receipt.next_stage && receipt.next_stage !== from) edges.add(`${from}>${receipt.next_stage}`);
    if (receipt.next_stage === from) edges.add(`${from}>${from}`);
    if (receipt.state === "ready") edges.add(`${from}>done`);
  }
  return edges;
}

function IconPaths({ id }: { id: string }) {
  const pen = { fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  if (id === "plan") return <><circle cx="10.5" cy="10.5" r="5.5" {...pen}/><path d="M15 15.5L19 19.5" {...pen}/></>;
  if (id === "draft") return <path d="M5 19l1.2-4.2L16.5 4.5a1.6 1.6 0 0 1 2.3 0l.7.7a1.6 1.6 0 0 1 0 2.3L9.2 17.8 5 19z" {...pen}/>;
  if (id === "review") return <path d="M12 3.5l7 2.4v6.2c0 4.2-2.8 6.8-7 8.4-4.2-1.6-7-4.2-7-8.4V5.9l7-2.4z" {...pen}/>;
  if (id === "wait") return <path d="M6 6.5h9.5a3 3 0 0 1 0 6H8.5L6 16.5V6.5z" {...pen}/>;
  if (id === "revise") return <><path d="M7 8H4v3" {...pen}/><path d="M4 8a8 8 0 1 1-1.2 4.5" {...pen}/></>;
  if (id === "done") return <path d="M5 12.5l4.2 4.2L19 7.5" {...pen}/>;
  return <><circle cx="12" cy="12" r="3" {...pen}/><path d="M12 4v2.5M12 17.5V20M4 12h2.5M17.5 12H20" {...pen}/></>;
}

function StageIcon({ id }: { id: string }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><IconPaths id={id}/></svg>;
}

function edgeTaken(edges: Set<string>, from: string, to: string): boolean {
  return edges.has(`${from}>${to}`);
}

export function AgentExecutionTrace({ receipts, currentStage, jobState }: {
  receipts?: StepReceipt[]; currentStage: string; jobState: string;
}) {
  const graph = buildExecutionGraph(receipts, currentStage, jobState);
  const taken = traversed(receipts);
  const supervise = graph.nodes.find(node => node.id === "supervise");
  const superviseUnused = supervise?.status === "skipped";
  const node = (id: string) => graph.nodes.find(item => item.id === id)!;
  const mark = (from: string, to: string) => edgeTaken(taken, from, to) ? "taken" : "allowed";
  const main = [node("plan"), node("draft"), node("review"), node("done")];
  return <section className="execution-graph" aria-label="生成阶段">
    <header>
      <div><span>当前状态</span><strong className="execution-status">{graph.statusLine}</strong></div>
      <small>已完成 {graph.successCount} 个节点</small>
    </header>
    <div className="stage-journey" aria-label="生成主流程">
      <h3>生成主流程</h3>
      <div className="stage-card-row">
        {main.map((spec, index) => <div className="stage-card-slot" key={spec.id}>
          {index > 0 && <span className={`stage-connector ${mark(main[index - 1].id, spec.id)}`} data-edge={`${main[index - 1].id}-${spec.id}`} aria-hidden="true"/>}
          <div className={`stage-card ${spec.status}`} data-stage-card={spec.id} data-status={spec.status}>
            <span className="stage-card-icon"><StageIcon id={spec.id}/></span>
            <div><strong>{spec.label}</strong><em>{statusText[spec.status]}</em></div>
            {spec.id === "plan" && <small data-edge="plan-plan">失败可重试</small>}
          </div>
        </div>)}
      </div>
    </div>
    <div className="stage-branches" aria-label="按需执行的阶段">
      <div className={`edge-row branch ${node("wait").status}`} data-branch="wait" data-status={node("wait").status}>
        <span className="branch-icon"><StageIcon id="wait"/></span><div><strong>需要时补问</strong><em>{statusText[node("wait").status]}</em><small>最多一轮；回答后进入起草，也可以直接跳过</small></div>
        <span data-edge="plan-wait"/><span data-edge="wait-draft"/>
      </div>
      <div className={`edge-row branch ${node("revise").status}`} data-branch="revise" data-status={node("revise").status}>
        <span className="branch-icon"><StageIcon id="revise"/></span><div><strong>发现问题时修正</strong><em>{statusText[node("revise").status]}</em><small>修正后回到事实审阅，不绕过检查</small></div>
        <span data-edge="review-revise"/><span data-edge="revise-review"/>
      </div>
      <div className={`edge-row branch ${supervise?.status || "pending"}`} data-branch="supervise" data-status={supervise?.status || "pending"}>
        <span className="branch-icon"><StageIcon id="supervise"/></span><div><strong>智能修正策略</strong><em>{superviseUnused ? "未启用" : statusText[supervise?.status || "pending"]}</em>
          <small>{superviseUnused ? "主管未启用；主流程仍可直接完成" : "可安排修正重点，再回审阅或进入完成"}</small></div>
        <span data-edge="review-supervise"/><span data-edge="supervise-revise"/><span data-edge="supervise-done"/>
      </div>
    </div>
  </section>;
}
