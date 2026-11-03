import asyncio
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.demo import demo_content
from app.generation_models import AnswerInput, GenerationInput, ResolveIssueInput
from app.jobs import JobStore
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
from app.store import Conflict, NotFound, ResumeStore
from app.workflow import Workflow


class ReviewRequest(RevisionRequest):
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,80}$")


class TakeoverRequest(RevisionRequest):
    acknowledged: bool


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def create_app(data_dir: Path, *, web_dir: Path | None = None, model_client=None) -> FastAPI:
    store = ResumeStore(data_dir / "resumes.sqlite3")
    jobs = JobStore(store)
    registry = ModelRegistry()
    workflow = Workflow(store, jobs, registry, model_client or ModelClient())

    @asynccontextmanager
    async def lifespan(app):
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
    app.state.workflow = workflow
    session = secrets.token_urlsafe(32)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])

    @app.middleware("http")
    async def local_session(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
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
        return {"status": "ok", "milestone": "m1", "ai_generation": True, "worker_warning": workflow.service_warning}

    @app.get("/api/session")
    def initialize_session():
        response = JSONResponse({"status": "ready", "milestone": "m1"})
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

    @app.get("/api/resumes/{resume_id}/history")
    def history(resume_id: str):
        return store.history(resume_id)

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

    from app import providers

    @app.exception_handler(providers.ProviderError)
    async def provider_error_handler(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.get("/api/model-settings")
    def model_settings():
        return app.state.provider or {"configured": False, "resume_generation_verified": False}

    @app.get("/api/model-presets")
    def model_presets():
        return providers.PRESETS

    @app.post("/api/model-settings/test")
    async def test_model_settings(body: providers.ProviderConfig):
        result = await providers.probe_provider(body)
        result["config_revision"] = registry.register(body)
        app.state.provider, app.state.provider_key = result, body.api_key
        return result

    @app.post("/api/model-settings/test-tools")
    async def test_model_tools():
        from app.supervisor import probe_context

        if workflow.execution_lock.locked():
            raise ValueError("当前有任务正在执行，请结束后再测试工具调用")
        revision = registry.current
        config = registry.get(revision)
        async with workflow.execution_lock:
            try:
                async with asyncio.timeout(20):
                    result = await workflow.client.delegate(config, probe_context())
            except TimeoutError:
                raise providers.ProviderError("工具测试超时，可能已计费；未启用智能修正策略") from None
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
        job = jobs.get(job_id)
        return {**job, "service_warning": workflow.service_warning, "continuation": workflow.continuation(job)}

    @app.post("/api/generation-jobs/{job_id}/answer")
    async def answer_generation_job(job_id: str, body: AnswerInput):
        return workflow.answer(job_id, body.model_dump())

    @app.post("/api/generation-jobs/{job_id}/cancel")
    async def cancel_generation_job(job_id: str):
        return workflow.cancel(job_id)

    @app.post("/api/generation-jobs/{job_id}/resume")
    async def resume_generation_job(job_id: str):
        return workflow.resume(job_id)

    @app.post("/api/generation-jobs/{job_id}/adopt")
    async def adopt_generation_job(job_id: str):
        return workflow.adopt(job_id)

    @app.post("/api/resumes/{resume_id}/review", status_code=201)
    async def recheck_resume(resume_id: str, body: ReviewRequest):
        return workflow.recheck(resume_id, body.expected_revision, body.request_id)

    @app.post("/api/resumes/{resume_id}/takeover")
    async def takeover_resume(resume_id: str, body: TakeoverRequest):
        if not body.acknowledged:
            raise ValueError("请明确确认已自行核对当前版本")
        return workflow.takeover(resume_id, body.expected_revision)

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
