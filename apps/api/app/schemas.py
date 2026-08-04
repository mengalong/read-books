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
    workspace_id: str | None = None
    owner_user_id: str | None = None
    owner_display_name: str | None = None
    title: str
    author: str
    description: str
    cover_color: str
    language: str
    reading_status: str
    shelf_status: Literal["active", "unlisted"] = "active"
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    stats: BookStats = Field(default_factory=BookStats)
    pre_generation_enabled: bool = False
    pre_generation_status: str = "disabled"
    pre_generation_error: str | None = None
    pre_generation_quiz_id: str | None = None
    active_generation_task_id: str | None = None
    active_generation_status: str | None = None
    active_generation_completed_questions: int = 0
    active_generation_total_questions: int = 0
    active_generation_phase: str | None = None


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


class QuizSummary(BaseModel):
    id: str
    book_id: str
    title: str
    difficulty: str
    duration_minutes: int
    status: str
    source_mode: Literal["pdf", "model_knowledge"] = "pdf"
    question_count: int
    single_count: int = 0
    multiple_count: int = 0
    short_count: int = 0
    max_score: float
    created_at: datetime
    review_count: int = 0
    latest_score: float | None = None
    last_reviewed_at: datetime | None = None


class BookDetail(BookSummary):
    pdfs: list[PdfResponse] = Field(default_factory=list)
    quizzes: list[QuizSummary] = Field(default_factory=list)


class AdminBookCopyRequest(BaseModel):
    target_user_id: str = Field(min_length=1, max_length=36)
    copy_pdf: bool = True
    copy_content: bool = True


class AdminBookCopyResponse(BaseModel):
    book: BookDetail
    source_book_id: str
    target_user_id: str
    copied_pdf_count: int
    copied_chunk_count: int


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
    highlight: str | None = None
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


class QuizGenerationTaskResponse(BaseModel):
    id: str
    book_id: str
    task_type: str
    status: Literal["pending", "processing", "completed", "failed"]
    source_mode: Literal["pdf", "model_knowledge"]
    total_questions: int
    completed_questions: int
    current_question_position: int | None
    current_phase: str
    difficulty: str
    duration_minutes: int
    single_count: int
    multiple_count: int
    short_count: int
    quiz_id: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


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
    source_mode: Literal["pdf", "model_knowledge"]
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


class ReviewTaskResponse(BaseModel):
    id: str
    quiz_id: str
    book_id: str
    book_title: str
    title: str
    attempt_number: int
    status: Literal["in_progress", "submitted"]
    source_mode: Literal["pdf", "model_knowledge"]
    difficulty: str
    duration_minutes: int
    total_score: float | None
    max_score: float
    elapsed_seconds: int | None
    submitted_at: datetime | None
    next_review_date: date | None
    created_at: datetime
    questions: list[QuestionResponse]
    answers: list[AnswerResult] = Field(default_factory=list)
    weak_points: list[str] = Field(default_factory=list)


class HistoryItem(ApiModel):
    id: str
    quiz_id: str
    book_id: str
    book_title: str
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


class ReviewTaskSummary(ApiModel):
    id: str
    quiz_id: str
    book_id: str
    book_title: str
    title: str
    attempt_number: int
    status: Literal["in_progress", "submitted"]
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


class ModelConfigurationUpdate(BaseModel):
    provider_mode: Literal["mock", "openai_compatible"] = "mock"
    base_url: str = Field(default="", max_length=2_000)
    model_name: str = Field(default="", max_length=200)
    api_key: str | None = Field(default=None, max_length=4_000)
    clear_api_key: bool = False
    timeout_ms: int = Field(default=180_000, ge=1_000, le=300_000)
    temperature: float = Field(default=0.2, ge=0, le=2)


class ModelConfigurationResponse(ApiModel):
    id: str
    provider_mode: str
    base_url: str
    model_name: str
    timeout_ms: int
    temperature: float
    api_key_configured: bool
    last_test_status: str | None = None
    last_test_message: str | None = None
    last_tested_at: datetime | None = None
    last_test_latency_ms: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ModelConnectionTestRequest(BaseModel):
    base_url: str = Field(max_length=2_000)
    model_name: str = Field(max_length=200)
    api_key: str | None = Field(default=None, max_length=4_000)
    clear_api_key: bool = False
    timeout_ms: int = Field(default=180_000, ge=1_000, le=300_000)


class ModelConnectionTestResponse(BaseModel):
    ok: bool
    message: str
    latency_ms: int
    model_name: str
    model_response: str | None = None
    tested_at: datetime


class PreGenerationResponse(BaseModel):
    status: Literal["disabled", "pending", "processing", "completed", "failed"]
    message: str
    error_message: str | None = None
    quiz_id: str | None = None
    task_id: str | None = None


class PromptTemplateUpdate(BaseModel):
    system_prompt: str = Field(min_length=1, max_length=20_000)
    user_prompt: str = Field(min_length=1, max_length=40_000)


class PromptTemplateResponse(ApiModel):
    id: str
    prompt_type: Literal["generation", "grading"]
    system_prompt: str
    user_prompt: str
    version: int
    is_active: bool
    available_variables: list[str]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PromptPreviewResponse(BaseModel):
    prompt_type: Literal["generation", "grading"]
    rendered_system_prompt: str
    rendered_user_prompt: str
    available_variables: list[str]


class TokenUsageStageResponse(ApiModel):
    id: str
    user_id: str | None = None
    workspace_id: str | None = None
    phase: str
    call_number: int
    model_name: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    status: Literal["success", "failed"]
    error_message: str | None
    latency_ms: int
    created_at: datetime


class TokenUsageTaskResponse(BaseModel):
    task_id: str
    task_type: str
    task_label: str
    user_id: str | None
    username: str | None
    display_name: str | None
    workspace_id: str | None
    status: Literal["success", "failed"]
    book_id: str | None
    quiz_id: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    unreported_calls: int
    started_at: datetime
    finished_at: datetime
    stages: list[TokenUsageStageResponse]


class TokenUsageUserSummaryResponse(ApiModel):
    user_id: str
    username: str
    display_name: str
    task_count: int
    total_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


class TokenUsageSummaryResponse(BaseModel):
    task_count: int
    total_calls: int
    successful_calls: int
    failed_calls: int
    unreported_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


class TokenUsageReportResponse(BaseModel):
    summary: TokenUsageSummaryResponse
    users: list[TokenUsageUserSummaryResponse] = Field(default_factory=list)
    tasks: list[TokenUsageTaskResponse]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class WorkspaceResponse(ApiModel):
    id: str
    name: str


class CurrentUserResponse(ApiModel):
    id: str
    username: str
    display_name: str
    role: Literal["admin", "user"]
    status: Literal["active", "disabled"]
    must_change_password: bool
    last_login_at: datetime | None
    workspace: WorkspaceResponse


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)


class AdminUserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    temporary_password: str | None = Field(default=None, min_length=8, max_length=128)
    role: Literal["admin", "user"] = "user"


class AdminUserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Literal["admin", "user"] | None = None
    status: Literal["active", "disabled"] | None = None


class AdminUserResponse(CurrentUserResponse):
    created_at: datetime
    updated_at: datetime


class AdminUserCreateResponse(BaseModel):
    user: AdminUserResponse
    temporary_password: str


class PasswordResetResponse(BaseModel):
    user_id: str
    temporary_password: str
    must_change_password: bool = True
