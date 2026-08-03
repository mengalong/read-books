from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Book(TimestampMixin, Base):
    __tablename__ = "books"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200), index=True)
    author: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    cover_color: Mapped[str] = mapped_column(String(20), default="#2F6B5F")
    language: Mapped[str] = mapped_column(String(30), default="中文")
    reading_status: Mapped[str] = mapped_column(String(30), default="finished", index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    pre_generation_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    pre_generation_status: Mapped[str] = mapped_column(String(20), default="disabled", index=True)
    pre_generation_error: Mapped[str | None] = mapped_column(Text)
    pre_generation_quiz_id: Mapped[str | None] = mapped_column(String(36))

    pdfs: Mapped[list[PdfDocument]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[ContentChunk]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    quizzes: Mapped[list[Quiz]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    generation_tasks: Mapped[list[QuizGenerationTask]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    review_tasks: Mapped[list[ReviewTask]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )


class PdfDocument(TimestampMixin, Base):
    __tablename__ = "pdf_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(Text)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    parse_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text)

    book: Mapped[Book] = relationship(back_populates="pdfs")
    chunks: Mapped[list[ContentChunk]] = relationship(
        back_populates="pdf", cascade="all, delete-orphan"
    )


class ContentChunk(TimestampMixin, Base):
    __tablename__ = "content_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    pdf_id: Mapped[str] = mapped_column(
        ForeignKey("pdf_documents.id", ondelete="CASCADE"), index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer)

    book: Mapped[Book] = relationship(back_populates="chunks")
    pdf: Mapped[PdfDocument] = relationship(back_populates="chunks")


class Quiz(TimestampMixin, Base):
    __tablename__ = "quizzes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=15)
    status: Mapped[str] = mapped_column(String(20), default="ready", index=True)
    source_mode: Mapped[str] = mapped_column(String(30), default="pdf", index=True)
    total_score: Mapped[float | None] = mapped_column(Float)
    max_score: Mapped[float] = mapped_column(Float, default=100)
    elapsed_seconds: Mapped[int | None] = mapped_column(Integer)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_review_date: Mapped[date | None] = mapped_column(Date)
    generation_task_id: Mapped[str | None] = mapped_column(String(36), index=True)

    book: Mapped[Book] = relationship(back_populates="quizzes")
    questions: Mapped[list[Question]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan", order_by="Question.position"
    )
    answers: Mapped[list[Answer]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan"
    )
    review_tasks: Mapped[list[ReviewTask]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan"
    )


class Question(TimestampMixin, Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    question_type: Mapped[str] = mapped_column(String(20))
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    correct_answers: Mapped[list[str]] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text)
    knowledge_point: Mapped[str] = mapped_column(String(120))
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    estimated_seconds: Mapped[int] = mapped_column(Integer)
    reference_answer: Mapped[str | None] = mapped_column(Text)
    grading_rubric: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    source_chunk_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    max_score: Mapped[float] = mapped_column(Float)

    quiz: Mapped[Quiz] = relationship(back_populates="questions")
    answer: Mapped[Answer | None] = relationship(
        back_populates="question", cascade="all, delete-orphan", uselist=False
    )
    review_answers: Mapped[list[ReviewAnswer]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )


class Answer(TimestampMixin, Base):
    __tablename__ = "answers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), unique=True, index=True
    )
    selected_answers: Mapped[list[str]] = mapped_column(JSON, default=list)
    text_answer: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float, default=0)
    max_score: Mapped[float] = mapped_column(Float)
    is_correct: Mapped[bool] = mapped_column(default=False)
    feedback: Mapped[str] = mapped_column(Text, default="")
    matched_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_points: Mapped[list[str]] = mapped_column(JSON, default=list)

    quiz: Mapped[Quiz] = relationship(back_populates="answers")
    question: Mapped[Question] = relationship(back_populates="answer")


class QuizGenerationTask(TimestampMixin, Base):
    __tablename__ = "quiz_generation_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    task_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    source_mode: Mapped[str] = mapped_column(String(30), default="pdf", index=True)
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    completed_questions: Mapped[int] = mapped_column(Integer, default=0)
    current_question_position: Mapped[int | None] = mapped_column(Integer)
    current_phase: Mapped[str] = mapped_column(String(120), default="等待开始")
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=15)
    single_count: Mapped[int] = mapped_column(Integer, default=0)
    multiple_count: Mapped[int] = mapped_column(Integer, default=0)
    short_count: Mapped[int] = mapped_column(Integer, default=0)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    quiz_id: Mapped[str | None] = mapped_column(String(36), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)

    book: Mapped[Book] = relationship(back_populates="generation_tasks")


class ReviewTask(TimestampMixin, Base):
    __tablename__ = "review_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="in_progress", index=True)
    total_score: Mapped[float | None] = mapped_column(Float)
    max_score: Mapped[float] = mapped_column(Float, default=100)
    elapsed_seconds: Mapped[int | None] = mapped_column(Integer)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_review_date: Mapped[date | None] = mapped_column(Date)

    book: Mapped[Book] = relationship(back_populates="review_tasks")
    quiz: Mapped[Quiz] = relationship(back_populates="review_tasks")
    answers: Mapped[list[ReviewAnswer]] = relationship(
        back_populates="review_task", cascade="all, delete-orphan"
    )


class ReviewAnswer(TimestampMixin, Base):
    __tablename__ = "review_answers"
    __table_args__ = (UniqueConstraint("review_task_id", "question_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    review_task_id: Mapped[str] = mapped_column(
        ForeignKey("review_tasks.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    selected_answers: Mapped[list[str]] = mapped_column(JSON, default=list)
    text_answer: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float, default=0)
    max_score: Mapped[float] = mapped_column(Float)
    is_correct: Mapped[bool] = mapped_column(default=False)
    feedback: Mapped[str] = mapped_column(Text, default="")
    matched_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_points: Mapped[list[str]] = mapped_column(JSON, default=list)

    review_task: Mapped[ReviewTask] = relationship(back_populates="answers")
    question: Mapped[Question] = relationship(back_populates="review_answers")


class ModelConfiguration(TimestampMixin, Base):
    __tablename__ = "model_configurations"

    id: Mapped[str] = mapped_column(String(20), primary_key=True, default="default")
    provider_mode: Mapped[str] = mapped_column(String(30), default="mock")
    base_url: Mapped[str] = mapped_column(Text, default="")
    api_key: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(200), default="")
    timeout_ms: Mapped[int] = mapped_column(Integer, default=180_000)
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    last_test_status: Mapped[str | None] = mapped_column(String(20))
    last_test_message: Mapped[str | None] = mapped_column(Text)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_latency_ms: Mapped[int | None] = mapped_column(Integer)


class PromptTemplate(TimestampMixin, Base):
    __tablename__ = "prompt_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    prompt_type: Mapped[str] = mapped_column(String(30), index=True)
    system_prompt: Mapped[str] = mapped_column(Text)
    user_prompt: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class ModelUsageRecord(Base):
    __tablename__ = "model_usage_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    task_type: Mapped[str] = mapped_column(String(40), index=True)
    task_label: Mapped[str] = mapped_column(String(240))
    phase: Mapped[str] = mapped_column(String(50), index=True)
    call_number: Mapped[int] = mapped_column(Integer, default=1)
    model_name: Mapped[str] = mapped_column(String(200))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    book_id: Mapped[str | None] = mapped_column(String(36), index=True)
    quiz_id: Mapped[str | None] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
