from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.users import router as users_router
from app.api.admin import router as admin_router
from app.api.startups import router as startups_router
from app.api.industries import router as industries_router
from app.api.experts import router as experts_router
from app.api.auth_exchange import router as auth_exchange_router
from app.api.admin_templates import router as admin_templates_router

app = FastAPI(title="Acutal API", version="0.1.0")

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


@app.get("/api/health")
async def health():
    return {"status": "ok"}
