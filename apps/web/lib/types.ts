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

export type WechatIdentityResponse = {
  user: {
    id: string;
    openid: string;
    unionid: string | null;
    nickname: string;
    avatar_url: string | null;
    last_login_at: string | null;
  };
  session: {
    id: string;
    expires_at: string;
    last_seen_at: string | null;
  };
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
export type SourceMode = "pdf" | "material" | "plot" | "combined" | "model_knowledge";
export type GenerationTheme = "general" | "classic_quotes" | "character";
export type QuestionSubtype =
  | "general"
  | "quote_speaker"
  | "quote_context"
  | "quote_meaning"
  | "character_relation"
  | "character_trait";

export type QuizThemeConfig = {
  material_ids: string[];
  character_names: string[];
  question_subtypes: QuestionSubtype[];
};

export type BookStats = {
  pdf_count: number;
  completed_pdf_count: number;
  chunk_count: number;
  quiz_count: number;
  average_score: number | null;
  last_reviewed_at: string | null;
  next_review_date: string | null;
  material_count: number;
  ready_material_count: number;
  quote_count: number;
  confirmed_quote_count: number;
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
  active_generation_status: "pending" | "processing" | "awaiting_intervention" | null;
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

export type ResourceMaterial = {
  id: string;
  book_id: string;
  material_type: "book_text" | "script" | "subtitle" | "quote_sheet" | "plot_summary";
  file_format: "pdf" | "txt" | "srt" | "vtt" | "ass" | "csv" | "xlsx" | "json";
  file_name: string;
  file_size: number;
  season_number: number | null;
  episode_label: string | null;
  version_label: string | null;
  parse_status: "pending" | "processing" | "needs_review" | "completed" | "failed";
  error_message: string | null;
  segment_count: number;
  quote_count: number;
  source_registry?: Record<string, unknown>[];
  created_at: string;
  updated_at: string;
};

export type PlotEvent = {
  id: string;
  book_id: string;
  material_id: string;
  event_id: string;
  level: string;
  season_number: number | null;
  episode_number: number | null;
  sequence: number | null;
  title: string;
  summary: string;
  cause: string;
  action: string;
  result: string;
  future_impact: string;
  characters: string[];
  relationship_changes: unknown[];
  conflict_tags: string[];
  theme_tags: string[];
  importance: string;
  source_refs: string[];
  confidence: string;
  question_usable: string;
  review_status: "pending" | "confirmed" | "rejected";
  enabled_for_generation: boolean;
  created_at: string;
  updated_at: string;
};

export type PlotEventList = {
  items: PlotEvent[];
  total: number;
  pending_count: number;
  confirmed_count: number;
};

export type QuoteEntry = {
  id: string;
  book_id: string;
  material_id: string;
  material_file_name: string;
  source_segment_ids: string[];
  quote_text: string;
  speaker: string | null;
  speaker_origin: "provided" | "inferred" | "confirmed" | "unknown";
  context: string | null;
  season_number: number | null;
  episode_number: number | null;
  start_ms: number | null;
  end_ms: number | null;
  page_number: number | null;
  review_status: "pending" | "confirmed" | "rejected";
  enabled_for_generation: boolean;
  created_at: string;
  updated_at: string;
};

export type QuoteEntryList = {
  items: QuoteEntry[];
  total: number;
  speakers: string[];
  pending_count: number;
  confirmed_count: number;
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
  generation_theme: GenerationTheme;
  theme_config: QuizThemeConfig;
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
  page_number: number | null;
  excerpt: string;
  highlight?: string | null;
  support: string;
  material_id?: string | null;
  material_type?: string | null;
  season_number?: number | null;
  episode_number?: number | null;
  start_ms?: number | null;
  end_ms?: number | null;
  speaker?: string | null;
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
  question_subtype: QuestionSubtype;
  prompt: string;
  options: QuestionOption[];
  explanation: string | null;
  knowledge_point: string;
  difficulty: string;
  estimated_seconds: number;
  reference_answer: string | null;
  grading_rubric: { point: string; keywords?: string[]; score?: number }[];
  source_evidence: SourceEvidence[];
  quote_entry_ids: string[];
  plot_event_ids: string[];
  source_segment_ids: string[];
  max_score: number;
  correct_answers: string[] | null;
  source_mode?: SourceMode | null;
  question_bank_entry_id?: string | null;
};

export type QuestionBankUsage = {
  id: string;
  entry_id: string;
  quiz_id: string | null;
  question_id: string | null;
  quiz_title: string;
  question_position: number | null;
  used_at: string;
};

export type QuestionBankEntry = {
  id: string;
  book_id: string;
  origin_quiz_id: string | null;
  origin_question_id: string | null;
  question_type: QuestionType;
  question_subtype: string;
  prompt: string;
  options: QuestionOption[];
  correct_answers: string[];
  explanation: string;
  knowledge_point: string;
  difficulty: string;
  estimated_seconds: number;
  reference_answer: string | null;
  grading_rubric: { point: string; keywords?: string[]; score?: number }[];
  source_chunk_ids: string[];
  quote_entry_ids: string[];
  plot_event_ids: string[];
  source_segment_ids: string[];
  fact_key: string | null;
  fact_claim: string | null;
  semantic_signature: Record<string, unknown>;
  source_evidence: SourceEvidence[];
  source_mode: SourceMode | null;
  max_score: number;
  status: "active" | "disabled";
  use_count: number;
  created_at: string;
  updated_at: string;
  usages: QuestionBankUsage[];
};

export type QuestionBankEntryList = {
  items: QuestionBankEntry[];
  total: number;
  unused_count: number;
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
  generation_theme: GenerationTheme;
  theme_config: QuizThemeConfig;
  total_score: number | null;
  max_score: number;
  elapsed_seconds: number | null;
  submitted_at: string | null;
  next_review_date: string | null;
  quality_review_status: "not_started" | "pending" | "processing" | "completed" | "failed";
  quality_review_task_id: string | null;
  quality_review_question_id: string | null;
  quality_review_result: QuizQualityReviewResult | null;
  quality_review_error: string | null;
  quality_review_requested_at: string | null;
  quality_review_completed_at: string | null;
  created_at: string;
  questions: Question[];
};

export type QuizQualityReviewIssue = {
  question_position: number | null;
  severity: "high" | "medium" | "low";
  category: "fact" | "answer" | "source" | "ambiguity" | "duplicate" | "distractor" | "wording" | "difficulty" | "other";
  problem: string;
  suggestion: string;
  evidence: string | null;
  suggested_prompt: string | null;
  suggested_options: { id: string; text: string }[];
  suggested_correct_answers: string[];
  suggested_explanation: string | null;
  suggested_knowledge_point: string | null;
  suggested_reference_answer: string | null;
  suggested_grading_rubric: { point: string; score?: number }[];
};

export type QuizQuestionQualityReview = {
  question_position: number;
  score: number;
  verdict: "pass" | "needs_revision" | "high_risk";
  summary: string;
  strengths: string[];
  issues: QuizQualityReviewIssue[];
};

export type QuizQualityReviewResult = {
  schema_version: string;
  overall_verdict: "pass" | "needs_revision" | "high_risk";
  score: number;
  summary: string;
  strengths: string[];
  issues: QuizQualityReviewIssue[];
  reviewed_question_count: number;
  total_question_count: number;
  reviewed_question_positions: number[];
  question_reviews: QuizQuestionQualityReview[];
  generated_at: string | null;
};

export type QuizQualityReview = {
  status: Quiz["quality_review_status"];
  task_id: string | null;
  question_id: string | null;
  result: QuizQualityReviewResult | null;
  error: string | null;
  requested_at: string | null;
  completed_at: string | null;
};

export type QuizExport = {
  format: string;
  purpose: string;
  quiz: Quiz;
};

export type QuizGenerationTask = {
  id: string;
  book_id: string;
  task_type: string;
  status: "pending" | "processing" | "completed" | "failed" | "awaiting_intervention" | "cancelled";
  source_mode: SourceMode;
  generation_theme: GenerationTheme;
  theme_config: QuizThemeConfig;
  total_questions: number;
  completed_questions: number;
  current_question_position: number | null;
  current_phase: string;
  difficulty: string;
  duration_minutes: number;
  single_count: number;
  multiple_count: number;
  short_count: number;
  use_question_bank: boolean;
  quiz_id: string | null;
  error_message: string | null;
  question_states: QuizGenerationQuestionState[];
  created_at: string;
  updated_at: string;
};

export type QuizGenerationQuestionState = {
  position: number;
  question_type: QuestionType;
  status: "pending" | "generating" | "ready" | "awaiting_intervention" | "confirmed";
  attempts: number;
  source_focus?: "content" | "dialogue" | "integrated" | null;
  error_message: string | null;
  question: Partial<Question> | null;
  updated_at: string | null;
};

export type GenerationPromptMessage = { role: string; content: string };

export type QuizGenerationCall = {
  id: string;
  question_position: number | null;
  phase: string;
  call_number: number;
  model_name: string;
  request_messages: GenerationPromptMessage[];
  model_response: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  status: "success" | "failed";
  error_message: string | null;
  latency_ms: number;
  created_at: string;
};

export type QuizQuestionGenerationTrace = {
  question_id: string;
  position: number;
  prompt: string;
  source_chunk_ids: string[];
  quote_entry_ids: string[];
  calls: QuizGenerationCall[];
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  unreported_calls: number;
};

export type QuizGenerationDebug = {
  quiz_id: string;
  book_id: string;
  quiz_title: string;
  generation_task_id: string | null;
  task_type: string | null;
  task_status: string | null;
  model_name: string | null;
  questions: QuizQuestionGenerationTrace[];
  unassigned_calls: QuizGenerationCall[];
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
};

export type QuizGenerationTaskDebug = {
  task_id: string;
  calls: QuizGenerationCall[];
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
  generation_theme: GenerationTheme;
  theme_config: QuizThemeConfig;
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
  question_subtype: QuestionSubtype;
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
  quote_entry_ids: string[];
  plot_event_ids: string[];
  source_segment_ids: string[];
  source_mode?: SourceMode | null;
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
  generation_theme: GenerationTheme;
  theme_config: QuizThemeConfig;
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
  generation_theme: GenerationTheme;
  theme_config: QuizThemeConfig;
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
  attempts_total?: number;
  attempts_page?: number;
  attempts_page_size?: number;
  graded_count?: number;
  average_points?: number | null;
  median_points?: number | null;
  median_score?: number | null;
  above_threshold_count?: number;
  above_threshold_rate?: number | null;
  score_distribution?: { label: string; min_score: number; max_score: number; count: number; percentage: number }[];
  participation_granularity?: ExamParticipationGranularity;
  participation_year?: number | null;
  participation_month?: number | null;
  participation_periods?: ExamParticipationPeriod[];
};

export type ExamParticipationGranularity = "month" | "year";

export type ExamParticipationPeriod = {
  period_key: string;
  period_label: string;
  participant_count: number;
  completed_count: number;
};

export type ExamShareVersion = {
  version: number;
  is_current: boolean;
  question_count: number;
  single_count: number;
  multiple_count: number;
  short_count: number;
  max_score: number;
  created_at: string;
};

export type ExamShareEdit = {
  id: string;
  share_code: string;
  name: string;
  status: ExamShareStatus;
  quiz_id: string | null;
  book_id: string | null;
  owner_user_id: string;
  owner_username: string;
  owner_display_name: string;
  book_title: string;
  book_author: string;
  quiz_title: string;
  source_mode: SourceMode;
  generation_theme: GenerationTheme;
  theme_config: QuizThemeConfig;
  difficulty: string;
  duration_minutes: number;
  max_score: number;
  snapshot_version: number;
  created_at: string;
  updated_at: string;
  questions: Question[];
  versions: ExamShareVersion[];
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
  generation_theme: GenerationTheme;
  theme_config: QuizThemeConfig;
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
