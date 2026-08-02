from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text
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

    pdfs: Mapped[list[PdfDocument]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[ContentChunk]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    quizzes: Mapped[list[Quiz]] = relationship(
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
    total_score: Mapped[float | None] = mapped_column(Float)
    max_score: Mapped[float] = mapped_column(Float, default=100)
    elapsed_seconds: Mapped[int | None] = mapped_column(Integer)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_review_date: Mapped[date | None] = mapped_column(Date)

    book: Mapped[Book] = relationship(back_populates="quizzes")
    questions: Mapped[list[Question]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan", order_by="Question.position"
    )
    answers: Mapped[list[Answer]] = relationship(
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


class ModelConfiguration(TimestampMixin, Base):
    __tablename__ = "model_configurations"

    id: Mapped[str] = mapped_column(String(20), primary_key=True, default="default")
    provider_mode: Mapped[str] = mapped_column(String(30), default="mock")
    base_url: Mapped[str] = mapped_column(Text, default="")
    api_key: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(200), default="")
    timeout_ms: Mapped[int] = mapped_column(Integer, default=60_000)
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    last_test_status: Mapped[str | None] = mapped_column(String(20))
    last_test_message: Mapped[str | None] = mapped_column(Text)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_latency_ms: Mapped[int | None] = mapped_column(Integer)
