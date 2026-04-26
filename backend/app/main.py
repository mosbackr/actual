import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup: resume any running EDGAR jobs that were interrupted by restart
    from sqlalchemy import select, update
    from app.db.session import async_session
    from app.models.edgar_job import EdgarJob, EdgarJobStep

    async with async_session() as db:
        result = await db.execute(
            select(EdgarJob).where(EdgarJob.status == "running")
        )
        jobs = result.scalars().all()
        for job in jobs:
            # Reset any steps stuck in 'running' state
            await db.execute(
                update(EdgarJobStep)
                .where(EdgarJobStep.job_id == job.id)
                .where(EdgarJobStep.status == "running")
                .values(status="pending")
            )
            await db.commit()

            # Re-launch worker in background
            from app.services.edgar_worker import run_edgar_worker
            asyncio.create_task(run_edgar_worker(str(job.id)))
            logger.info(f"Resumed EDGAR worker for job {job.id}")

    yield
from app.api.users import router as users_router
from app.api.admin import router as admin_router
from app.api.startups import router as startups_router
from app.api.industries import router as industries_router
from app.api.experts import router as experts_router
from app.api.auth_exchange import router as auth_exchange_router
from app.api.admin_templates import router as admin_templates_router
from app.api.admin_dimensions import router as admin_dimensions_router
from app.api.admin_assignments import router as admin_assignments_router
from app.api.expert_assignments import router as expert_assignments_router
from app.api.admin_auth import router as admin_auth_router
from app.api.admin_scout import router as admin_scout_router
from app.api.admin_enrichment import router as admin_enrichment_router
from app.api.public_auth import router as public_auth_router
from app.api.reviews import router as reviews_router
from app.api.insights import router as insights_router
from app.api.admin_batch import router as admin_batch_router
from app.api.admin_edgar import router as admin_edgar_router
from app.api.analyze import router as analyze_router
from app.api.analyst import router as analyst_router
from app.api.billing import router as billing_router
from app.api.notifications import router as notifications_router
from app.api.memo import router as memo_router
from app.api.tool_calls import router as tool_calls_router
from app.api.watchlist import router as watchlist_router
from app.api.admin_investors import router as admin_investors_router
from app.api.pitch_intelligence import router as pitch_intelligence_router
from app.api.feedback import router as feedback_router
from app.api.admin_feedback import router as admin_feedback_router
from app.api.admin_investor_rankings import router as admin_investor_rankings_router
from app.api.faq import router as faq_router
from app.api.admin_marketing import router as admin_marketing_router
from app.api.investor_rankings_public import router as investor_rankings_public_router
from app.api.unsubscribe import router as unsubscribe_router
from app.api.zoom import router as zoom_router

app = FastAPI(title="Acutal API", version="0.1.0", lifespan=lifespan)

MAX_REQUEST_BODY_SIZE = 52_428_800  # 50 MB


class LimitRequestBodyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Request body too large. Max size is {MAX_REQUEST_BODY_SIZE} bytes."},
            )
        return await call_next(request)


app.add_middleware(LimitRequestBodyMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users_router)
app.include_router(admin_router)
app.include_router(startups_router)
app.include_router(industries_router)
app.include_router(experts_router)
app.include_router(auth_exchange_router)
app.include_router(admin_templates_router)
app.include_router(admin_dimensions_router)
app.include_router(admin_assignments_router)
app.include_router(expert_assignments_router)
app.include_router(admin_auth_router)
app.include_router(admin_scout_router)
app.include_router(admin_enrichment_router)
app.include_router(public_auth_router)
app.include_router(reviews_router)
app.include_router(insights_router)
app.include_router(admin_batch_router)
app.include_router(admin_edgar_router)
app.include_router(analyze_router)
app.include_router(analyst_router)
app.include_router(billing_router)
app.include_router(notifications_router)
app.include_router(memo_router)
app.include_router(tool_calls_router)
app.include_router(watchlist_router)
app.include_router(admin_investors_router)
app.include_router(pitch_intelligence_router)
app.include_router(feedback_router)
app.include_router(admin_feedback_router)
app.include_router(admin_investor_rankings_router)
app.include_router(faq_router)
app.include_router(admin_marketing_router)
app.include_router(investor_rankings_public_router)
app.include_router(unsubscribe_router)
app.include_router(zoom_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
