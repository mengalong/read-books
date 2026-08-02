import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import PdfDocument
from app.routers.books import router as books_router
from app.routers.quizzes import router as quizzes_router
from app.services.demo_data import seed_demo_data
from app.services.pdf_parser import parse_pdf_document

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:
        with SessionLocal() as db:
            seed_demo_data(db)
            pending_pdf_ids = list(
                db.scalars(
                    select(PdfDocument.id).where(
                        PdfDocument.parse_status.in_(["pending", "processing"])
                    )
                ).all()
            )
        for pdf_id in pending_pdf_ids:
            threading.Thread(target=parse_pdf_document, args=(pdf_id,), daemon=True).start()
    yield


app = FastAPI(
    title=f"{settings.app_name} API",
    version="0.1.0",
    description="基于 PDF 原文生成读书复习测试。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(books_router, prefix="/api")
app.include_router(quizzes_router, prefix="/api")


@app.get("/api/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
        "mock_mode": settings.mock_mode,
    }
