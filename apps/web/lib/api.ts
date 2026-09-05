import type {
  BookDetail,
  BookSummary,
  Chunk,
  ModelConfiguration,
  ModelConnectionTestResult,
  ModelProviderMode,
  PdfDocument,
  QuoteEntry,
  QuoteEntryList,
  PreGenerationResponse,
  PromptPreview,
  PromptTemplate,
  PromptType,
  PlotEvent,
  PlotEventList,
  Quiz,
  QuizExport,
  QuizQualityReview,
  QuizGenerationTask,
  QuizGenerationDebug,
  QuizGenerationTaskDebug,
  QuizSummary,
  QuizResult,
  QuestionUpdatePayload,
  ReadingStatus,
  ResourceType,
  ResourceMaterial,
  GenerationTheme,
  QuizThemeConfig,
  ShelfStatus,
  ReviewTask,
  ReviewTaskSummary,
  TokenUsageReport,
  CurrentUser,
  AdminUser,
  AdminUserCreateResult,
  PasswordResetResult,
  AdminBookCopyResult,
  AccessGranularity,
  AccessStatisticsReport,
  ExamAttempt,
  ExamShareEdit,
  ExamShare,
  ExamShareStatus,
  PublicExam,
  SiteFooterConfiguration,
  WechatIdentityResponse,
  WechatLoginConfiguration,
} from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

function extractErrorMessage(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== "object") return null;
        const message = (item as { msg?: unknown }).msg;
        return typeof message === "string" ? message : null;
      })
      .filter((message): message is string => Boolean(message));
    if (messages.length) return messages.join("；");
  }
  return null;
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      credentials: "include",
      headers: {
        ...(options?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...options?.headers,
      },
    });
  } catch {
    throw new ApiError("无法连接后端服务，请确认 FastAPI 已启动。", 0);
  }

  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const detail = await response.json();
      message = extractErrorMessage(detail) || message;
    } catch {
      // Keep the HTTP status message when the server did not return JSON.
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function getBooks(search = "", status?: ReadingStatus, shelfStatus: ShelfStatus = "active") {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (status) params.set("status", status);
  params.set("shelf_status", shelfStatus);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<BookSummary[]>(`/books${suffix}`);
}

export function getAdminBooks(search = "", ownerId?: string, shelfStatus?: ShelfStatus) {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (ownerId) params.set("owner_id", ownerId);
  if (shelfStatus) params.set("shelf_status", shelfStatus);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<BookSummary[]>(`/admin/books${suffix}`);
}

export function getAdminBook(bookId: string) {
  return apiFetch<BookDetail>(`/admin/books/${bookId}`);
}

export function getAdminBookChunks(bookId: string, pageSize = 8) {
  return apiFetch<Chunk[]>(`/admin/books/${bookId}/chunks?page_size=${pageSize}`);
}

export function copyAdminBook(
  bookId: string,
  payload: { target_user_id: string; copy_pdf: boolean; copy_content: boolean },
) {
  return apiFetch<AdminBookCopyResult>(`/admin/books/${bookId}/copy`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function unlistAdminBook(bookId: string) {
  return apiFetch<BookDetail>(`/admin/books/${bookId}/unlist`, { method: "POST" });
}

export function restoreAdminBook(bookId: string) {
  return apiFetch<BookDetail>(`/admin/books/${bookId}/restore`, { method: "POST" });
}

export function deleteAdminBook(bookId: string) {
  return apiFetch<void>(`/admin/books/${bookId}`, { method: "DELETE" });
}

export function getBook(bookId: string) {
  return apiFetch<BookDetail>(`/books/${bookId}`);
}

export function unlistBook(bookId: string) {
  return apiFetch<BookDetail>(`/books/${bookId}/unlist`, { method: "POST" });
}

export function restoreBook(bookId: string) {
  return apiFetch<BookDetail>(`/books/${bookId}/restore`, { method: "POST" });
}

export function deleteBook(bookId: string) {
  return apiFetch<void>(`/books/${bookId}`, { method: "DELETE" });
}

export function createBook(payload: {
  resource_type: ResourceType;
  title: string;
  author: string;
  description: string;
  cover_color: string;
  language: string;
  reading_status: ReadingStatus;
  tags: string[];
}) {
  return apiFetch<BookDetail>("/books", { method: "POST", body: JSON.stringify(payload) });
}

export function updateBook(
  bookId: string,
  payload: {
    resource_type: ResourceType;
    title: string;
    author: string;
    description: string;
    cover_color: string;
    language: string;
    reading_status: ReadingStatus;
    tags: string[];
  },
) {
  return apiFetch<BookDetail>(`/books/${bookId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function uploadPdf(bookId: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch<PdfDocument>(`/books/${bookId}/pdfs`, { method: "POST", body: formData });
}

export function getMaterials(bookId: string) {
  return apiFetch<ResourceMaterial[]>(`/books/${bookId}/materials`);
}

export function getPlotEvents(
  bookId: string,
  params: { materialId?: string; episodeNumber?: number; reviewStatus?: string; search?: string; page?: number; pageSize?: number } = {},
) {
  const query = new URLSearchParams();
  if (params.materialId) query.set("material_id", params.materialId);
  if (params.episodeNumber) query.set("episode_number", String(params.episodeNumber));
  if (params.reviewStatus) query.set("review_status", params.reviewStatus);
  if (params.search) query.set("search", params.search);
  if (params.page) query.set("page", String(params.page));
  if (params.pageSize) query.set("page_size", String(params.pageSize));
  return apiFetch<PlotEventList>(`/books/${bookId}/plot-events${query.toString() ? `?${query}` : ""}`);
}

export function updatePlotEvent(
  bookId: string,
  eventId: string,
  payload: Partial<Pick<PlotEvent, "title" | "summary" | "cause" | "action" | "result" | "future_impact" | "review_status" | "enabled_for_generation">>,
) {
  return apiFetch<PlotEvent>(`/books/${bookId}/plot-events/${eventId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function uploadMaterial(
  bookId: string,
  file: File,
  payload: {
    material_type: ResourceMaterial["material_type"];
    season_number?: number;
    episode_label?: string;
    version_label?: string;
  },
) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("material_type", payload.material_type);
  if (payload.season_number) formData.append("season_number", String(payload.season_number));
  if (payload.episode_label) formData.append("episode_label", payload.episode_label);
  if (payload.version_label) formData.append("version_label", payload.version_label);
  return apiFetch<ResourceMaterial>(`/books/${bookId}/materials`, {
    method: "POST",
    body: formData,
  });
}

export function reparseMaterial(bookId: string, materialId: string) {
  return apiFetch<ResourceMaterial>(`/books/${bookId}/materials/${materialId}/reparse`, {
    method: "POST",
  });
}

export function deleteMaterial(bookId: string, materialId: string) {
  return apiFetch<void>(`/books/${bookId}/materials/${materialId}`, { method: "DELETE" });
}

export function getQuotes(
  bookId: string,
  filters: {
    material_id?: string;
    speaker?: string;
    review_status?: QuoteEntry["review_status"];
    search?: string;
    page?: number;
    page_size?: number;
  } = {},
) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  const suffix = params.size ? `?${params.toString()}` : "";
  return apiFetch<QuoteEntryList>(`/books/${bookId}/quotes${suffix}`);
}

export function updateQuote(
  bookId: string,
  quoteId: string,
  payload: {
    speaker?: string | null;
    context?: string | null;
    review_status?: QuoteEntry["review_status"];
    enabled_for_generation?: boolean;
  },
) {
  return apiFetch<QuoteEntry>(`/books/${bookId}/quotes/${quoteId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function bulkReviewQuotes(
  bookId: string,
  quoteIds: string[],
  action: "confirm" | "reject",
) {
  return apiFetch<QuoteEntry[]>(`/books/${bookId}/quotes/bulk-${action}`, {
    method: "POST",
    body: JSON.stringify({ quote_ids: quoteIds }),
  });
}

export function getQuoteSheetTemplateUrl() {
  return `${API_BASE}/material-templates/quote-sheet.csv`;
}

export function startPreGeneration(bookId: string) {
  return apiFetch<PreGenerationResponse>(`/books/${bookId}/pre-generation`, {
    method: "POST",
  });
}

export function deletePdf(bookId: string, pdfId: string) {
  return apiFetch<void>(`/books/${bookId}/pdfs/${pdfId}`, { method: "DELETE" });
}

export function getChunks(bookId: string, pageSize = 8) {
  return apiFetch<Chunk[]>(`/books/${bookId}/chunks?page_size=${pageSize}`);
}

export function generateQuiz(
  bookId: string,
  payload: {
    duration_minutes: number;
    difficulty: string;
    single_count: number;
    multiple_count: number;
    short_count: number;
    page_start?: number;
    page_end?: number;
    generation_theme?: GenerationTheme;
    theme_config?: QuizThemeConfig;
  },
) {
  return apiFetch<QuizGenerationTask>(`/books/${bookId}/quizzes`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getGenerationTask(taskId: string) {
  return apiFetch<QuizGenerationTask>(`/quiz-generation-tasks/${taskId}`);
}

export function cancelGenerationTask(taskId: string) {
  return apiFetch<QuizGenerationTask>(`/quiz-generation-tasks/${taskId}/cancel`, {
    method: "POST",
  });
}

export function deleteGenerationTask(taskId: string) {
  return apiFetch<void>(`/quiz-generation-tasks/${taskId}`, { method: "DELETE" });
}

export function interveneGenerationTask(
  taskId: string,
  position: number,
  payload: { action: "retry" | "accept" | "replace" | "edit"; question?: Record<string, unknown> },
) {
  return apiFetch<QuizGenerationTask>(
    `/quiz-generation-tasks/${taskId}/questions/${position}/intervene`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export function getQuizGenerationDebug(quizId: string) {
  return apiFetch<QuizGenerationDebug>(`/quizzes/${quizId}/generation-debug`);
}

export function getGenerationTaskDebug(taskId: string) {
  return apiFetch<QuizGenerationTaskDebug>(`/quiz-generation-tasks/${taskId}/debug`);
}

export function getQuiz(quizId: string) {
  return apiFetch<Quiz>(`/quizzes/${quizId}`);
}

export function getQuizExport(quizId: string) {
  return apiFetch<QuizExport>(`/quizzes/${quizId}/export`);
}

export function requestQuizQualityReview(quizId: string) {
  return apiFetch<QuizQualityReview>(`/quizzes/${quizId}/quality-review`, { method: "POST" });
}

export function getQuizQualityReview(quizId: string) {
  return apiFetch<QuizQualityReview>(`/quizzes/${quizId}/quality-review`);
}

export function requestQuizQuestionQualityReview(quizId: string, questionId: string) {
  return apiFetch<QuizQualityReview>(
    `/quizzes/${quizId}/questions/${questionId}/quality-review`,
    { method: "POST" },
  );
}

export function getEditableQuiz(quizId: string) {
  return apiFetch<Quiz>(`/quizzes/${quizId}/editable`);
}

export function updateQuizQuestion(
  quizId: string,
  questionId: string,
  payload: QuestionUpdatePayload,
) {
  return apiFetch<Quiz["questions"][number]>(`/quizzes/${quizId}/questions/${questionId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function regenerateQuizQuestion(quizId: string, questionId: string) {
  return apiFetch<Quiz["questions"][number]>(
    `/quizzes/${quizId}/questions/${questionId}/regenerate`,
    {
      method: "POST",
    },
  );
}

export function submitQuiz(
  quizId: string,
  payload: {
    elapsed_seconds: number;
    answers: { question_id: string; selected_answers: string[]; text_answer?: string }[];
  },
) {
  return apiFetch<QuizResult>(`/quizzes/${quizId}/submit`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getBookQuizzes(bookId: string) {
  return apiFetch<QuizSummary[]>(`/books/${bookId}/quizzes`);
}

export function deleteQuiz(quizId: string) {
  return apiFetch<void>(`/quizzes/${quizId}`, { method: "DELETE" });
}

export function createExamShare(quizId: string, payload: { name?: string; expires_at?: string | null }) {
  return apiFetch<ExamShare>(`/quizzes/${quizId}/exam-shares`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getExamShares(filters: { search?: string; status?: ExamShareStatus; createdFrom?: string; createdTo?: string } = {}) {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.status) params.set("status", filters.status);
  if (filters.createdFrom) params.set("created_from", filters.createdFrom);
  if (filters.createdTo) params.set("created_to", filters.createdTo);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<ExamShare[]>(`/exam-shares${suffix}`);
}

export function getExamShare(
  shareId: string,
  options: { page?: number; pageSize?: number; status?: string; sort?: "latest" | "score_desc" | "score_asc"; search?: string; participationGranularity?: "month" | "year"; participationYear?: number; participationMonth?: number } = {},
) {
  const params = new URLSearchParams();
  if (options.page) params.set("attempt_page", String(options.page));
  if (options.pageSize) params.set("attempt_page_size", String(options.pageSize));
  if (options.status) params.set("attempt_status", options.status);
  if (options.sort) params.set("attempt_sort", options.sort);
  if (options.search) params.set("attempt_search", options.search);
  if (options.participationGranularity) params.set("participation_granularity", options.participationGranularity);
  if (options.participationYear) params.set("participation_year", String(options.participationYear));
  if (options.participationMonth) params.set("participation_month", String(options.participationMonth));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<ExamShare>(`/exam-shares/${shareId}${suffix}`);
}

export function getEditableExamShare(shareId: string) {
  return apiFetch<ExamShareEdit>(`/exam-shares/${shareId}/editable`);
}

export function updateExamShare(shareId: string, payload: { name?: string; status?: "active" | "stopped"; expires_at?: string | null }) {
  return apiFetch<ExamShare>(`/exam-shares/${shareId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function updateExamShareQuestion(
  shareId: string,
  questionId: string,
  payload: QuestionUpdatePayload,
) {
  return apiFetch<ExamShareEdit["questions"][number]>(
    `/exam-shares/${shareId}/questions/${questionId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function regenerateExamShareQuestion(shareId: string, questionId: string) {
  return apiFetch<ExamShareEdit["questions"][number]>(
    `/exam-shares/${shareId}/questions/${questionId}/regenerate`,
    {
      method: "POST",
    },
  );
}

export function deleteExamShareVersion(shareId: string, version: number) {
  return apiFetch<void>(`/exam-shares/${shareId}/versions/${version}`, { method: "DELETE" });
}

export function getExamAttemptForOwner(shareId: string, attemptId: string) {
  return apiFetch<ExamAttempt>(`/exam-shares/${shareId}/attempts/${attemptId}`);
}

export function retryExamAttemptGrading(shareId: string, attemptId: string) {
  return apiFetch<ExamAttempt>(`/exam-shares/${shareId}/attempts/${attemptId}/retry-grading`, {
    method: "POST",
  });
}

export function getAdminExamShares(filters: { search?: string; ownerId?: string; status?: ExamShareStatus; createdFrom?: string; createdTo?: string } = {}) {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.ownerId) params.set("owner_id", filters.ownerId);
  if (filters.status) params.set("status", filters.status);
  if (filters.createdFrom) params.set("created_from", filters.createdFrom);
  if (filters.createdTo) params.set("created_to", filters.createdTo);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<ExamShare[]>(`/admin/exam-shares${suffix}`);
}

export function getAdminExamShare(
  shareId: string,
  options: { page?: number; pageSize?: number; status?: string; sort?: "latest" | "score_desc" | "score_asc"; search?: string; participationGranularity?: "month" | "year"; participationYear?: number; participationMonth?: number } = {},
) {
  const params = new URLSearchParams();
  if (options.page) params.set("attempt_page", String(options.page));
  if (options.pageSize) params.set("attempt_page_size", String(options.pageSize));
  if (options.status) params.set("attempt_status", options.status);
  if (options.sort) params.set("attempt_sort", options.sort);
  if (options.search) params.set("attempt_search", options.search);
  if (options.participationGranularity) params.set("participation_granularity", options.participationGranularity);
  if (options.participationYear) params.set("participation_year", String(options.participationYear));
  if (options.participationMonth) params.set("participation_month", String(options.participationMonth));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<ExamShare>(`/admin/exam-shares/${shareId}${suffix}`);
}

export function getAdminExamAttempt(shareId: string, attemptId: string) {
  return apiFetch<ExamAttempt>(`/admin/exam-shares/${shareId}/attempts/${attemptId}`);
}

export function retryAdminExamAttemptGrading(shareId: string, attemptId: string) {
  return apiFetch<ExamAttempt>(`/admin/exam-shares/${shareId}/attempts/${attemptId}/retry-grading`, {
    method: "POST",
  });
}

export function getPublicExam(shareCode: string, attemptToken?: string | null) {
  return apiFetch<PublicExam>(`/public/exams/${shareCode}`, {
    headers: attemptHeaders(attemptToken),
  });
}

export function startPublicExam(shareCode: string, participantName?: string) {
  return apiFetch<ExamAttempt>(`/public/exams/${shareCode}/attempts`, {
    method: "POST",
    body: JSON.stringify({ ...(participantName ? { participant_name: participantName } : {}) }),
  });
}

function attemptHeaders(token?: string | null): HeadersInit | undefined {
  return token ? { "X-Exam-Attempt-Token": token } : undefined;
}

export function getPublicExamAttempt(attemptId: string, token?: string | null) {
  return apiFetch<ExamAttempt>(`/public/exam-attempts/${attemptId}`, {
    headers: attemptHeaders(token),
  });
}

export function submitPublicExamAttempt(
  attemptId: string,
  payload: {
    elapsed_seconds: number;
    answers: { question_id: string; selected_answers: string[]; text_answer?: string }[];
  },
  token?: string | null,
) {
  return apiFetch<ExamAttempt>(`/public/exam-attempts/${attemptId}/submit`, {
    method: "POST",
    headers: attemptHeaders(token),
    body: JSON.stringify(payload),
  });
}

export function getPublicExamResult(attemptId: string, token?: string | null) {
  return apiFetch<ExamAttempt>(`/public/exam-attempts/${attemptId}/result`, {
    headers: attemptHeaders(token),
  });
}

export function getWechatLoginUrl(shareCode: string) {
  return `${API_BASE}/public/wechat/login?${new URLSearchParams({ share_code: shareCode })}`;
}

export function getWechatDiagnosticLoginUrl() {
  return `${API_BASE}/public/wechat/diagnostic/login`;
}

export function getWechatIdentity() {
  return apiFetch<WechatIdentityResponse>("/public/wechat/me");
}

export function logoutWechat() {
  return apiFetch<void>("/public/wechat/logout", { method: "POST" });
}

export function startReview(quizId: string) {
  return apiFetch<ReviewTask>(`/quizzes/${quizId}/reviews`, { method: "POST" });
}

export function getReview(reviewId: string) {
  return apiFetch<ReviewTask>(`/reviews/${reviewId}`);
}

export function submitReview(
  reviewId: string,
  payload: {
    elapsed_seconds: number;
    answers: { question_id: string; selected_answers: string[]; text_answer?: string }[];
  },
) {
  return apiFetch<ReviewTask>(`/reviews/${reviewId}/submit`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getReviewResult(reviewId: string) {
  return apiFetch<ReviewTask>(`/reviews/${reviewId}/result`);
}

export function getReviewHistory(filters: { bookId?: string; search?: string; ownerId?: string; status?: "in_progress" | "submitted" } = {}) {
  const params = new URLSearchParams();
  if (filters.bookId) params.set("book_id", filters.bookId);
  if (filters.search) params.set("search", filters.search);
  if (filters.ownerId) params.set("owner_id", filters.ownerId);
  if (filters.status) params.set("status", filters.status);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<ReviewTaskSummary[]>(`/reviews${suffix}`);
}

export function reopenReview(reviewId: string) {
  return apiFetch<ReviewTask>(`/reviews/${reviewId}/reopen`, { method: "POST" });
}

export function deleteReview(reviewId: string) {
  return apiFetch<void>(`/reviews/${reviewId}`, { method: "DELETE" });
}

export function getQuizResult(quizId: string) {
  return apiFetch<QuizResult>(`/quizzes/${quizId}/result`);
}

export function getHistory(bookId: string) {
  return apiFetch<ReviewTaskSummary[]>(`/books/${bookId}/history`);
}

export function getModelConfiguration() {
  return apiFetch<ModelConfiguration>("/settings/model");
}

export function getWechatLoginConfiguration() {
  return apiFetch<WechatLoginConfiguration>("/settings/wechat-login");
}

export function getSiteFooterConfiguration() {
  return apiFetch<SiteFooterConfiguration>("/site-footer");
}

export function updateWechatLoginConfiguration(payload: {
  enabled: boolean;
  required_for_public_exams: boolean;
  app_id: string;
  app_secret?: string;
  callback_base_url: string;
}) {
  return apiFetch<WechatLoginConfiguration>("/settings/wechat-login", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function updateSiteFooterConfiguration(payload: {
  record_number: string;
  record_url: string;
}) {
  return apiFetch<SiteFooterConfiguration>("/site-footer", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function updateModelConfiguration(payload: {
  provider_mode: ModelProviderMode;
  base_url: string;
  model_name: string;
  api_key?: string;
  clear_api_key: boolean;
  timeout_ms: number;
  temperature: number;
}) {
  return apiFetch<ModelConfiguration>("/settings/model", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function testModelConnection(payload: {
  base_url: string;
  model_name: string;
  api_key?: string;
  clear_api_key: boolean;
  timeout_ms: number;
}) {
  return apiFetch<ModelConnectionTestResult>("/settings/model/test", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getPromptTemplates() {
  return apiFetch<PromptTemplate[]>("/settings/prompts");
}

export function getPromptHistory(promptType: PromptType) {
  return apiFetch<PromptTemplate[]>(`/settings/prompts/${promptType}/history`);
}

export function updatePromptTemplate(
  promptType: PromptType,
  payload: { system_prompt: string; user_prompt: string },
) {
  return apiFetch<PromptTemplate>(`/settings/prompts/${promptType}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function resetPromptTemplate(promptType: PromptType) {
  return apiFetch<PromptTemplate>(`/settings/prompts/${promptType}/reset`, {
    method: "POST",
  });
}

export function previewPrompt(
  promptType: PromptType,
  payload: { system_prompt: string; user_prompt: string },
) {
  return apiFetch<PromptPreview>(`/settings/prompts/${promptType}/preview`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getTokenUsage(taskType?: string, userId?: string) {
  const params = new URLSearchParams();
  if (taskType) params.set("task_type", taskType);
  if (userId) params.set("user_id", userId);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<TokenUsageReport>(`/settings/token-usage${suffix}`);
}

export function getAccessStatistics(filters: {
  granularity: AccessGranularity;
  startDate?: string;
  endDate?: string;
  userId?: string;
}) {
  const params = new URLSearchParams({ granularity: filters.granularity });
  if (filters.startDate) params.set("start_date", filters.startDate);
  if (filters.endDate) params.set("end_date", filters.endDate);
  if (filters.userId) params.set("user_id", filters.userId);
  return apiFetch<AccessStatisticsReport>(`/settings/access-statistics?${params.toString()}`);
}

export function getCurrentUser() {
  return apiFetch<CurrentUser>("/auth/me");
}

export function recordActivity() {
  return apiFetch<void>("/auth/activity", { method: "POST" });
}

export function login(username: string, password: string) {
  return apiFetch<CurrentUser>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function logout() {
  return apiFetch<void>("/auth/logout", { method: "POST" });
}

export function changePassword(currentPassword: string, newPassword: string) {
  return apiFetch<CurrentUser>("/auth/change-password", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

export function getAdminUsers() {
  return apiFetch<AdminUser[]>("/admin/users");
}

export function createAdminUser(payload: {
  username: string;
  display_name: string;
  role: "admin" | "user";
  temporary_password?: string;
}) {
  return apiFetch<AdminUserCreateResult>("/admin/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAdminUser(
  userId: string,
  payload: { display_name?: string; role?: "admin" | "user"; status?: "active" | "disabled" },
) {
  return apiFetch<AdminUser>(`/admin/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function resetAdminUserPassword(userId: string) {
  return apiFetch<PasswordResetResult>(`/admin/users/${userId}/reset-password`, {
    method: "POST",
  });
}
