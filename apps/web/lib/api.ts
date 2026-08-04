import type {
  BookDetail,
  BookSummary,
  Chunk,
  ModelConfiguration,
  ModelConnectionTestResult,
  ModelProviderMode,
  PdfDocument,
  PreGenerationResponse,
  PromptPreview,
  PromptTemplate,
  PromptType,
  Quiz,
  QuizGenerationTask,
  QuizSummary,
  QuizResult,
  ReadingStatus,
  ShelfStatus,
  ReviewTask,
  ReviewTaskSummary,
  TokenUsageReport,
  CurrentUser,
  AdminUser,
  AdminUserCreateResult,
  PasswordResetResult,
  AdminBookCopyResult,
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
      if (typeof detail.detail === "string") message = detail.detail;
      else if (detail.detail && typeof detail.detail.message === "string") message = detail.detail.message;
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

export function getQuiz(quizId: string) {
  return apiFetch<Quiz>(`/quizzes/${quizId}`);
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

export function getCurrentUser() {
  return apiFetch<CurrentUser>("/auth/me");
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
