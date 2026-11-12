import asyncio
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import key_store, providers
from app import uploads as upload_text
from app.budget import DEFAULT_POLICY
from app.chat import ChatMessageInput, ChatService
from app.demo import demo_content
from app.generation_models import AnswerInput, GenerationInput, ResolveIssueInput
from app.intake import ParseRequest, parse_material
from app.jobs import JobStore
from app.lifecycle import Lifecycle
from app.model_client import ModelClient, ModelRegistry
from app.models import (
    CreateResume,
    ExportRequest,
    Item,
    ResumeContent,
    RevisionRequest,
    SaveResume,
    Section,
)
from app.resume_agent import AgentMessageInput, AgentService, AgentTargetInput
from app.store import Conflict, NotFound, ResumeStore
from app.workflow import Workflow


class ReviewRequest(RevisionRequest):
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,80}$")


class TakeoverRequest(RevisionRequest):
    acknowledged: bool


class ProviderSetup(providers.ProviderConfig):
    remember: bool = False


def is_local_page_origin(origin: str) -> bool:
    parts = urlsplit(origin)
    return (
        parts.scheme == "http"
        and parts.hostname in {"localhost", "127.0.0.1"}
        and parts.username is None
        and parts.password is None
        and parts.path in {"", "/"}
        and not parts.query
        and not parts.fragment
    )


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def create_app(data_dir: Path, *, web_dir: Path | None = None, model_client=None) -> FastAPI:
    store = ResumeStore(data_dir / "resumes.sqlite3")
    jobs = JobStore(store)
    registry = ModelRegistry()
    client = model_client or ModelClient()
    workflow = Workflow(store, jobs, registry, client)
    lifecycle = Lifecycle(store, jobs, data_dir)

    @asynccontextmanager
    async def lifespan(app):
        remembered = key_store.load(data_dir)
        if remembered:
            try:
                config = providers.ProviderConfig(provider=remembered["provider"], base_url=remembered["base_url"],
                                                  model=remembered["model"], api_key=remembered["api_key"])
                registry.register(config)
                secret = remembered["api_key"]
                app.state.provider = {"provider": config.provider, "base_url": config.base_url, "model": config.model,
                                      "configured": True, "key_mask": "••••" + (secret[-4:] if len(secret) > 8 else ""),
                                      "json_probe_passed": False, "resume_generation_verified": False, "key_storage": "keyring",
                                      "message": "已从系统钥匙串恢复连接。"}
                app.state.provider_key = secret
                app.state.key_storage = "keyring"
            except Exception:  # noqa: BLE001 -- a bad saved key must not stop startup or print the secret
                app.state.key_storage = "memory"
        lifecycle.retry_cleanup()
        await workflow.start()
        try:
            yield
        finally:
            await workflow.close()
            store.engine.dispose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    app.state.data_dir = data_dir
    app.state.provider = None
    app.state.provider_key = None
    app.state.key_storage = "memory"
    app.state.workflow = workflow
    chat = ChatService(store.engine, workflow)
    agent = AgentService(workflow)
    session = secrets.token_urlsafe(32)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])

    @app.middleware("http")
    async def local_session(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and not is_local_page_origin(origin):
                return JSONResponse({"detail": "仅接受本地页面的请求"}, status_code=403)
            if request.url.path != "/api/session":
                cookie = request.cookies.get("mt_session", "")
                if not secrets.compare_digest(cookie, session):
                    return JSONResponse({"detail": "请从本机工作台打开"}, status_code=401)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        return response

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(NotFound)
    async def not_found_handler(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        return JSONResponse({"detail": "输入不符合要求，请检查长度、空段落和字段类型",
                             "fields": [".".join(map(str, error["loc"])) for error in exc.errors()]}, status_code=422)

    @app.exception_handler(ValueError)
    async def generation_validation_handler(request, exc):
        message = "当前内容不符合处理要求，请检查材料长度与正文结构" if isinstance(exc, ValidationError) else str(exc)
        return JSONResponse({"detail": message}, status_code=422)

    @app.get("/health")
    def health():
        return {"status": "ok", "milestone": "m1.7", "ai_generation": True, "worker_warning": workflow.service_warning}

    @app.get("/api/session")
    def initialize_session():
        response = JSONResponse({"status": "ready", "milestone": "m1.7"})
        response.set_cookie("mt_session", session, httponly=True, samesite="strict", path="/")
        return response

    @app.get("/api/resumes")
    def list_resumes():
        return store.list()

    @app.post("/api/resumes", status_code=201)
    def create_resume(body: CreateResume):
        text = body.source_text
        items = [Item(id=f"material-{i // 4000}", text=text[i:i + 4000])
                 for i in range(0, len(text), 4000) if text[i:i + 4000].strip()]
        sections = [Section(id="experience", title="经历与实践", items=items)] if items else []
        content = ResumeContent(name=body.name, target_role=body.target_role, contact=body.contact, education=body.education, sections=sections)
        return store.create(content, "manual", text)

    @app.post("/api/demo", status_code=201)
    def create_demo():
        return store.create(demo_content(), "demo")

    @app.get("/api/resumes/{resume_id}")
    def get_resume(resume_id: str):
        return store.get(resume_id)

    @app.delete("/api/resumes/{resume_id}")
    async def delete_resume(resume_id: str, body: RevisionRequest):
        try:
            record = store.get(resume_id)
            if record.revision != body.expected_revision:
                raise Conflict("简历版本已变化，请刷新后再删除")
        except NotFound:
            pass
        for job_id in lifecycle.related_jobs(resume_id):
            job = jobs.get(job_id)
            if job['state'] in ('queued', 'running', 'waiting_input'):
                workflow.cancel(job_id)
        try:
            async with workflow.execution_lock:
                return lifecycle.delete_resume(resume_id, body.expected_revision)
        finally:
            workflow.wake()

    @app.get("/api/resumes/{resume_id}/history")
    def history(resume_id: str):
        return store.history(resume_id)

    @app.get('/api/resumes/{resume_id}/evidence')
    def resume_evidence(resume_id: str):
        record = store.get(resume_id)
        return {'evidence': jobs.get(record.ai.job_id).get('evidence', []) if record.ai else []}

    @app.put("/api/resumes/{resume_id}")
    def save_resume(resume_id: str, body: SaveResume):
        return store.save(resume_id, body.expected_revision, body.content)

    @app.post("/api/resumes/{resume_id}/confirm")
    def confirm_resume(resume_id: str, body: RevisionRequest):
        return store.confirm(resume_id, body.expected_revision)

    from app.exports import IncompleteResume, export_resume
    from app.processes import WorkerFailure
    from app.rendering import font_path, render_html

    @app.exception_handler(WorkerFailure)
    async def export_error_handler(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(IncompleteResume)
    async def incomplete_handler(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.post("/api/resumes/{resume_id}/exports")
    async def export_file(resume_id: str, body: ExportRequest):
        if workflow.execution_lock.locked():
            raise Conflict("当前有生成或导出任务正在执行，请完成或取消后再导出")
        try:
            async with workflow.execution_lock:
                path = await asyncio.to_thread(export_resume, store, data_dir, resume_id, body)
        finally:
            workflow.wake()
        media = "application/pdf" if body.format == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return FileResponse(path, media_type=media, filename=path.name)

    @app.post("/api/preview", response_class=HTMLResponse)
    def preview(body: ResumeContent, demo: bool = False):
        return render_html(body, demo=demo)

    @app.get("/api/font")
    def resume_font():
        path = font_path()
        if not path.is_file():
            return JSONResponse({"detail": "中文字体未配置"}, status_code=404)
        return FileResponse(path, media_type="font/otf")

    @app.exception_handler(providers.ProviderError)
    async def provider_error_handler(request, exc):
        detail = str(exc) or "模型服务调用失败"
        secret = getattr(app.state, "provider_key", None)
        if secret and secret in detail:
            detail = detail.replace(secret, "••••")
        return JSONResponse({"detail": detail, "category": getattr(exc, "category", "model_unavailable")}, status_code=422)

    @app.get("/api/model-settings")
    def model_settings():
        return {**(app.state.provider or {"configured": False, "resume_generation_verified": False}),
                "tool_calls_verified": registry.supports_tools(registry.current),
                "key_storage": app.state.key_storage}

    @app.get("/api/model-presets")
    def model_presets():
        return providers.PRESETS

    @app.post("/api/model-settings/test")
    async def test_model_settings(body: ProviderSetup):
        result = await providers.probe_provider(body)
        result["config_revision"] = registry.register(body)
        secret = body.api_key.get_secret_value()
        if body.remember:
            storage = key_store.save(data_dir, body.provider, body.model, body.base_url, secret)
            result["message"] += "。已保存到系统钥匙串，可随时清除。" if storage == "keyring" else "。本机没有可用的系统钥匙串，Key 只保留在本次服务内存中，重启后需要重新填写。"
        else:
            key_store.clear(data_dir)
            storage = "memory"
            result["message"] += "。Key 只保留在本次服务内存中，重启后需要重新填写。"
        result["key_storage"] = storage
        app.state.provider, app.state.provider_key, app.state.key_storage = result, secret, storage
        return result

    @app.post("/api/model-settings/forget")
    def forget_model_key():
        key_store.clear(data_dir)
        app.state.key_storage = "memory"
        if isinstance(app.state.provider, dict):
            app.state.provider["key_storage"] = "memory"
        return {"cleared": True, "key_storage": "memory"}

    @app.post("/api/model-settings/test-tools")
    async def test_model_tools():
        from app.supervisor import probe_context

        if workflow.execution_lock.locked():
            raise ValueError("当前有任务正在执行，请结束后再测试工具调用")
        revision = registry.current
        config = registry.get(revision)
        try:
            async with workflow.execution_lock:
                try:
                    async with asyncio.timeout(DEFAULT_POLICY.supervisor_ms / 1000):
                        result = await workflow.client.delegate(config, probe_context())
                except TimeoutError:
                    raise providers.ProviderError("工具测试超时，可能已计费；未启用智能修正策略") from None
        finally:
            workflow.wake()
        if result.value.action != "revise" or result.value.issue_indices != [0]:
            raise ValueError("工具测试未按合成任务执行，未启用智能修正策略")
        registry.verify_tools(revision)
        return {"verified": True, "config_revision": revision, "calls": 1, "usage": result.usage,
                "message": "合成工具调用测试通过；仅验证委派能力，不代表简历质量已验证"}

    @app.get("/api/generation-jobs")
    def list_generation_jobs():
        return jobs.list()

    @app.post("/api/generation-jobs", status_code=201)
    async def create_generation_job(body: GenerationInput):
        return workflow.submit(body)

    @app.get("/api/generation-jobs/{job_id}")
    def get_generation_job(job_id: str):
        job = public_job(job_id)
        return {**job, "service_warning": workflow.service_warning, "continuation": workflow.continuation(job)}

    def public_job(job_id):
        job = jobs.get(job_id)
        if job.get('deleted'):
            raise NotFound('任务已删除')
        return job

    @app.delete('/api/generation-jobs/{job_id}')
    async def delete_generation_job(job_id: str):
        job = jobs.get(job_id)
        if job['state'] in ('queued', 'running', 'waiting_input'):
            workflow.cancel(job_id)
        try:
            async with workflow.execution_lock:
                return lifecycle.delete_job(job_id)
        finally:
            workflow.wake()

    @app.post("/api/generation-jobs/{job_id}/answer")
    async def answer_generation_job(job_id: str, body: AnswerInput):
        public_job(job_id)
        return workflow.answer(job_id, body.model_dump())

    @app.post("/api/generation-jobs/{job_id}/cancel")
    async def cancel_generation_job(job_id: str):
        public_job(job_id)
        return workflow.cancel(job_id)

    @app.post("/api/generation-jobs/{job_id}/resume")
    async def resume_generation_job(job_id: str):
        public_job(job_id)
        return workflow.resume(job_id)

    @app.post("/api/generation-jobs/{job_id}/adopt")
    async def adopt_generation_job(job_id: str):
        public_job(job_id)
        return workflow.adopt(job_id)

    @app.post("/api/resumes/{resume_id}/review", status_code=201)
    async def recheck_resume(resume_id: str, body: ReviewRequest):
        return workflow.recheck(resume_id, body.expected_revision, body.request_id)

    @app.post("/api/resumes/{resume_id}/takeover")
    async def takeover_resume(resume_id: str, body: TakeoverRequest):
        if not body.acknowledged:
            raise ValueError("请明确确认已自行核对当前版本")
        return workflow.takeover(resume_id, body.expected_revision)

    @app.post("/api/chat/sessions", status_code=201)
    def create_chat():
        return chat.create()

    @app.get("/api/chat/sessions/{session_id}")
    def get_chat(session_id: str):
        return chat.get(session_id)

    @app.post("/api/chat/sessions/{session_id}/messages")
    async def post_chat(session_id: str, body: ChatMessageInput):
        return await chat.post(session_id, body)

    @app.post("/api/intake/parse")
    def parse_intake(body: ParseRequest):
        return parse_material(body.text, purpose=body.purpose)

    @app.post("/api/chat/uploads")
    async def upload_material(file: Annotated[UploadFile, File()]):
        data = await file.read()
        return chat.save_upload(upload_text.extract_upload(file.filename or "", data))

    @app.post("/api/agent/sessions", status_code=201)
    def create_agent_session(body: AgentTargetInput):
        return agent.create(body)

    @app.get("/api/agent/sessions/{session_id}")
    def get_agent_session(session_id: str):
        return agent.get(session_id)

    @app.post("/api/agent/sessions/{session_id}/messages")
    async def post_agent_message(session_id: str, body: AgentMessageInput):
        return await agent.post(session_id, body)

    @app.post("/api/agent/sessions/{session_id}/proposals/{proposal_id}/apply")
    def apply_agent_proposal(session_id: str, proposal_id: str):
        return agent.apply(session_id, proposal_id)

    @app.post("/api/agent/sessions/{session_id}/proposals/{proposal_id}/discard")
    def discard_agent_proposal(session_id: str, proposal_id: str):
        return agent.discard(session_id, proposal_id)

    @app.post("/api/resumes/{resume_id}/resolve-issue")
    async def resolve_resume_issue(resume_id: str, body: ResolveIssueInput):
        return workflow.resolve_issue(resume_id, body.model_dump())

    web = web_dir or resource_root() / "web" / "dist"
    if web.is_dir():
        app.mount("/", StaticFiles(directory=web, html=True), name="workbench")
    else:
        @app.get("/")
        def missing_frontend():
            return HTMLResponse("<h1>Match-Trajectory</h1><p>前端尚未构建，请执行 npm run build。</p>")
    return app
