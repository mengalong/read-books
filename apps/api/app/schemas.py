from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SourceMode = Literal["pdf", "material", "model_knowledge"]
GenerationTheme = Literal["general", "classic_quotes", "character"]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=2000)
    resource_type: Literal["book", "movie", "tv_series"] = "book"
    cover_color: str = "#2F6B5F"
    language: str = "中文"
    reading_status: Literal["reading", "finished", "reviewing"] = "finished"
    tags: list[str] = Field(default_factory=list)


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    author: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    resource_type: Literal["book", "movie", "tv_series"] | None = None
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
    material_count: int = 0
    ready_material_count: int = 0
    quote_count: int = 0
    confirmed_quote_count: int = 0


class BookSummary(ApiModel):
    id: str
    workspace_id: str | None = None
    owner_user_id: str | None = None
    owner_display_name: str | None = None
    resource_type: Literal["book", "movie", "tv_series"] = "book"
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
    model_knowledge_supported: bool | None = None
    model_knowledge_message: str | None = None
    model_knowledge_checked_at: datetime | None = None


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


class MaterialResponse(ApiModel):
    id: str
    book_id: str
    material_type: Literal["book_text", "script", "subtitle", "quote_sheet"]
    file_format: Literal["pdf", "txt", "srt", "vtt", "ass", "csv", "xlsx"]
    file_name: str
    file_size: int
    season_number: int | None = None
    episode_label: str | None = None
    version_label: str | None = None
    parse_status: Literal["pending", "processing", "needs_review", "completed", "failed"]
    error_message: str | None = None
    segment_count: int = 0
    quote_count: int = 0
    created_at: datetime
    updated_at: datetime


class QuoteEntryResponse(ApiModel):
    id: str
    book_id: str
    material_id: str
    material_file_name: str
    source_segment_ids: list[str]
    quote_text: str
    speaker: str | None = None
    speaker_origin: Literal["provided", "inferred", "confirmed", "unknown"]
    context: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    page_number: int | None = None
    review_status: Literal["pending", "confirmed", "rejected"]
    enabled_for_generation: bool
    created_at: datetime
    updated_at: datetime


class QuoteEntryListResponse(BaseModel):
    items: list[QuoteEntryResponse]
    total: int
    speakers: list[str] = Field(default_factory=list)
    pending_count: int = 0
    confirmed_count: int = 0


class QuoteEntryUpdateRequest(BaseModel):
    speaker: str | None = Field(default=None, max_length=120)
    context: str | None = Field(default=None, max_length=2000)
    review_status: Literal["pending", "confirmed", "rejected"] | None = None
    enabled_for_generation: bool | None = None


class QuoteEntryBulkRequest(BaseModel):
    quote_ids: list[str] = Field(min_length=1, max_length=200)


class QuizSummary(BaseModel):
    id: str
    book_id: str
    title: str
    difficulty: str
    duration_minutes: int
    status: str
    source_mode: SourceMode = "pdf"
    generation_theme: GenerationTheme = "general"
    theme_config: dict[str, Any] = Field(default_factory=dict)
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
    page_number: int | None = None
    excerpt: str
    highlight: str | None = None
    support: str
    material_id: str | None = None
    material_type: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    speaker: str | None = None


class QuestionOption(BaseModel):
    id: str
    text: str


class QuestionUpdateRequest(BaseModel):
    prompt: str | None = None
    options: list[QuestionOption] | None = None
    correct_answers: list[str] | None = None
    explanation: str | None = None
    knowledge_point: str | None = Field(default=None, max_length=120)
    reference_answer: str | None = None
    grading_rubric: list[dict[str, Any]] | None = None


class QuizThemeConfig(BaseModel):
    material_ids: list[str] = Field(default_factory=list, max_length=50)
    character_names: list[str] = Field(default_factory=list, max_length=20)
    question_subtypes: list[
        Literal[
            "quote_speaker",
            "quote_context",
            "quote_meaning",
            "character_relation",
            "character_trait",
        ]
    ] = Field(default_factory=list, max_length=5)

    @field_validator("material_ids", "character_names", "question_subtypes")
    @classmethod
    def unique_non_empty_values(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        return list(dict.fromkeys(cleaned))


class QuizGenerateRequest(BaseModel):
    duration_minutes: int = Field(default=15, ge=5, le=45)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    single_count: int = Field(default=5, ge=0, le=15)
    multiple_count: int = Field(default=3, ge=0, le=10)
    short_count: int = Field(default=2, ge=0, le=8)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    generation_theme: GenerationTheme = "general"
    theme_config: QuizThemeConfig = Field(default_factory=QuizThemeConfig)


class QuizGenerationTaskResponse(BaseModel):
    id: str
    book_id: str
    task_type: str
    status: Literal["pending", "processing", "completed", "failed"]
    source_mode: SourceMode
    generation_theme: GenerationTheme = "general"
    theme_config: dict[str, Any] = Field(default_factory=dict)
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
    question_subtype: str = "general"
    prompt: str
    options: list[QuestionOption]
    explanation: str | None = None
    knowledge_point: str
    difficulty: str
    estimated_seconds: int
    reference_answer: str | None = None
    grading_rubric: list[dict[str, Any]] = Field(default_factory=list)
    source_evidence: list[SourceEvidence]
    quote_entry_ids: list[str] = Field(default_factory=list)
    source_segment_ids: list[str] = Field(default_factory=list)
    max_score: float
    correct_answers: list[str] | None = None
    source_mode: SourceMode | None = None


class QuizResponse(ApiModel):
    id: str
    book_id: str
    book_title: str
    title: str
    difficulty: str
    duration_minutes: int
    status: str
    source_mode: SourceMode
    generation_theme: GenerationTheme = "general"
    theme_config: dict[str, Any] = Field(default_factory=dict)
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


class ExamShareCreate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    expires_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("考试活动名称不能为空")
        return value


class ExamShareUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["active", "stopped"] | None = None
    expires_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("考试活动名称不能为空")
        return value


class ExamAttemptCreate(BaseModel):
    participant_name: str | None = Field(default=None, max_length=50)


class ExamQuestionResponse(BaseModel):
    id: str
    position: int
    question_type: Literal["single", "multiple", "short"]
    question_subtype: str = "general"
    prompt: str
    options: list[QuestionOption] = Field(default_factory=list)
    knowledge_point: str
    difficulty: str
    estimated_seconds: int
    max_score: float
    correct_answers: list[str] | None = None
    explanation: str | None = None
    reference_answer: str | None = None
    grading_rubric: list[dict[str, Any]] = Field(default_factory=list)
    source_evidence: list[SourceEvidence] = Field(default_factory=list)
    quote_entry_ids: list[str] = Field(default_factory=list)
    source_segment_ids: list[str] = Field(default_factory=list)
    source_mode: SourceMode | None = None


class PublicExamResponse(BaseModel):
    share_code: str
    name: str
    status: Literal["active", "stopped", "source_deleted", "expired"]
    book_title: str
    book_author: str
    quiz_title: str
    owner_display_name: str
    difficulty: str
    duration_minutes: int
    source_mode: SourceMode
    generation_theme: GenerationTheme = "general"
    theme_config: dict[str, Any] = Field(default_factory=dict)
    max_score: float
    question_count: int
    single_count: int
    multiple_count: int
    short_count: int
    expires_at: datetime | None
    authenticated: bool
    identity_type: Literal["user", "wechat", "anonymous"] = "anonymous"
    participant_name: str | None = None
    participant_avatar_url: str | None = None
    wechat_login_enabled: bool = False
    wechat_login_required: bool = False
    existing_attempt_id: str | None = None
    existing_attempt_status: str | None = None


class ExamAnswerResponse(BaseModel):
    question_id: str
    selected_answers: list[str] = Field(default_factory=list)
    text_answer: str | None = None
    score: float
    max_score: float
    is_correct: bool
    feedback: str
    matched_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    grading_status: Literal["pending", "completed", "failed"]


class ExamWeakKnowledgePoint(BaseModel):
    knowledge_point: str
    score: float
    max_score: float
    score_percentage: float
    question_count: int
    focus_points: list[str] = Field(default_factory=list)
    recommendation: str


class ExamAttemptResponse(BaseModel):
    id: str
    exam_share_id: str
    share_code: str
    exam_name: str
    book_title: str
    quiz_title: str
    participant_type: Literal["user", "wechat", "anonymous"]
    participant_name: str
    participant_avatar_url: str | None = None
    status: Literal["in_progress", "grading", "completed", "grading_failed"]
    total_score: float | None
    max_score: float
    elapsed_seconds: int | None
    started_at: datetime
    submitted_at: datetime | None
    completed_at: datetime | None
    grading_error: str | None
    device_type: Literal["desktop", "mobile", "tablet", "unknown"] | None = None
    user_agent: str | None = None
    started_ip_address: str | None = None
    submitted_ip_address: str | None = None
    ip_changed: bool = False
    duration_minutes: int
    source_mode: SourceMode
    generation_theme: GenerationTheme = "general"
    theme_config: dict[str, Any] = Field(default_factory=dict)
    questions: list[ExamQuestionResponse]
    answers: list[ExamAnswerResponse] = Field(default_factory=list)
    weak_knowledge_points: list[ExamWeakKnowledgePoint] = Field(default_factory=list)
    recommended_direction: str | None = None
    access_token: str | None = None


class ExamAttemptSummary(BaseModel):
    id: str
    participant_type: Literal["user", "wechat", "anonymous"]
    participant_user_id: str | None
    participant_name: str
    participant_avatar_url: str | None = None
    status: Literal["in_progress", "grading", "completed", "grading_failed"]
    total_score: float | None
    max_score: float
    score_percentage: float | None
    elapsed_seconds: int | None
    started_at: datetime
    submitted_at: datetime | None
    completed_at: datetime | None
    grading_error: str | None
    device_type: Literal["desktop", "mobile", "tablet", "unknown"] | None = None
    started_ip_address: str | None = None
    submitted_ip_address: str | None = None
    ip_changed: bool = False


class ExamShareSummary(BaseModel):
    id: str
    share_code: str
    name: str
    status: Literal["active", "stopped", "source_deleted", "expired"]
    quiz_id: str | None
    book_id: str | None
    owner_user_id: str
    owner_username: str
    owner_display_name: str
    workspace_id: str
    book_title: str
    book_author: str
    quiz_title: str
    source_mode: SourceMode
    generation_theme: GenerationTheme = "general"
    theme_config: dict[str, Any] = Field(default_factory=dict)
    difficulty: str
    duration_minutes: int
    max_score: float
    question_count: int
    single_count: int
    multiple_count: int
    short_count: int
    started_count: int
    submitted_count: int
    grading_count: int
    grading_failed_count: int
    completion_rate: float
    average_score: float | None
    highest_score: float | None
    created_at: datetime
    updated_at: datetime
    stopped_at: datetime | None
    expires_at: datetime | None
    last_attempt_at: datetime | None


class ExamShareDetail(ExamShareSummary):
    attempts: list[ExamAttemptSummary] = Field(default_factory=list)


class ExamShareVersionSummary(BaseModel):
    version: int
    is_current: bool
    question_count: int
    single_count: int
    multiple_count: int
    short_count: int
    max_score: float
    created_at: datetime


class ExamShareEditResponse(BaseModel):
    id: str
    share_code: str
    name: str
    status: Literal["active", "stopped", "source_deleted", "expired"]
    quiz_id: str | None
    book_id: str | None
    owner_user_id: str
    owner_username: str
    owner_display_name: str
    book_title: str
    book_author: str
    quiz_title: str
    source_mode: SourceMode
    generation_theme: GenerationTheme = "general"
    theme_config: dict[str, Any] = Field(default_factory=dict)
    difficulty: str
    duration_minutes: int
    max_score: float
    snapshot_version: int
    created_at: datetime
    updated_at: datetime
    questions: list[QuestionResponse] = Field(default_factory=list)
    versions: list[ExamShareVersionSummary] = Field(default_factory=list)


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
    source_mode: SourceMode
    generation_theme: GenerationTheme = "general"
    theme_config: dict[str, Any] = Field(default_factory=dict)
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


class WechatLoginConfigurationUpdate(BaseModel):
    enabled: bool = False
    required_for_public_exams: bool = False
    app_id: str = Field(default="", max_length=128)
    app_secret: str | None = Field(default=None, max_length=500)
    callback_base_url: str = Field(default="", max_length=2_000)


class WechatLoginConfigurationResponse(ApiModel):
    id: str
    enabled: bool
    required_for_public_exams: bool
    app_id: str
    app_secret_configured: bool
    callback_base_url: str
    callback_url: str
    configuration_complete: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WechatIdentityUserResponse(ApiModel):
    id: str
    openid: str
    unionid: str | None = None
    nickname: str
    avatar_url: str | None = None
    last_login_at: datetime | None = None


class WechatIdentitySessionResponse(ApiModel):
    id: str
    expires_at: datetime
    last_seen_at: datetime | None = None


class WechatIdentityResponse(ApiModel):
    user: WechatIdentityUserResponse
    session: WechatIdentitySessionResponse


class SiteFooterConfigurationUpdate(BaseModel):
    record_number: str = Field(default="", max_length=255)
    record_url: str = Field(default="", max_length=2_000)


class SiteFooterConfigurationResponse(ApiModel):
    id: str
    record_number: str
    record_url: str
    configuration_complete: bool
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
    exam_share_id: str | None = None
    exam_attempt_id: str | None = None
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
    exam_share_id: str | None = None
    exam_attempt_id: str | None = None
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


class AccessStatisticsSummaryResponse(BaseModel):
    visit_count: int = 0
    login_count: int = 0
    active_user_count: int = 0
    total_duration_seconds: int = 0
    average_duration_seconds: int = 0


class AccessStatisticsPeriodResponse(AccessStatisticsSummaryResponse):
    period_key: str
    period_label: str
    period_start: datetime
    period_end: datetime


class AccessStatisticsUserResponse(BaseModel):
    user_id: str
    workspace_id: str
    username: str
    display_name: str
    visit_count: int = 0
    login_count: int = 0
    active_period_count: int = 0
    total_duration_seconds: int = 0
    average_duration_seconds: int = 0
    first_visit_at: datetime | None = None
    last_visit_at: datetime | None = None


class AccessStatisticsReportResponse(BaseModel):
    granularity: Literal["day", "month", "year"]
    timezone: str = "Asia/Shanghai"
    range_start: datetime
    range_end: datetime
    selected_user_id: str | None = None
    summary: AccessStatisticsSummaryResponse
    periods: list[AccessStatisticsPeriodResponse] = Field(default_factory=list)
    users: list[AccessStatisticsUserResponse] = Field(default_factory=list)


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
