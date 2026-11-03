"""Execution adapters; business state and billing remain authoritative."""

from pathlib import Path
from typing import TypedDict

from app.providers import ProviderError

ENGINE_VERSION = "m15-v1"


class GraphState(TypedDict):
    job_id: str
    engine_version: str
    step_key: str


def projection(job):
    return {"job_id": job["id"], "engine_version": ENGINE_VERSION,
            "step_key": f"{job['stage']}:{job['revisions']}"}


async def run_engine(workflow, job):
    engine = job.get("engine", "legacy")
    if engine not in ("legacy", "langgraph", "supervisor"):
        raise ProviderError("任务执行器未知，不能自动切换；已有结果保留")
    if engine == "legacy":
        while True:
            current = workflow.jobs.get(job["id"])
            if current["state"] != "running" or current["run_token"] != job["run_token"]:
                return
            await workflow.execute_step(current, job["run_token"])
    if job.get("engine_version") != ENGINE_VERSION:
        raise ProviderError("执行图版本不兼容；请使用原版本继续或新建任务，已有结果保留")
    await run_graph(workflow, job)


async def run_graph(workflow, job):
    # Lazy imports keep pre-upgrade tasks independent from graph initialization.
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, interrupt

    def current():
        return workflow.jobs.get(job["id"])

    async def step(state):
        value = current()
        if value["state"] == "running" and value["run_token"] == job["run_token"]:
            # A successful business commit may lead the last checkpoint. Reconcile
            # its stage/revision first, rather than repeating the saved operation.
            if state["step_key"] == projection(value)["step_key"]:
                await workflow.execute_step(value, job["run_token"])
        return projection(current())

    def route(state):
        value = current()
        if value["state"] == "waiting_input":
            return "wait"
        if value["state"] != "running" or value["run_token"] != job["run_token"]:
            return END
        return value["stage"]

    def wait(state):
        value = current()
        if value["state"] == "waiting_input":
            interrupt({"question_group": value["question_group"]})
        value = current()
        if value["state"] == "running" and not value["answered"]:
            raise ProviderError("补问尚未回答，不能恢复生成")
        return projection(value)

    builder = StateGraph(GraphState)
    builder.add_node("dispatch", lambda state: projection(current()))
    for name in ("plan", "draft", "review", "revise", "supervise"):
        builder.add_node(name, step)
        builder.add_conditional_edges(name, route)
    builder.add_node("wait", wait)
    builder.add_conditional_edges("wait", route)
    builder.add_edge(START, "dispatch")
    builder.add_conditional_edges("dispatch", route)
    db_path = Path(workflow.store.engine.url.database).parent / "workflow-checkpoints.sqlite3"
    config = {"configurable": {"thread_id": job["id"]}, "recursion_limit": 48, "callbacks": []}
    async with AsyncSqliteSaver.from_conn_string(str(db_path)) as saver:
        graph = builder.compile(checkpointer=saver)
        snapshot = await graph.aget_state(config)
        if snapshot.next:
            interrupted = any(task.interrupts for task in snapshot.tasks)
            value = Command(resume={"question_group": job["question_group"]}) if interrupted and job["answered"] else None
        else:
            value = projection(job)
        await graph.ainvoke(value, config, durability="sync")
