"""Explicit v2 business graph; v1/legacy are pinned compatibility adapters."""
from pathlib import Path
from typing import TypedDict

from app.budget import budget_for_job
from app.phases import ALLOWED, phase_key
from app.providers import ProviderError

ENGINE_VERSION = "m17-v2"


class GraphState(TypedDict):
    job_id: str
    engine_version: str
    step_key: str
    outcome: str


def projection(job, outcome="dispatch"):
    return {"job_id": job["id"], "engine_version": ENGINE_VERSION,
            "step_key": phase_key(job), "outcome": outcome}


async def run_engine(workflow, job):
    engine = job.get("engine", "legacy")
    if engine not in ("legacy", "langgraph", "supervisor"):
        raise ProviderError("任务执行器未知，不能自动切换；已有结果保留")
    if engine == "legacy" or job.get("engine_version") == "m15-v1":
        from app.execution_compat import run_engine as run_compat

        return await run_compat(workflow, job)
    if job.get("engine_version") != ENGINE_VERSION:
        raise ProviderError("执行图版本不兼容；已有结果保留，请使用原版本继续或新建任务")
    return await run_graph(workflow, job)


async def run_graph(workflow, job):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, interrupt

    from app.workflow import StaleRun

    def current():
        return workflow.jobs.get(job["id"])

    async def execute(state, stage, handler):
        value = current()
        if value["state"] != "running" or value["run_token"] != job["run_token"]:
            return projection(value, "done")
        if value["stage"] != stage or state["step_key"] != phase_key(value):
            return projection(value, "reconcile")
        try:
            result = await handler(value, job["run_token"])
            outcome = workflow.commit_stage(value, job["run_token"], result)
        except (ProviderError, StaleRun):
            raise
        except Exception:  # noqa: BLE001 -- framework checkpoints must never persist raw SDK/database errors.
            raise ProviderError("执行步骤异常，材料与已保存结果保留；请检查本机存储或稍后继续") from None
        return projection(current(), outcome)

    async def plan(state):
        return await execute(state, "plan", workflow.plan_stage)

    async def draft(state):
        return await execute(state, "draft", workflow.draft_stage)

    async def review(state):
        return await execute(state, "review", workflow.review_stage)

    async def revise(state):
        return await execute(state, "revise", workflow.revise_stage)

    async def supervise(state):
        return await execute(state, "supervise", workflow.supervise_stage)

    def dispatch(state):
        value = current()
        target = "wait" if value["state"] == "waiting_input" else value["stage"] if value["state"] == "running" else "done"
        return projection(value, target)

    def wait(state):
        value = current()
        if value["state"] == "waiting_input":
            answer = interrupt({"question_group": value["question_group"]})
            if not isinstance(answer, dict) or answer.get("question_group") != current()["question_group"]:
                raise ProviderError("补问组已变化，请刷新任务后继续")
        value = current()
        if value["state"] != "running" or value["run_token"] != job["run_token"]:
            return projection(value, "done")
        if not value["answered"]:
            raise ProviderError("补问尚未回答，不能恢复生成")
        return projection(value, "draft")

    builder = StateGraph(GraphState)
    builder.add_node("dispatch", dispatch)
    builder.add_edge(START, "dispatch")
    for name, handler in (("plan", plan), ("draft", draft), ("review", review), ("revise", revise), ("supervise", supervise)):
        builder.add_node(name, handler)
        paths = {target: END if target == "done" else target for target in ALLOWED[name]}
        paths.update(done=END, reconcile="dispatch")
        builder.add_conditional_edges(name, lambda state: state["outcome"], paths)
    builder.add_node("wait", wait)
    builder.add_conditional_edges("wait", lambda state: state["outcome"], {"draft": "draft", "done": END})
    builder.add_conditional_edges("dispatch", lambda state: state["outcome"],
                                  {**{name: name for name in ALLOWED}, "wait": "wait", "done": END})
    db_path = Path(workflow.store.engine.url.database).parent / "workflow-checkpoints.sqlite3"
    config = {"configurable": {"thread_id": job["id"]},
              "recursion_limit": budget_for_job(job).graph_recursion_limit, "callbacks": []}
    async with AsyncSqliteSaver.from_conn_string(str(db_path)) as saver:
        graph = builder.compile(checkpointer=saver)
        snapshot = await graph.aget_state(config)
        if snapshot.next:
            interrupted = any(task.interrupts for task in snapshot.tasks)
            value = Command(resume={"question_group": job["question_group"]}) if interrupted and job["answered"] else None
        else:
            value = projection(job)
        await graph.ainvoke(value, config, durability="sync")
