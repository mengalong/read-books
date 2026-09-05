"use client";

import { AlertCircle, ArrowLeft, Clock3, Code2, FileQuestion } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ErrorState, SourceModeNotice } from "@/components/ui";
import { QuizQuestionEditList } from "@/components/quiz-question-edit-list";
import { ApiError, getEditableQuiz, getQuizQualityReview, promoteQuestionToBank, regenerateQuizQuestion, requestQuizQuestionQualityReview, updateQuizQuestion } from "@/lib/api";
import type { Question, Quiz, QuizQualityReview } from "@/lib/types";

const questionTypeLabels: Record<Question["question_type"], string> = {
  single: "单项选择题",
  multiple: "多项选择题",
  short: "问答题",
};

export default function QuizEditPage() {
  const params = useParams<{ quizId: string }>();
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [dirtyQuestionIds, setDirtyQuestionIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getEditableQuiz(params.quizId)
      .then(setQuiz)
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "试卷加载失败"))
      .finally(() => setLoading(false));
  }, [params.quizId]);

  useEffect(() => {
    if (!quiz || !["pending", "processing"].includes(quiz.quality_review_status)) return;
    const timer = window.setInterval(() => {
      getQuizQualityReview(params.quizId)
        .then((review) => applyQualityReview(review))
        .catch(() => undefined);
    }, 2200);
    return () => window.clearInterval(timer);
  }, [params.quizId, quiz?.quality_review_status]);

  useEffect(() => {
    if (dirtyQuestionIds.size === 0) return;
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [dirtyQuestionIds.size]);

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

  const handleDirtyChange = useCallback((questionId: string, dirty: boolean) => {
    setDirtyQuestionIds((current) => {
      const next = new Set(current);
      if (dirty) next.add(questionId);
      else next.delete(questionId);
      return next;
    });
  }, []);

  function applyQualityReview(review: QuizQualityReview) {
    setQuiz((current) => current ? {
      ...current,
      quality_review_status: review.status,
      quality_review_task_id: review.task_id,
      quality_review_question_id: review.question_id,
      quality_review_result: review.result,
      quality_review_error: review.error,
      quality_review_requested_at: review.requested_at,
      quality_review_completed_at: review.completed_at,
    } : current);
  }

  async function handleQuestionReview(questionId: string): Promise<QuizQualityReview> {
    const initial = await requestQuizQuestionQualityReview(params.quizId, questionId);
    applyQualityReview(initial);
    if (!["pending", "processing"].includes(initial.status)) {
      if (initial.status === "failed") throw new Error(initial.error || "本题审查失败");
      return initial;
    }
    let latest = initial;
    for (let attempt = 0; attempt < 90; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 2200));
      latest = await getQuizQualityReview(params.quizId);
      applyQualityReview(latest);
      if (!["pending", "processing"].includes(latest.status)) break;
    }
    if (latest.status === "failed") throw new Error(latest.error || "本题审查失败");
    return latest;
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在打开试卷编辑器……</div></div>;
  if (!quiz) return <div className="page-wrap"><ErrorState message={error || "未找到这套试卷"} /></div>;

  return (
    <div className="page-wrap">
      <Link className="back-link" href={`/books/${quiz.book_id}`} onClick={(event) => { if (dirtyQuestionIds.size > 0 && !window.confirm("还有题目未保存，确定离开吗？未保存内容会丢失。")) event.preventDefault(); }}><ArrowLeft size={14} />返回《{quiz.book_title}》</Link>
      {error && <div className="toast-error">{error}</div>}
      {dirtyQuestionIds.size > 0 && <div className="question-edit-unsaved-banner"><AlertCircle size={17} /><div><strong>有未保存修改</strong><span>{dirtyQuestionIds.size} 道题已发生变化，请逐题点击“保存本题”。离开页面时系统会再次提醒。</span></div></div>}
      <SourceModeNotice sourceMode={quiz.source_mode} />
      <header className="page-header">
        <div>
          <div className="eyebrow">Quiz editor</div>
          <h1 className="page-title">{quiz.title}</h1>
          <p className="page-description">这里用于调整试卷题目内容，不会进入答题流程。</p>
        </div>
        <div className="quiz-editor-summary"><Link className="button button-secondary" href={`/quizzes/${quiz.id}/generation-debug`} onClick={(event) => { if (dirtyQuestionIds.size > 0 && !window.confirm("还有题目未保存，确定离开吗？未保存内容会丢失。")) event.preventDefault(); }}><Code2 size={15} />查看出题过程</Link>{dirtyQuestionIds.size > 0 && <div className="quiz-editor-dirty-summary"><AlertCircle size={14} />{dirtyQuestionIds.size} 道题待保存</div>}
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
          <dl><div><dt>难度</dt><dd>{quiz.difficulty === "easy" ? "基础" : quiz.difficulty === "hard" ? "深入" : "适中"}</dd></div><div><dt>来源</dt><dd>{quiz.source_mode === "model_knowledge" ? "模型知识" : quiz.source_mode === "material" ? "可信台词" : quiz.source_mode === "plot" ? "剧情梗概" : quiz.source_mode === "combined" ? "综合可信来源" : "PDF 原文"}</dd></div><div><dt>状态</dt><dd>{quiz.status === "ready" ? "可复习" : "已提交"}</dd></div></dl>
        </aside>
      </div>

      <section className="content-panel quiz-question-edit-panel">
        <div className="section-title"><h2>题目编辑</h2><span>直接修改每道题的题干、选项和标准答案</span></div>
        <QuizQuestionEditList
          onRegenerateQuestion={(questionId) => regenerateQuizQuestion(quiz.id, questionId)}
          onSaved={handleQuestionSaved}
          onReviewQuestion={handleQuestionReview}
          onPromoteQuestion={(questionId) => promoteQuestionToBank(quiz.id, questionId)}
          onDirtyChange={handleDirtyChange}
          onUpdateQuestion={(questionId, payload) => updateQuizQuestion(quiz.id, questionId, payload)}
          qualityReviewResult={quiz.quality_review_result}
          questions={quiz.questions}
        />
      </section>
    </div>
  );
}
