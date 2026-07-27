"""
FastAPI application entrypoint.

Run with:
    uvicorn app.main:app --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import ai_bug, auth_router

# Create all tables on startup against PostgreSQL. Fine while the schema
# is small; once the project grows, swap this for Alembic migrations.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.app_name,
    description="AI-powered Bug Intelligence and QA Management Platform API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(ai_bug.router)


@app.get("/", tags=["Health"])
def health_check():
    return {"status": "ok", "service": settings.app_name}
