"use client";

import { ArrowLeft, CheckCircle2, Code2, Eye, FileQuestion } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ErrorState, SourceModeNotice } from "@/components/ui";
import { ApiError, getQuizExport } from "@/lib/api";
import type { Question, Quiz } from "@/lib/types";

const questionTypeLabels: Record<Question["question_type"], string> = {
  single: "单项选择题",
  multiple: "多项选择题",
  short: "问答题",
};

export default function QuizPreviewPage() {
  const params = useParams<{ quizId: string }>();
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getQuizExport(params.quizId)
      .then((payload) => setQuiz(payload.quiz))
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "试卷预览加载失败"))
      .finally(() => setLoading(false));
  }, [params.quizId]);

  if (loading) return <div className="page-wrap"><div className="loading-state">正在打开试卷预览……</div></div>;
  if (!quiz) return <div className="page-wrap"><ErrorState message={error || "未找到这套试卷"} /></div>;

  return (
    <div className="page-wrap">
      <Link className="back-link" href={`/quizzes/${quiz.id}`}><ArrowLeft size={14} />返回试卷概览</Link>
      {error && <div className="toast-error">{error}</div>}
      <SourceModeNotice sourceMode={quiz.source_mode} />
      <header className="page-header quiz-preview-header">
        <div><div className="eyebrow"><Eye size={13} />Quiz preview</div><h1 className="page-title">{quiz.title}</h1><p className="page-description">快速查看整套试卷的题目、答案和解析，不会创建复习记录。</p></div>
        <div className="quiz-overview-actions"><Link className="button button-secondary" href={`/quizzes/${quiz.id}/generation-debug`}><Code2 size={15} />查看出题过程</Link><Link className="button button-secondary" href={`/quizzes/${quiz.id}`}><ArrowLeft size={15} />返回概览</Link></div>
      </header>

      <div className="quiz-preview-summary"><FileQuestion size={16} /><strong>{quiz.questions.length} 道题</strong><span>{quiz.max_score} 分 · {quiz.duration_minutes} 分钟</span></div>
      <section className="quiz-preview-list">
        {quiz.questions.map((question) => <PreviewQuestion key={question.id} question={question} />)}
      </section>
    </div>
  );
}

function PreviewQuestion({ question }: { question: Question }) {
  const correctAnswers = new Set(question.correct_answers || []);
  return <article className="quiz-preview-question"><header className="quiz-preview-question-header"><div><span className="question-number">第 {question.position} 题</span><span className="question-type">{questionTypeLabels[question.question_type]}</span></div><strong>{question.max_score} 分</strong></header><h2>{question.prompt}</h2>{question.options.length > 0 && <ol className="quiz-preview-options">{question.options.map((option) => <li className={correctAnswers.has(option.id) ? "correct" : ""} key={option.id}><span>{option.id}</span>{option.text}{correctAnswers.has(option.id) && <CheckCircle2 size={14} />}</li>)}</ol>}<div className="quiz-preview-answer"><strong>正确答案</strong><span>{question.question_type === "short" ? "见下方参考答案" : (question.correct_answers || []).join("、") || "未设置"}</span></div>{question.explanation && <div className="quiz-preview-field"><strong>解析</strong><p>{question.explanation}</p></div>}<div className="quiz-preview-field"><strong>知识点</strong><p>{question.knowledge_point || "未设置"}</p></div>{question.reference_answer && <div className="quiz-preview-field"><strong>参考答案</strong><p>{question.reference_answer}</p></div>}{question.grading_rubric.length > 0 && <div className="quiz-preview-field"><strong>评分要点</strong><ul>{question.grading_rubric.map((item, index) => <li key={index}>{item.point}{item.score !== undefined ? `（${item.score} 分）` : ""}</li>)}</ul></div>}{question.source_evidence.length > 0 && <details className="quiz-preview-sources"><summary>查看来源依据（{question.source_evidence.length} 条）</summary>{question.source_evidence.map((source, index) => <div key={`${source.chunk_id || source.material_id || "source"}-${index}`}><span>{source.speaker || source.file_name || "可信来源"}</span><p>{source.excerpt}</p></div>)}</details>}</article>;
}
