import type {
  BookDetail,
  BookSummary,
  Chunk,
  HistoryItem,
  PdfDocument,
  Quiz,
  QuizResult,
  ReadingStatus,
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
      message = detail.detail || message;
    } catch {
      // Keep the HTTP status message when the server did not return JSON.
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function getBooks(search = "", status?: ReadingStatus) {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (status) params.set("status", status);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<BookSummary[]>(`/books${suffix}`);
}

export function getBook(bookId: string) {
  return apiFetch<BookDetail>(`/books/${bookId}`);
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

export function uploadPdf(bookId: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch<PdfDocument>(`/books/${bookId}/pdfs`, { method: "POST", body: formData });
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
  return apiFetch<Quiz>(`/books/${bookId}/quizzes`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
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

export function getQuizResult(quizId: string) {
  return apiFetch<QuizResult>(`/quizzes/${quizId}/result`);
}

export function getHistory(bookId: string) {
  return apiFetch<HistoryItem[]>(`/books/${bookId}/history`);
}
