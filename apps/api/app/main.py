import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import PdfDocument, ResourceMaterial
from app.routers.auth import router as auth_router
from app.routers.books import admin_router as admin_books_router
from app.routers.books import router as books_router
from app.routers.quizzes import router as quizzes_router
from app.routers.question_bank import router as question_bank_router
from app.routers.materials import router as materials_router
from app.routers.site import router as site_router
from app.routers.settings import router as settings_router
from app.routers.wechat import router as wechat_router
from app.routers.exams import admin_router as admin_exams_router
from app.routers.exams import public_router as public_exams_router
from app.routers.exams import router as exams_router
from app.services.demo_data import seed_demo_data
from app.services.auth import ensure_initial_admin
from app.services.pdf_parser import parse_pdf_document
from app.services.quiz_generation import recover_generation_tasks, run_generation_task
from app.services.material_parser import parse_material_document, recover_material_tasks
from app.services.material_understanding import refresh_material_understanding
from app.services.exam_sharing import recover_exam_grading_tasks, launch_exam_grading
from app.services.quiz_quality_review import recover_quality_review_tasks, run_quiz_quality_review

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:
        with SessionLocal() as db:
            seed_demo_data(db)
            ensure_initial_admin(db, settings)
            pending_pdf_ids = list(
                db.scalars(
                    select(PdfDocument.id).where(
                        PdfDocument.parse_status.in_(["pending", "processing"])
                    )
                ).all()
            )
    else:
        with SessionLocal() as db:
            ensure_initial_admin(db, settings)
            pending_pdf_ids = list(
                db.scalars(
                    select(PdfDocument.id).where(
                        PdfDocument.parse_status.in_(["pending", "processing"])
                    )
                ).all()
            )
    for pdf_id in pending_pdf_ids:
        threading.Thread(target=parse_pdf_document, args=(pdf_id,), daemon=True).start()
    for material_id in recover_material_tasks():
        threading.Thread(target=parse_material_document, args=(material_id,), daemon=True).start()
    with SessionLocal() as db:
        pending_understanding_book_ids = list(
            dict.fromkeys(
                row
                for row in db.scalars(select(ResourceMaterial.book_id)).all()
            )
        )
    for understanding_book_id in pending_understanding_book_ids:
        threading.Thread(
            target=refresh_material_understanding, args=(understanding_book_id,), daemon=True
        ).start()
    with SessionLocal() as db:
        pending_generation_task_ids = recover_generation_tasks(db)
    for task_id in pending_generation_task_ids:
        threading.Thread(target=run_generation_task, args=(task_id,), daemon=True).start()
    with SessionLocal() as db:
        pending_exam_attempt_ids = recover_exam_grading_tasks(db)
    for attempt_id in pending_exam_attempt_ids:
        launch_exam_grading(attempt_id)
    with SessionLocal() as db:
        pending_quality_review_tasks = recover_quality_review_tasks(db)
    for quiz_id, task_id, question_id in pending_quality_review_tasks:
        threading.Thread(
            target=run_quiz_quality_review,
            args=(quiz_id, task_id, question_id),
            daemon=True,
        ).start()
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
app.include_router(materials_router, prefix="/api")
app.include_router(admin_books_router, prefix="/api")
app.include_router(quizzes_router, prefix="/api")
app.include_router(question_bank_router, prefix="/api")
app.include_router(site_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(wechat_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(exams_router, prefix="/api")
app.include_router(admin_exams_router, prefix="/api")
app.include_router(public_exams_router, prefix="/api")


@app.get("/api/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
        "mock_mode": settings.mock_mode,
    }
