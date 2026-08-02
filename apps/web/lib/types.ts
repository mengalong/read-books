export type ReadingStatus = "reading" | "finished" | "reviewing";
export type QuestionType = "single" | "multiple" | "short";

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
  title: string;
  author: string;
  description: string;
  cover_color: string;
  language: string;
  reading_status: ReadingStatus;
  tags: string[];
  created_at: string;
  updated_at: string;
  stats: BookStats;
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

export type BookDetail = BookSummary & { pdfs: PdfDocument[] };

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
  support: string;
};

export type QuestionOption = { id: string; text: string };

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
  total_score: number | null;
  max_score: number;
  elapsed_seconds: number | null;
  submitted_at: string | null;
  next_review_date: string | null;
  created_at: string;
  questions: Question[];
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

export type HistoryItem = {
  id: string;
  title: string;
  difficulty: string;
  status: string;
  total_score: number | null;
  max_score: number;
  duration_minutes: number;
  elapsed_seconds: number | null;
  question_count: number;
  created_at: string;
  submitted_at: string | null;
  next_review_date: string | null;
};
