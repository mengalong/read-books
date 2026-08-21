"use client";

import { ArrowLeft, Clock3, FileQuestion } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ErrorState, SourceModeNotice } from "@/components/ui";
import { QuizQuestionEditList } from "@/components/quiz-question-edit-list";
import { ApiError, getEditableQuiz, regenerateQuizQuestion, updateQuizQuestion } from "@/lib/api";
import type { Question, Quiz } from "@/lib/types";

const questionTypeLabels: Record<Question["question_type"], string> = {
  single: "单项选择题",
  multiple: "多项选择题",
  short: "问答题",
};

export default function QuizEditPage() {
  const params = useParams<{ quizId: string }>();
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getEditableQuiz(params.quizId)
      .then(setQuiz)
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "试卷加载失败"))
      .finally(() => setLoading(false));
  }, [params.quizId]);

  const counts = useMemo(() => {
    if (!quiz) return [];
    return (["single", "multiple", "short"] as const)
      .map((type) => ({ type, count: quiz.questions.filter((question) => question.question_type === type).length }))
      .filter((item) => item.count > 0);
  }, [quiz]);

  function handleQuestionSaved(updatedQuestion: Question) {
    setQuiz((current) => {
      if (!current) return current;
      return {
        ...current,
        questions: current.questions.map((question) =>
          question.id === updatedQuestion.id ? updatedQuestion : question,
        ),
      };
    });
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在打开试卷编辑器……</div></div>;
  if (!quiz) return <div className="page-wrap"><ErrorState message={error || "未找到这套试卷"} /></div>;

  return (
    <div className="page-wrap">
      <Link className="back-link" href={`/books/${quiz.book_id}`}><ArrowLeft size={14} />返回《{quiz.book_title}》</Link>
      {error && <div className="toast-error">{error}</div>}
      <SourceModeNotice sourceMode={quiz.source_mode} />
      <header className="page-header">
        <div>
          <div className="eyebrow">Quiz editor</div>
          <h1 className="page-title">{quiz.title}</h1>
          <p className="page-description">这里用于调整试卷题目内容，不会进入答题流程。</p>
        </div>
        <div className="quiz-editor-summary">
          <div><Clock3 size={16} />{quiz.duration_minutes} 分钟</div>
          <div><FileQuestion size={16} />{quiz.questions.length} 道题</div>
        </div>
      </header>

      <div className="quiz-choice-layout">
        <section className="content-panel">
          <div className="section-title"><h2>题型概览</h2><span>逐题修改题干、选项和标准答案</span></div>
          <div className="quiz-choice-items">
            {counts.map(({ type, count }) => <div className="quiz-choice-item" key={type}><div className="count-icon"><FileQuestion size={17} /></div><div><strong>{questionTypeLabels[type]}</strong><span>{count} 道</span></div></div>)}
          </div>
        </section>
        <aside className="quiz-settings-summary">
          <div className="eyebrow">编辑模式</div>
          <strong>{quiz.questions.length} 道题</strong>
          <p>每道题都可以单独保存，保存后立即生效。</p>
          <dl><div><dt>难度</dt><dd>{quiz.difficulty === "easy" ? "基础" : quiz.difficulty === "hard" ? "深入" : "适中"}</dd></div><div><dt>来源</dt><dd>{quiz.source_mode === "model_knowledge" ? "模型知识" : "PDF 原文"}</dd></div><div><dt>状态</dt><dd>{quiz.status === "ready" ? "可复习" : "已提交"}</dd></div></dl>
        </aside>
      </div>

      <section className="content-panel quiz-question-edit-panel">
        <div className="section-title"><h2>题目编辑</h2><span>直接修改每道题的题干、选项和标准答案</span></div>
        <QuizQuestionEditList
          onRegenerateQuestion={(questionId) => regenerateQuizQuestion(quiz.id, questionId)}
          onSaved={handleQuestionSaved}
          onUpdateQuestion={(questionId, payload) => updateQuizQuestion(quiz.id, questionId, payload)}
          questions={quiz.questions}
        />
      </section>
    </div>
  );
}
