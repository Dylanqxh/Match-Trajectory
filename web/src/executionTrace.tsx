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
  return <section className="execution-graph" aria-label="生成阶段">
    <header>
      <div><span>当前状态</span><strong className="execution-status">{graph.statusLine}</strong></div>
      <small>已完成 {graph.successCount} 个节点</small>
    </header>
    <svg className="execution-wide" viewBox="0 0 760 250" role="img" aria-label="阶段图，含计划自环、补问分叉、回答后进入起草、修正回审阅，以及主管到完成">
      <defs>
        <marker id="stage-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 1.4 L 8 5 L 0 8.6 Z" fill="#2e6249"/>
        </marker>
      </defs>
      <title>阶段图</title>
      <Edge name="plan-draft" x1={118} y1={78} x2={188} y2={78} kind={mark("plan", "draft")} label="" />
      <Edge name="draft-review" x1={268} y1={78} x2={338} y2={78} kind={mark("draft", "review")} label="" />
      <Edge name="review-done" x1={448} y1={78} x2={548} y2={78} kind={mark("review", "done")} label="" />
      <path data-edge="plan-plan" data-kind={mark("plan", "plan")} d="M58 58c-28-8-36 28-8 40" className={`flow-edge ${mark("plan", "plan")}`} markerEnd="url(#stage-arrow)" />
      <text x={22} y={48} className="flow-label">再试</text>
      <path data-edge="plan-wait" data-kind={mark("plan", "wait")} d="M78 104v62" className={`flow-edge ${mark("plan", "wait")}`} markerEnd="url(#stage-arrow)" />
      <path data-edge="wait-draft" data-kind={mark("wait", "draft")} d="M112 176h116" className={`flow-edge resume ${mark("wait", "draft")}`} markerEnd="url(#stage-arrow)" />
      <text x={124} y={168} className="flow-label">回答后</text>
      <path data-edge="review-revise" data-kind={mark("review", "revise")} d="M392 104v62" className={`flow-edge ${mark("review", "revise")}`} markerEnd="url(#stage-arrow)" />
      <path data-edge="revise-review" data-kind={mark("revise", "review")} d="M360 176c-36 0-36-62 20-78" className={`flow-edge back ${mark("revise", "review")}`} markerEnd="url(#stage-arrow)" />
      <text x={300} y={168} className="flow-label">回到审阅</text>
      <path data-edge="review-supervise" data-kind={mark("review", "supervise")} d="M430 96c70 20 90 70 150 78" className={`flow-edge secondary ${mark("review", "supervise")}`} markerEnd="url(#stage-arrow)" />
      <path data-edge="supervise-revise" data-kind={mark("supervise", "revise")} d="M620 176H470" className={`flow-edge secondary ${mark("supervise", "revise")}`} markerEnd="url(#stage-arrow)" />
      <path data-edge="supervise-done" data-kind={mark("supervise", "done")} d="M640 150c40-20 40-52 8-62" className={`flow-edge secondary ${mark("supervise", "done")}`} markerEnd="url(#stage-arrow)" />
      <text x={648} y={132} className="flow-label">主管到完成</text>
      <GraphNode spec={node("plan")} x={78} y={78} />
      <GraphNode spec={node("draft")} x={228} y={78} />
      <GraphNode spec={node("review")} x={392} y={78} />
      <GraphNode spec={node("done")} x={612} y={78} />
      <GraphNode spec={node("wait")} x={78} y={176} />
      <GraphNode spec={node("revise")} x={392} y={176} />
      <GraphNode spec={node("supervise")} x={640} y={176} secondary={superviseUnused} />
    </svg>
    <div className="execution-narrow" aria-label="窄屏阶段关系">
      <div className="edge-row" data-stage="plan" data-status={node("plan").status}>
        <StageIcon id="plan"/><strong>材料分析</strong><em>{statusText[node("plan").status]}</em>
        <span data-edge="plan-plan" className="loop-mark">可再试</span>
      </div>
      <div className="edge-row branch" data-branch="wait" data-edge="plan-wait" data-status={node("wait").status}>
        <StageIcon id="wait"/><strong>补问</strong><em>{statusText[node("wait").status]}</em>
        <div className="edge-row resume" data-edge="wait-draft">回答后进入起草，不是跳过材料分析的捷径</div>
      </div>
      <div className="edge-row" data-stage="draft" data-edge="plan-draft" data-status={node("draft").status}>
        <StageIcon id="draft"/><strong>简历写作</strong><em>{statusText[node("draft").status]}</em>
      </div>
      <div className="edge-row" data-stage="review" data-edge="draft-review" data-status={node("review").status}>
        <StageIcon id="review"/><strong>事实审阅</strong><em>{statusText[node("review").status]}</em>
      </div>
      <div className="edge-row branch" data-branch="revise" data-edge="review-revise" data-status={node("revise").status}>
        <StageIcon id="revise"/><strong>修正</strong><em>{statusText[node("revise").status]}</em>
        <div className="edge-row back" data-edge="revise-review">回到事实审阅</div>
      </div>
      <div className="edge-row" data-stage="done" data-edge="review-done" data-status={node("done").status}>
        <StageIcon id="done"/><strong>完成</strong><em>{statusText[node("done").status]}</em>
      </div>
      <aside className={`supervise-note${superviseUnused ? " unused" : ""}`} data-edge="supervise-done" data-edge-also="review-supervise supervise-revise">
        <StageIcon id="supervise"/>
        <p>{superviseUnused ? "主管未启用。仍可从事实审阅进入，之后回到修正，或进入完成。" : `主管${statusText[supervise?.status || "pending"]}。事实审阅可进入主管，主管可回到修正，或进入完成。`}</p>
      </aside>
    </div>
  </section>;
}

function Edge({ name, x1, y1, x2, y2, kind }: { name: string; x1: number; y1: number; x2: number; y2: number; kind: string; label: string }) {
  return <line data-edge={name} data-kind={kind} x1={x1} y1={y1} x2={x2} y2={y2} className={`flow-edge ${kind}`} markerEnd="url(#stage-arrow)" />;
}

function GraphNode({ spec, x, y, secondary = false }: { spec: ExecutionNode; x: number; y: number; secondary?: boolean }) {
  return <g className={`flow-node ${spec.status}${secondary ? " secondary" : ""}`} data-stage={spec.id} data-status={spec.status} transform={`translate(${x} ${y})`}>
    <circle r={secondary ? 16 : 22} />
    <g transform="translate(-8 -8) scale(0.66)"><IconPaths id={spec.id}/></g>
    <text y={38} textAnchor="middle" className="flow-name">{spec.label}</text>
    <text y={52} textAnchor="middle" className="flow-state">{statusText[spec.status]}</text>
  </g>;
}
