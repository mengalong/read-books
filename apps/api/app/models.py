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
    LargeBinary,
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


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="user", index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    workspace_memberships: Mapped[list[WorkspaceMember]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    access_visits: Mapped[list[UserAccessVisit]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    created_workspaces: Mapped[list[Workspace]] = relationship(
        back_populates="created_by_user", foreign_keys="Workspace.created_by_user_id"
    )
    created_books: Mapped[list[Book]] = relationship(
        back_populates="created_by_user", foreign_keys="Book.created_by_user_id"
    )
    created_generation_tasks: Mapped[list[QuizGenerationTask]] = relationship(
        back_populates="created_by_user", foreign_keys="QuizGenerationTask.created_by_user_id"
    )
    created_materials: Mapped[list[ResourceMaterial]] = relationship(
        back_populates="created_by_user", foreign_keys="ResourceMaterial.created_by_user_id"
    )
    usage_records: Mapped[list[ModelUsageRecord]] = relationship(
        back_populates="user", foreign_keys="ModelUsageRecord.user_id"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        back_populates="actor_user", foreign_keys="AuditLog.actor_user_id"
    )
    created_exam_shares: Mapped[list[ExamShare]] = relationship(
        back_populates="owner_user", foreign_keys="ExamShare.owner_user_id"
    )
    exam_attempts: Mapped[list[ExamAttempt]] = relationship(
        back_populates="participant_user", foreign_keys="ExamAttempt.participant_user_id"
    )


class Workspace(TimestampMixin, Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    workspace_type: Mapped[str] = mapped_column(String(20), default="personal")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )

    created_by_user: Mapped[User] = relationship(
        back_populates="created_workspaces", foreign_keys=[created_by_user_id]
    )
    members: Mapped[list[WorkspaceMember]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    books: Mapped[list[Book]] = relationship(back_populates="workspace")
    usage_records: Mapped[list[ModelUsageRecord]] = relationship(back_populates="workspace")
    access_visits: Mapped[list[UserAccessVisit]] = relationship(back_populates="workspace")
    exam_shares: Mapped[list[ExamShare]] = relationship(back_populates="workspace")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    workspace: Mapped[Workspace] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="workspace_memberships")


class UserSession(TimestampMixin, Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    ip_address: Mapped[str | None] = mapped_column(String(80))

    user: Mapped[User] = relationship(back_populates="sessions")
    access_visits: Mapped[list[UserAccessVisit]] = relationship(back_populates="session")


class UserAccessVisit(Base):
    __tablename__ = "user_access_visits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="SET NULL"), index=True
    )
    entry_type: Mapped[str] = mapped_column(String(20), default="resume", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    end_reason: Mapped[str | None] = mapped_column(String(20), index=True)

    user: Mapped[User] = relationship(back_populates="access_visits")
    workspace: Mapped[Workspace] = relationship(back_populates="access_visits")
    session: Mapped[UserSession | None] = relationship(back_populates="access_visits")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_type: Mapped[str] = mapped_column(String(50), index=True)
    target_id: Mapped[str | None] = mapped_column(String(36), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    actor_user: Mapped[User | None] = relationship(
        back_populates="audit_logs", foreign_keys=[actor_user_id]
    )


class Book(TimestampMixin, Base):
    __tablename__ = "books"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    resource_type: Mapped[str] = mapped_column(String(20), default="book", index=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    author: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    cover_color: Mapped[str] = mapped_column(String(20), default="#2F6B5F")
    language: Mapped[str] = mapped_column(String(30), default="中文")
    reading_status: Mapped[str] = mapped_column(String(30), default="finished", index=True)
    shelf_status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    model_knowledge_supported: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    model_knowledge_message: Mapped[str | None] = mapped_column(Text)
    model_knowledge_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
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
    materials: Mapped[list[ResourceMaterial]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    material_segments: Mapped[list[MaterialSegment]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    plot_events: Mapped[list["PlotEvent"]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    quote_entries: Mapped[list[QuoteEntry]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    material_understandings: Mapped[list["MaterialUnderstanding"]] = relationship(
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
    exam_shares: Mapped[list[ExamShare]] = relationship(back_populates="book")
    workspace: Mapped[Workspace | None] = relationship(back_populates="books")
    created_by_user: Mapped[User | None] = relationship(
        back_populates="created_books", foreign_keys=[created_by_user_id]
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
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String(120))

    book: Mapped[Book] = relationship(back_populates="chunks")
    pdf: Mapped[PdfDocument] = relationship(back_populates="chunks")


class ResourceMaterial(TimestampMixin, Base):
    __tablename__ = "resource_materials"
    __table_args__ = (
        UniqueConstraint("book_id", "file_hash", name="uq_resource_material_book_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    book_id: Mapped[str] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    material_type: Mapped[str] = mapped_column(String(30), index=True)
    file_format: Mapped[str] = mapped_column(String(20), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(Text)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    season_number: Mapped[int | None] = mapped_column(Integer)
    episode_label: Mapped[str | None] = mapped_column(String(80))
    version_label: Mapped[str | None] = mapped_column(String(120))
    parse_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    segment_count: Mapped[int] = mapped_column(Integer, default=0)
    quote_count: Mapped[int] = mapped_column(Integer, default=0)
    source_registry: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    book: Mapped[Book] = relationship(back_populates="materials")
    created_by_user: Mapped[User | None] = relationship(
        back_populates="created_materials", foreign_keys=[created_by_user_id]
    )
    segments: Mapped[list[MaterialSegment]] = relationship(
        back_populates="material", cascade="all, delete-orphan"
    )
    quotes: Mapped[list[QuoteEntry]] = relationship(
        back_populates="material", cascade="all, delete-orphan"
    )
    plot_events: Mapped[list["PlotEvent"]] = relationship(
        back_populates="material", cascade="all, delete-orphan"
    )


class MaterialSegment(TimestampMixin, Base):
    __tablename__ = "material_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    book_id: Mapped[str] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    material_id: Mapped[str] = mapped_column(
        ForeignKey("resource_materials.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    page_number: Mapped[int | None] = mapped_column(Integer, index=True)
    season_number: Mapped[int | None] = mapped_column(Integer, index=True)
    episode_number: Mapped[int | None] = mapped_column(Integer, index=True)
    start_ms: Mapped[int | None] = mapped_column(Integer)
    end_ms: Mapped[int | None] = mapped_column(Integer)
    scene_label: Mapped[str | None] = mapped_column(String(200))
    speaker: Mapped[str | None] = mapped_column(String(120), index=True)
    speaker_origin: Mapped[str] = mapped_column(String(20), default="unknown", index=True)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String(120))

    book: Mapped[Book] = relationship(back_populates="material_segments")
    material: Mapped[ResourceMaterial] = relationship(back_populates="segments")


class PlotEvent(TimestampMixin, Base):
    __tablename__ = "plot_events"
    __table_args__ = (
        UniqueConstraint("material_id", "event_id", name="uq_plot_event_material_event"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    material_id: Mapped[str] = mapped_column(
        ForeignKey("resource_materials.id", ondelete="CASCADE"), index=True
    )
    event_id: Mapped[str] = mapped_column(String(160), index=True)
    level: Mapped[str] = mapped_column(String(20), default="event", index=True)
    season_number: Mapped[int | None] = mapped_column(Integer, index=True)
    episode_number: Mapped[int | None] = mapped_column(Integer, index=True)
    sequence: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(240), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    cause: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(Text, default="")
    future_impact: Mapped[str] = mapped_column(Text, default="")
    characters: Mapped[list[str]] = mapped_column(JSON, default=list)
    relationship_changes: Mapped[list[Any]] = mapped_column(JSON, default=list)
    conflict_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    theme_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    importance: Mapped[str] = mapped_column(String(20), default="medium")
    source_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[str] = mapped_column(String(20), default="unknown", index=True)
    question_usable: Mapped[str] = mapped_column(String(20), default="needs_review", index=True)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    enabled_for_generation: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    book: Mapped[Book] = relationship(back_populates="plot_events")
    material: Mapped[ResourceMaterial] = relationship(back_populates="plot_events")


class QuoteEntry(TimestampMixin, Base):
    __tablename__ = "quote_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    book_id: Mapped[str] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    material_id: Mapped[str] = mapped_column(
        ForeignKey("resource_materials.id", ondelete="CASCADE"), index=True
    )
    source_segment_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    quote_text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    speaker: Mapped[str | None] = mapped_column(String(120), index=True)
    speaker_origin: Mapped[str] = mapped_column(String(20), default="unknown", index=True)
    context: Mapped[str | None] = mapped_column(Text)
    season_number: Mapped[int | None] = mapped_column(Integer, index=True)
    episode_number: Mapped[int | None] = mapped_column(Integer, index=True)
    start_ms: Mapped[int | None] = mapped_column(Integer)
    end_ms: Mapped[int | None] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer, index=True)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    enabled_for_generation: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String(120))

    book: Mapped[Book] = relationship(back_populates="quote_entries")
    material: Mapped[ResourceMaterial] = relationship(back_populates="quotes")


class MaterialUnderstanding(TimestampMixin, Base):
    __tablename__ = "material_understandings"
    __table_args__ = (
        UniqueConstraint(
            "book_id", "scope_type", "scope_ref", name="uq_material_understanding_scope"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    scope_type: Mapped[str] = mapped_column(String(20), index=True)
    scope_ref: Mapped[str] = mapped_column(String(60), default="", index=True)
    summary_text: Mapped[str] = mapped_column(Text, default="")
    key_entities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_segment_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_chunk_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    content_signature: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text)

    book: Mapped[Book] = relationship(back_populates="material_understandings")


class Quiz(TimestampMixin, Base):
    __tablename__ = "quizzes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=15)
    status: Mapped[str] = mapped_column(String(20), default="ready", index=True)
    source_mode: Mapped[str] = mapped_column(String(30), default="pdf", index=True)
    generation_theme: Mapped[str] = mapped_column(String(30), default="general", index=True)
    theme_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    total_score: Mapped[float | None] = mapped_column(Float)
    max_score: Mapped[float] = mapped_column(Float, default=100)
    elapsed_seconds: Mapped[int | None] = mapped_column(Integer)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_review_date: Mapped[date | None] = mapped_column(Date)
    generation_task_id: Mapped[str | None] = mapped_column(String(36), index=True)
    quality_review_status: Mapped[str] = mapped_column(
        String(20), default="not_started", index=True
    )
    quality_review_task_id: Mapped[str | None] = mapped_column(String(36), index=True)
    quality_review_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    quality_review_error: Mapped[str | None] = mapped_column(Text)
    quality_review_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    quality_review_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

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
    exam_shares: Mapped[list[ExamShare]] = relationship(back_populates="quiz")


class Question(TimestampMixin, Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    question_type: Mapped[str] = mapped_column(String(20))
    question_subtype: Mapped[str] = mapped_column(String(40), default="general", index=True)
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
    quote_entry_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    plot_event_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_segment_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    fact_key: Mapped[str | None] = mapped_column(String(1000), index=True)
    fact_claim: Mapped[str | None] = mapped_column(Text)
    semantic_signature: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    max_score: Mapped[float] = mapped_column(Float)
    source_mode: Mapped[str | None] = mapped_column(String(30))

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
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    task_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    source_mode: Mapped[str] = mapped_column(String(30), default="pdf", index=True)
    generation_theme: Mapped[str] = mapped_column(String(30), default="general", index=True)
    theme_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
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
    question_states: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    book: Mapped[Book] = relationship(back_populates="generation_tasks")
    created_by_user: Mapped[User | None] = relationship(
        back_populates="created_generation_tasks", foreign_keys=[created_by_user_id]
    )


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


class ExamShare(TimestampMixin, Base):
    __tablename__ = "exam_shares"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    share_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    quiz_id: Mapped[str | None] = mapped_column(
        ForeignKey("quizzes.id", ondelete="SET NULL"), index=True
    )
    book_id: Mapped[str | None] = mapped_column(
        ForeignKey("books.id", ondelete="SET NULL"), index=True
    )
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    quiz_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    snapshot_version: Mapped[int] = mapped_column(Integer, default=1)
    book_title: Mapped[str] = mapped_column(String(200))
    book_author: Mapped[str] = mapped_column(String(120), default="")
    quiz_title: Mapped[str] = mapped_column(String(200))
    source_mode: Mapped[str] = mapped_column(String(30), default="pdf", index=True)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=15)
    max_score: Mapped[float] = mapped_column(Float, default=100)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    quiz: Mapped[Quiz | None] = relationship(back_populates="exam_shares")
    book: Mapped[Book | None] = relationship(back_populates="exam_shares")
    owner_user: Mapped[User] = relationship(
        back_populates="created_exam_shares", foreign_keys=[owner_user_id]
    )
    workspace: Mapped[Workspace] = relationship(back_populates="exam_shares")
    versions: Mapped[list[ExamShareVersion]] = relationship(
        back_populates="exam_share", cascade="all, delete-orphan", order_by="ExamShareVersion.version"
    )
    attempts: Mapped[list[ExamAttempt]] = relationship(
        back_populates="exam_share", cascade="all, delete-orphan"
    )


class ExamShareVersion(TimestampMixin, Base):
    __tablename__ = "exam_share_versions"
    __table_args__ = (UniqueConstraint("exam_share_id", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    exam_share_id: Mapped[str] = mapped_column(
        ForeignKey("exam_shares.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, index=True)
    quiz_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)

    exam_share: Mapped[ExamShare] = relationship(back_populates="versions")


class ExamAttempt(TimestampMixin, Base):
    __tablename__ = "exam_attempts"
    __table_args__ = (
        UniqueConstraint("exam_share_id", "participant_user_id"),
        UniqueConstraint(
            "exam_share_id",
            "participant_wechat_user_id",
            name="uq_exam_attempt_share_wechat",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    exam_share_id: Mapped[str] = mapped_column(
        ForeignKey("exam_shares.id", ondelete="CASCADE"), index=True
    )
    participant_type: Mapped[str] = mapped_column(String(20), index=True)
    participant_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    participant_wechat_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("wechat_users.id", ondelete="SET NULL"), index=True
    )
    participant_name: Mapped[str] = mapped_column(String(120))
    participant_avatar_url: Mapped[str | None] = mapped_column(Text)
    access_token_hash: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    snapshot_version: Mapped[int | None] = mapped_column(Integer, index=True)
    quiz_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="in_progress", index=True)
    total_score: Mapped[float | None] = mapped_column(Float)
    max_score: Mapped[float] = mapped_column(Float, default=100)
    elapsed_seconds: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    grading_error: Mapped[str | None] = mapped_column(Text)
    device_type: Mapped[str | None] = mapped_column(String(20))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    started_ip_address: Mapped[str | None] = mapped_column(String(80))
    submitted_ip_address: Mapped[str | None] = mapped_column(String(80))

    exam_share: Mapped[ExamShare] = relationship(back_populates="attempts")
    participant_user: Mapped[User | None] = relationship(
        back_populates="exam_attempts", foreign_keys=[participant_user_id]
    )
    participant_wechat_user: Mapped[WechatUser | None] = relationship(
        back_populates="exam_attempts", foreign_keys=[participant_wechat_user_id]
    )
    answers: Mapped[list[ExamAnswer]] = relationship(
        back_populates="exam_attempt", cascade="all, delete-orphan"
    )


class ExamAnswer(TimestampMixin, Base):
    __tablename__ = "exam_answers"
    __table_args__ = (UniqueConstraint("exam_attempt_id", "snapshot_question_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    exam_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("exam_attempts.id", ondelete="CASCADE"), index=True
    )
    snapshot_question_id: Mapped[str] = mapped_column(String(36), index=True)
    selected_answers: Mapped[list[str]] = mapped_column(JSON, default=list)
    text_answer: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float, default=0)
    max_score: Mapped[float] = mapped_column(Float)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    feedback: Mapped[str] = mapped_column(Text, default="")
    matched_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    grading_status: Mapped[str] = mapped_column(String(20), default="completed", index=True)

    exam_attempt: Mapped[ExamAttempt] = relationship(back_populates="answers")


class WechatUser(TimestampMixin, Base):
    __tablename__ = "wechat_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    openid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    unionid: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    nickname: Mapped[str] = mapped_column(String(120))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    sessions: Mapped[list[WechatSession]] = relationship(
        back_populates="wechat_user", cascade="all, delete-orphan"
    )
    exam_attempts: Mapped[list[ExamAttempt]] = relationship(
        back_populates="participant_wechat_user",
        foreign_keys="ExamAttempt.participant_wechat_user_id",
    )


class WechatSession(TimestampMixin, Base):
    __tablename__ = "wechat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    wechat_user_id: Mapped[str] = mapped_column(
        ForeignKey("wechat_users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    ip_address: Mapped[str | None] = mapped_column(String(80))

    wechat_user: Mapped[WechatUser] = relationship(back_populates="sessions")


class WechatOAuthState(Base):
    __tablename__ = "wechat_oauth_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    state_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    browser_nonce_hash: Mapped[str] = mapped_column(String(128))
    share_code: Mapped[str] = mapped_column(String(80), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_ip_address: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WechatLoginConfiguration(TimestampMixin, Base):
    __tablename__ = "wechat_login_configurations"

    id: Mapped[str] = mapped_column(String(20), primary_key=True, default="default")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    required_for_public_exams: Mapped[bool] = mapped_column(Boolean, default=False)
    app_id: Mapped[str] = mapped_column(String(128), default="")
    app_secret: Mapped[str | None] = mapped_column(Text)
    callback_base_url: Mapped[str] = mapped_column(Text, default="")
    updated_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )


class SiteFooterConfiguration(TimestampMixin, Base):
    __tablename__ = "site_footer_configurations"

    id: Mapped[str] = mapped_column(String(20), primary_key=True, default="default")
    record_number: Mapped[str] = mapped_column(String(255), default="")
    record_url: Mapped[str] = mapped_column(Text, default="")
    updated_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )


class ModelConfiguration(TimestampMixin, Base):
    __tablename__ = "model_configurations"

    id: Mapped[str] = mapped_column(String(20), primary_key=True, default="default")
    scope_type: Mapped[str] = mapped_column(String(20), default="platform", index=True)
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    updated_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
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
    scope_type: Mapped[str] = mapped_column(String(20), default="platform", index=True)
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    updated_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
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
    exam_share_id: Mapped[str | None] = mapped_column(String(36), index=True)
    exam_attempt_id: Mapped[str | None] = mapped_column(String(36), index=True)
    question_position: Mapped[int | None] = mapped_column(Integer, index=True)
    request_messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    model_response: Mapped[str | None] = mapped_column(Text)
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )

    workspace: Mapped[Workspace | None] = relationship(back_populates="usage_records")
    user: Mapped[User | None] = relationship(
        back_populates="usage_records", foreign_keys=[user_id]
    )
