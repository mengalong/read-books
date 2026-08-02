from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=2000)
    cover_color: str = "#2F6B5F"
    language: str = "中文"
    reading_status: Literal["reading", "finished", "reviewing"] = "finished"
    tags: list[str] = Field(default_factory=list)


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    author: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    cover_color: str | None = None
    language: str | None = None
    reading_status: Literal["reading", "finished", "reviewing"] | None = None
    tags: list[str] | None = None


class BookStats(ApiModel):
    pdf_count: int = 0
    completed_pdf_count: int = 0
    chunk_count: int = 0
    quiz_count: int = 0
    average_score: float | None = None
    last_reviewed_at: datetime | None = None
    next_review_date: date | None = None


class BookSummary(ApiModel):
    id: str
    title: str
    author: str
    description: str
    cover_color: str
    language: str
    reading_status: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    stats: BookStats = Field(default_factory=BookStats)


class PdfResponse(ApiModel):
    id: str
    book_id: str
    file_name: str
    file_size: int
    page_count: int
    chunk_count: int
    parse_status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class BookDetail(BookSummary):
    pdfs: list[PdfResponse] = Field(default_factory=list)


class ChunkResponse(ApiModel):
    id: str
    pdf_id: str
    page_number: int
    sequence: int
    content: str
    char_count: int
    file_name: str


class SourceEvidence(BaseModel):
    chunk_id: str
    file_name: str
    page_number: int
    excerpt: str
    support: str


class QuestionOption(BaseModel):
    id: str
    text: str


class QuizGenerateRequest(BaseModel):
    duration_minutes: int = Field(default=15, ge=5, le=45)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    single_count: int = Field(default=5, ge=0, le=15)
    multiple_count: int = Field(default=3, ge=0, le=10)
    short_count: int = Field(default=2, ge=0, le=8)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)


class QuestionResponse(ApiModel):
    id: str
    position: int
    question_type: str
    prompt: str
    options: list[QuestionOption]
    explanation: str | None = None
    knowledge_point: str
    difficulty: str
    estimated_seconds: int
    reference_answer: str | None = None
    grading_rubric: list[dict[str, Any]] = Field(default_factory=list)
    source_evidence: list[SourceEvidence]
    max_score: float
    correct_answers: list[str] | None = None


class QuizResponse(ApiModel):
    id: str
    book_id: str
    book_title: str
    title: str
    difficulty: str
    duration_minutes: int
    status: str
    total_score: float | None
    max_score: float
    elapsed_seconds: int | None
    submitted_at: datetime | None
    next_review_date: date | None
    created_at: datetime
    questions: list[QuestionResponse]


class AnswerSubmission(BaseModel):
    question_id: str
    selected_answers: list[str] = Field(default_factory=list)
    text_answer: str | None = Field(default=None, max_length=10_000)


class QuizSubmitRequest(BaseModel):
    answers: list[AnswerSubmission]
    elapsed_seconds: int = Field(default=0, ge=0)


class AnswerResult(ApiModel):
    question_id: str
    selected_answers: list[str]
    text_answer: str | None
    score: float
    max_score: float
    is_correct: bool
    feedback: str
    matched_points: list[str]
    missing_points: list[str]


class QuizResult(QuizResponse):
    answers: list[AnswerResult]
    weak_points: list[str]


class HistoryItem(ApiModel):
    id: str
    title: str
    difficulty: str
    status: str
    total_score: float | None
    max_score: float
    duration_minutes: int
    elapsed_seconds: int | None
    question_count: int
    created_at: datetime
    submitted_at: datetime | None
    next_review_date: date | None


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str
    mock_mode: bool
