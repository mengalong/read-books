export type ResourceType = "book" | "movie" | "tv_series";
export type ReadingStatus = "reading" | "finished" | "reviewing";
export type ShelfStatus = "active" | "unlisted";

export type ModelProviderMode = "mock" | "openai_compatible";

export type ModelConfiguration = {
  id: string;
  provider_mode: ModelProviderMode;
  base_url: string;
  model_name: string;
  timeout_ms: number;
  temperature: number;
  api_key_configured: boolean;
  last_test_status: "success" | "failed" | null;
  last_test_message: string | null;
  last_tested_at: string | null;
  last_test_latency_ms: number | null;
  created_at: string | null;
  updated_at: string | null;
};

export type ModelConnectionTestResult = {
  ok: boolean;
  message: string;
  latency_ms: number;
  model_name: string;
  model_response: string;
  tested_at: string;
};

export type WechatLoginConfiguration = {
  id: string;
  enabled: boolean;
  required_for_public_exams: boolean;
  app_id: string;
  app_secret_configured: boolean;
  callback_base_url: string;
  callback_url: string;
  configuration_complete: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type SiteFooterConfiguration = {
  id: string;
  record_number: string;
  record_url: string;
  configuration_complete: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type PromptType = "generation" | "grading";

export type PromptTemplate = {
  id: string;
  prompt_type: PromptType;
  system_prompt: string;
  user_prompt: string;
  version: number;
  is_active: boolean;
  available_variables: string[];
  created_at: string | null;
  updated_at: string | null;
};

export type PromptPreview = {
  prompt_type: PromptType;
  rendered_system_prompt: string;
  rendered_user_prompt: string;
  available_variables: string[];
};

export type TokenUsageStage = {
  id: string;
  user_id: string | null;
  workspace_id: string | null;
  phase: string;
  call_number: number;
  model_name: string;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  status: "success" | "failed";
  error_message: string | null;
  latency_ms: number;
  created_at: string;
};

export type TokenUsageTask = {
  task_id: string;
  task_type: string;
  task_label: string;
  user_id: string | null;
  username: string | null;
  display_name: string | null;
  workspace_id: string | null;
  status: "success" | "failed";
  book_id: string | null;
  quiz_id: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  unreported_calls: number;
  started_at: string;
  finished_at: string;
  stages: TokenUsageStage[];
};

export type TokenUsageReport = {
  summary: {
    task_count: number;
    total_calls: number;
    successful_calls: number;
    failed_calls: number;
    unreported_calls: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
  users: {
    user_id: string;
    username: string;
    display_name: string;
    task_count: number;
    total_calls: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  }[];
  tasks: TokenUsageTask[];
};

export type AccessGranularity = "day" | "month" | "year";

export type AccessStatisticsSummary = {
  visit_count: number;
  login_count: number;
  active_user_count: number;
  total_duration_seconds: number;
  average_duration_seconds: number;
};

export type AccessStatisticsPeriod = AccessStatisticsSummary & {
  period_key: string;
  period_label: string;
  period_start: string;
  period_end: string;
};

export type AccessStatisticsUser = {
  user_id: string;
  workspace_id: string;
  username: string;
  display_name: string;
  visit_count: number;
  login_count: number;
  active_period_count: number;
  total_duration_seconds: number;
  average_duration_seconds: number;
  first_visit_at: string | null;
  last_visit_at: string | null;
};

export type AccessStatisticsReport = {
  granularity: AccessGranularity;
  timezone: string;
  range_start: string;
  range_end: string;
  selected_user_id: string | null;
  summary: AccessStatisticsSummary;
  periods: AccessStatisticsPeriod[];
  users: AccessStatisticsUser[];
};

export type CurrentUser = {
  id: string;
  username: string;
  display_name: string;
  role: "admin" | "user";
  status: "active" | "disabled";
  must_change_password: boolean;
  last_login_at: string | null;
  workspace: { id: string; name: string };
};

export type AdminUser = CurrentUser & {
  created_at: string;
  updated_at: string;
};

export type AdminUserCreateResult = {
  user: AdminUser;
  temporary_password: string;
};

export type PasswordResetResult = {
  user_id: string;
  temporary_password: string;
  must_change_password: boolean;
};

export type AdminBookCopyResult = {
  book: BookDetail;
  source_book_id: string;
  target_user_id: string;
  copied_pdf_count: number;
  copied_chunk_count: number;
};

export type PreGenerationResponse = {
  status: "disabled" | "pending" | "processing" | "completed" | "failed";
  message: string;
  error_message: string | null;
  quiz_id: string | null;
  task_id: string | null;
};

export type QuestionType = "single" | "multiple" | "short";
export type SourceMode = "pdf" | "model_knowledge";

export type BookStats = {
  pdf_count: number;
  completed_pdf_count: number;
  chunk_count: number;
  quiz_count: number;
  average_score: number | null;
  last_reviewed_at: string | null;
  next_review_date: string | null;
};

export type BookSummary = {
  id: string;
  workspace_id: string | null;
  owner_user_id: string | null;
  owner_display_name: string | null;
  resource_type: ResourceType;
  title: string;
  author: string;
  description: string;
  cover_color: string;
  language: string;
  reading_status: ReadingStatus;
  shelf_status: ShelfStatus;
  tags: string[];
  created_at: string;
  updated_at: string;
  pre_generation_enabled: boolean;
  pre_generation_status: PreGenerationResponse["status"];
  pre_generation_error: string | null;
  pre_generation_quiz_id: string | null;
  active_generation_task_id: string | null;
  active_generation_status: "pending" | "processing" | null;
  active_generation_completed_questions: number;
  active_generation_total_questions: number;
  active_generation_phase: string | null;
  stats: BookStats;
  model_knowledge_supported: boolean | null;
  model_knowledge_message: string | null;
  model_knowledge_checked_at: string | null;
};

export type PdfDocument = {
  id: string;
  book_id: string;
  file_name: string;
  file_size: number;
  page_count: number;
  chunk_count: number;
  parse_status: "pending" | "processing" | "completed" | "failed";
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type BookDetail = BookSummary & { pdfs: PdfDocument[]; quizzes: QuizSummary[] };

export type QuizSummary = {
  id: string;
  book_id: string;
  title: string;
  difficulty: string;
  duration_minutes: number;
  status: string;
  source_mode: SourceMode;
  question_count: number;
  single_count: number;
  multiple_count: number;
  short_count: number;
  max_score: number;
  created_at: string;
  review_count: number;
  latest_score: number | null;
  last_reviewed_at: string | null;
};

export type Chunk = {
  id: string;
  pdf_id: string;
  page_number: number;
  sequence: number;
  content: string;
  char_count: number;
  file_name: string;
};

export type SourceEvidence = {
  chunk_id: string;
  file_name: string;
  page_number: number;
  excerpt: string;
  highlight?: string | null;
  support: string;
};

export type QuestionOption = { id: string; text: string };

export type QuestionUpdatePayload = {
  prompt?: string;
  options?: QuestionOption[];
  correct_answers?: string[];
  explanation?: string | null;
  knowledge_point?: string;
  reference_answer?: string | null;
  grading_rubric?: { point: string; keywords?: string[]; score?: number }[];
};

export type Question = {
  id: string;
  position: number;
  question_type: QuestionType;
  prompt: string;
  options: QuestionOption[];
  explanation: string | null;
  knowledge_point: string;
  difficulty: string;
  estimated_seconds: number;
  reference_answer: string | null;
  grading_rubric: { point: string; keywords?: string[]; score?: number }[];
  source_evidence: SourceEvidence[];
  max_score: number;
  correct_answers: string[] | null;
};

export type Quiz = {
  id: string;
  book_id: string;
  book_title: string;
  title: string;
  difficulty: string;
  duration_minutes: number;
  status: "ready" | "submitted";
  source_mode: SourceMode;
  total_score: number | null;
  max_score: number;
  elapsed_seconds: number | null;
  submitted_at: string | null;
  next_review_date: string | null;
  created_at: string;
  questions: Question[];
};

export type QuizGenerationTask = {
  id: string;
  book_id: string;
  task_type: string;
  status: "pending" | "processing" | "completed" | "failed";
  source_mode: SourceMode;
  total_questions: number;
  completed_questions: number;
  current_question_position: number | null;
  current_phase: string;
  difficulty: string;
  duration_minutes: number;
  single_count: number;
  multiple_count: number;
  short_count: number;
  quiz_id: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type AnswerResult = {
  question_id: string;
  selected_answers: string[];
  text_answer: string | null;
  score: number;
  max_score: number;
  is_correct: boolean;
  feedback: string;
  matched_points: string[];
  missing_points: string[];
};

export type QuizResult = Quiz & {
  answers: AnswerResult[];
  weak_points: string[];
};

export type ReviewTask = {
  id: string;
  quiz_id: string;
  book_id: string;
  book_title: string;
  title: string;
  attempt_number: number;
  status: "in_progress" | "submitted";
  source_mode: SourceMode;
  difficulty: string;
  duration_minutes: number;
  total_score: number | null;
  max_score: number;
  elapsed_seconds: number | null;
  submitted_at: string | null;
  next_review_date: string | null;
  created_at: string;
  questions: Question[];
  answers: AnswerResult[];
  weak_points: string[];
};

export type HistoryItem = {
  id: string;
  quiz_id: string;
  book_id: string;
  book_title: string;
  title: string;
  difficulty: string;
  status: "in_progress" | "submitted";
  total_score: number | null;
  max_score: number;
  duration_minutes: number;
  elapsed_seconds: number | null;
  question_count: number;
  created_at: string;
  submitted_at: string | null;
  next_review_date: string | null;
};

export type ReviewTaskSummary = HistoryItem & { attempt_number: number };

export type ExamShareStatus = "active" | "stopped" | "source_deleted" | "expired";
export type ExamAttemptStatus = "in_progress" | "grading" | "completed" | "grading_failed";
export type ExamDeviceType = "desktop" | "mobile" | "tablet" | "unknown";

export type ExamQuestion = {
  id: string;
  position: number;
  question_type: QuestionType;
  prompt: string;
  options: QuestionOption[];
  knowledge_point: string;
  difficulty: string;
  estimated_seconds: number;
  max_score: number;
  correct_answers: string[] | null;
  explanation: string | null;
  reference_answer: string | null;
  grading_rubric: { point: string; keywords?: string[]; score?: number }[];
  source_evidence: SourceEvidence[];
};

export type ExamAnswer = {
  question_id: string;
  selected_answers: string[];
  text_answer: string | null;
  score: number;
  max_score: number;
  is_correct: boolean;
  feedback: string;
  matched_points: string[];
  missing_points: string[];
  grading_status: "pending" | "completed" | "failed";
};

export type ExamWeakKnowledgePoint = {
  knowledge_point: string;
  score: number;
  max_score: number;
  score_percentage: number;
  question_count: number;
  focus_points: string[];
  recommendation: string;
};

export type ExamAttempt = {
  id: string;
  exam_share_id: string;
  share_code: string;
  exam_name: string;
  book_title: string;
  quiz_title: string;
  participant_type: "user" | "wechat" | "anonymous";
  participant_name: string;
  participant_avatar_url: string | null;
  status: ExamAttemptStatus;
  total_score: number | null;
  max_score: number;
  elapsed_seconds: number | null;
  started_at: string;
  submitted_at: string | null;
  completed_at: string | null;
  grading_error: string | null;
  device_type: ExamDeviceType | null;
  user_agent: string | null;
  started_ip_address: string | null;
  submitted_ip_address: string | null;
  ip_changed: boolean;
  duration_minutes: number;
  source_mode: SourceMode;
  questions: ExamQuestion[];
  answers: ExamAnswer[];
  weak_knowledge_points: ExamWeakKnowledgePoint[];
  recommended_direction: string | null;
  access_token: string | null;
};

export type ExamAttemptSummary = {
  id: string;
  participant_type: "user" | "wechat" | "anonymous";
  participant_user_id: string | null;
  participant_name: string;
  participant_avatar_url: string | null;
  status: ExamAttemptStatus;
  total_score: number | null;
  max_score: number;
  score_percentage: number | null;
  elapsed_seconds: number | null;
  started_at: string;
  submitted_at: string | null;
  completed_at: string | null;
  grading_error: string | null;
  device_type: ExamDeviceType | null;
  started_ip_address: string | null;
  submitted_ip_address: string | null;
  ip_changed: boolean;
};

export type ExamShare = {
  id: string;
  share_code: string;
  name: string;
  status: ExamShareStatus;
  quiz_id: string | null;
  book_id: string | null;
  owner_user_id: string;
  owner_username: string;
  owner_display_name: string;
  workspace_id: string;
  book_title: string;
  book_author: string;
  quiz_title: string;
  source_mode: SourceMode;
  difficulty: string;
  duration_minutes: number;
  max_score: number;
  question_count: number;
  single_count: number;
  multiple_count: number;
  short_count: number;
  started_count: number;
  submitted_count: number;
  grading_count: number;
  grading_failed_count: number;
  completion_rate: number;
  average_score: number | null;
  highest_score: number | null;
  created_at: string;
  updated_at: string;
  stopped_at: string | null;
  expires_at: string | null;
  last_attempt_at: string | null;
  attempts?: ExamAttemptSummary[];
};

export type PublicExam = {
  share_code: string;
  name: string;
  status: ExamShareStatus;
  book_title: string;
  book_author: string;
  quiz_title: string;
  owner_display_name: string;
  difficulty: string;
  duration_minutes: number;
  source_mode: SourceMode;
  max_score: number;
  question_count: number;
  single_count: number;
  multiple_count: number;
  short_count: number;
  expires_at: string | null;
  authenticated: boolean;
  identity_type: "user" | "wechat" | "anonymous";
  participant_name: string | null;
  participant_avatar_url: string | null;
  wechat_login_enabled: boolean;
  wechat_login_required: boolean;
  existing_attempt_id: string | null;
  existing_attempt_status: ExamAttemptStatus | null;
};
