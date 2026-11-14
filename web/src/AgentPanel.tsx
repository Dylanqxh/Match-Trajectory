import { FormEvent, useEffect, useRef, useState } from "react";
import { AgentApplyResponse, AgentProposal, AgentSession, AgentTarget, api, Resume } from "./api";

export function sameAgentTarget(left: AgentTarget | null, right: AgentTarget | null): boolean {
  return Boolean(left && right && left.type === right.type && left.id === right.id
    && left.revision === right.revision && left.state === right.state);
}

export function AgentProposalCard({ proposal }: { proposal: AgentProposal }) {
  const blocked = proposal.state === "blocked";
  return <section className={`agent-proposal ${blocked ? "blocked" : ""}`} aria-label="Agent 修改结果">
    <div className="agent-proposal-title"><div><span>{blocked ? "本次未保存" : "已自动保存"}</span><strong>{proposal.changes.length} 处改动</strong></div>
      <em>{blocked ? "存在事实风险" : `源自 v${proposal.base_revision}`}</em></div>
    {proposal.changes.map(change => <article className="agent-diff" key={change.item_id}>
      <div><span>修改前</span><p>{change.before || "（新增内容）"}</p></div>
      <div className="after"><span>修改后</span><p>{change.after || "（删除内容）"}</p></div>
      <footer><strong>{change.reason}</strong><small>{change.evidence_ids.length ? `引用 ${change.evidence_ids.length} 段原文` : "没有原文引用"}</small></footer>
    </article>)}
    {proposal.issues.length > 0 && <div className="agent-risk"><strong>未写入简历</strong>{proposal.issues.map((issue, index) => <p key={index}>{issue.message}</p>)}</div>}
  </section>;
}

export function AgentPanel({ target, modelReady, onOpenSettings, onApplied }: {
  target: AgentTarget | null; modelReady: boolean; onOpenSettings: () => void; onApplied: (row: Resume) => void;
}) {
  const [session, setSession] = useState<AgentSession | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const currentTarget = useRef<AgentTarget | null>(target); currentTarget.current = target;
  const log = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const requested = target;
    setSession(null); setError(""); setText("");
    if (!requested) return;
    let active = true;
    void api<AgentSession>("/api/agent/sessions", { target_type: requested.type, target_id: requested.id })
      .then(row => { if (active && sameAgentTarget(currentTarget.current, requested)) setSession(row); })
      .catch(reason => { if (active && sameAgentTarget(currentTarget.current, requested)) setError((reason as Error).message); });
    return () => { active = false; };
  }, [target?.type, target?.id, target?.revision, target?.state]);

  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight; }, [session?.messages.length]);

  async function act(work: () => Promise<void>) {
    setBusy(true); setError("");
    try { await work(); } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    const value = text.trim();
    if (!value || !session) return;
    await act(async () => {
      const result = await api<AgentApplyResponse>(`/api/agent/sessions/${session.id}/messages`, { text: value });
      setSession(result.session); setText("");
      if (result.resume) onApplied(result.resume);
    });
  }
  async function undo() {
    if (!session) return;
    await act(async () => {
      const result = await api<AgentApplyResponse>(`/api/agent/sessions/${session.id}/undo`, {});
      setSession(result.session);
      if (result.resume) onApplied(result.resume);
    });
  }

  const locked = busy || !session || !modelReady || Boolean(target?.blockedReason);
  const suggestions = ["把最长的一条压缩到一行", "更突出我本人负责的部分", "按目标岗位调整经历顺序"];

  return <aside className="agent-rail" aria-label="简历 Agent">
    <header className="agent-head">
      <div className="agent-mark">AI</div>
      <div><strong>简历 Agent</strong><small>自动保存 · 随时撤销</small></div>
      <span className={`agent-status ${busy ? "running" : ""}`}>{busy ? "正在思考" : "本地会话"}</span>
    </header>
    {!target ? <div className="agent-empty"><span>✦</span><strong>先选择一份简历或生成任务</strong><p>Agent 会绑定当前对象，读取它的版本和原文依据，再为你提出可核对的修改。</p></div> : <>
      <div className="agent-context"><span>{target.type === "resume" ? "正在修改" : "正在讨论"}</span><strong>{target.label}</strong>
        <small>{target.type === "resume" ? `已保存版本 v${target.revision}` : "生成任务候选"}</small>
        {session?.can_undo && <button className="text-button" type="button" disabled={busy} onClick={() => void undo()}>撤销上次修改</button>}</div>
      <div className="agent-body" ref={log}>
        {error && <div className="agent-error" role="alert">{error}</div>}
        {target.blockedReason && <div className="agent-note"><strong>先完成当前编辑</strong><p>{target.blockedReason}</p></div>}
        {!modelReady && <div className="agent-note"><strong>需要连接模型</strong><p>连接后，Agent 才能基于当前版本生成修改提案。</p><button className="text-button" onClick={onOpenSettings}>连接模型</button></div>}
        {!session && !error && <p className="chat-empty">正在连接这份简历…</p>}
        <div className="agent-log">{session?.messages.map((message, index) => <p className={`agent-message ${message.role}`} key={index}>{message.text}</p>)}</div>
        {session?.proposal && ["applied", "blocked"].includes(session.proposal.state) && <AgentProposalCard proposal={session.proposal}/>}
      </div>
      <form className="agent-compose" onSubmit={event => void send(event)}>
        <div className="agent-suggestions">{suggestions.map(value => <button type="button" key={value} disabled={locked} onClick={() => setText(value)}>{value}</button>)}</div>
        <label htmlFor="agent-message">告诉 Agent 想怎么改</label>
        <textarea id="agent-message" rows={4} maxLength={2000} value={text} disabled={locked}
          onChange={event => setText(event.target.value)} placeholder="例如：把项目第二条写得更简洁，但保留原文中的数字结果"/>
        <div><small>通过事实校验后自动保存；新增事实仍需原文依据。</small><button className="primary" type="submit" disabled={locked || !text.trim()}>发送并修改</button></div>
      </form>
    </>}
  </aside>;
}
