"""GramSathi API - application factory.

Run:  uvicorn app.asgi:app --reload      (from the backend/ folder)
"""
from __future__ import annotations

from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import ai as ai_mod
from . import db as dbm
from .config import Settings, load_settings
from .http import error_response
from .middleware import SecurityHeadersMiddleware
from .routes import admin, assistant, auth, documents, news, services, rozgar
from .seed import seed

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"


async def health(request):
    return JSONResponse({"status": "ok", "ai": "claude" if request.app.state.ai.enabled else "rules"})


async def readiness(request):
    """Verify the database can be reached before a deployment receives traffic."""
    try:
        conn = dbm.connect(request.app.state.settings.database_path)
        conn.execute("SELECT 1").fetchone()
        conn.close()
        return JSONResponse({"status": "ready", "database": "ok"})
    except Exception:
        return JSONResponse({"status": "not_ready"}, status_code=503)


def _routes() -> list:
    r = lambda path, fn, methods: Route(path, fn, methods=methods)  # noqa: E731
    return [
        r("/api/health", health, ["GET"]),
        r("/api/ready", readiness, ["GET"]),
        # auth
        r("/api/auth/register", auth.register, ["POST"]),
        r("/api/auth/login", auth.login, ["POST"]),
        r("/api/auth/me", auth.me, ["GET"]),
        r("/api/auth/me", auth.update_me, ["PATCH"]),
        # citizen self-service
        r("/api/me/ration", services.my_ration, ["GET"]),
        r("/api/me/anganwadi", services.my_anganwadi, ["GET"]),
        r("/api/me/water", services.my_water, ["GET"]),
        r("/api/me/property", services.my_property, ["GET"]),
        r("/api/me/water/bills/{id:int}/pay", services.pay_water_bill, ["POST"]),
        r("/api/me/property/{id:int}/pay", services.pay_property, ["POST"]),
        # documents
        r("/api/documents", documents.create, ["POST"]),
        r("/api/documents", documents.list_documents, ["GET"]),
        r("/api/documents/{id:int}", documents.get_document, ["GET"]),
        r("/api/documents/{id:int}/review", documents.review, ["POST"]),
        r("/api/documents/{id:int}/pdf", documents.download_pdf, ["GET"]),
        # news
        r("/api/news", news.list_news, ["GET"]),
        r("/api/news", news.create_news, ["POST"]),
        r("/api/news/{id:int}", news.update_news, ["PUT"]),
        r("/api/news/{id:int}", news.delete_news, ["DELETE"]),
        r("/api/ai/news-draft", news.draft, ["POST"]),
        # anganwadi
        r("/api/anganwadi", services.list_centers, ["GET"]),
        # AI assistant
        r("/api/ai/chat", assistant.chat, ["POST"]),
        r("/api/ai/chat/history", assistant.history, ["GET"]),
        # Rozgar employment marketplace
        r("/api/ai/rozgar/profile-draft", rozgar.profile_draft, ["POST"]),
        r("/api/ai/rozgar/job-draft", rozgar.job_draft, ["POST"]),
        r("/api/ai/rozgar/cover-draft", rozgar.cover_draft, ["POST"]),
        r("/api/rozgar/jobs/{id:int}/applicant-summary", rozgar.applicant_summary, ["GET"]),
        r("/api/rozgar/profile", rozgar.get_profile, ["GET"]),
        r("/api/rozgar/profile", rozgar.save_profile, ["PUT"]),
        r("/api/rozgar/jobs", rozgar.list_jobs, ["GET"]),
        r("/api/rozgar/jobs", rozgar.create_job, ["POST"]),
        r("/api/rozgar/jobs/mine", rozgar.employer_jobs, ["GET"]),
        r("/api/rozgar/jobs/{id:int}/apply", rozgar.apply, ["POST"]),
        r("/api/rozgar/applications/mine", rozgar.my_applications, ["GET"]),
        r("/api/rozgar/jobs/{id:int}/applicants", rozgar.applicants, ["GET"]),
        r("/api/rozgar/applications/{id:int}", rozgar.update_application, ["PATCH"]),
        r("/api/admin/rozgar/moderation", rozgar.moderation_queue, ["GET"]),
        r("/api/admin/rozgar/jobs/{id:int}/moderate", rozgar.moderate, ["POST"]),
        # admin
        r("/api/admin/dashboard", admin.dashboard, ["GET"]),
        r("/api/admin/ai/insights", admin.insights, ["POST"]),
        r("/api/admin/audit", admin.audit_log, ["GET"]),
        r("/api/admin/users", admin.list_users, ["GET"]),
        r("/api/admin/users/{id:int}", admin.update_user, ["PATCH"]),
        r("/api/admin/ration", services.admin_ration, ["GET"]),
        r("/api/admin/ration", services.create_ration, ["POST"]),
        r("/api/admin/ration/{id:int}", services.update_ration, ["PUT"]),
        r("/api/admin/anganwadi", services.create_center, ["POST"]),
        r("/api/admin/anganwadi/{id:int}", services.update_center, ["PUT"]),
        r("/api/admin/anganwadi/beneficiaries", services.admin_beneficiaries, ["GET"]),
        r("/api/admin/anganwadi/beneficiaries", services.create_beneficiary, ["POST"]),
        r("/api/admin/water", services.admin_water, ["GET"]),
        r("/api/admin/water/bills", services.upsert_water_bill, ["POST"]),
        r("/api/admin/property", services.admin_property, ["GET"]),
        r("/api/admin/property", services.create_property, ["POST"]),
    ]


def create_app(settings: Settings | None = None, ai_client: ai_mod.AIClient | None = None) -> Starlette:
    settings = settings or load_settings()

    async def not_found(request, exc):
        return error_response(404, "Not found")

    async def server_error(request, exc):
        return error_response(500, "Internal server error")

    async def index(request):
        return FileResponse(WEB_DIR / "index.html")

    routes = _routes()
    routes.append(Route("/", index))
    if WEB_DIR.exists():
        routes.append(Mount("/static", StaticFiles(directory=WEB_DIR), name="static"))

    app = Starlette(
        routes=routes,
        middleware=[
            Middleware(SecurityHeadersMiddleware),
            Middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Request-ID"], allow_credentials=False),
        ],
        exception_handlers={404: not_found, 500: server_error},
    )
    app.state.settings = settings
    app.state.ai = ai_client or ai_mod.AIClient(settings)
    dbm.init_schema(settings.database_path)
    if settings.seed_demo_data:
        seed(settings.database_path)
    return app

