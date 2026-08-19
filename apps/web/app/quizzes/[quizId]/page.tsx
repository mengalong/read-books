"use client";

import { ArrowLeft, CheckCircle2, Clock3, FileQuestion, Play } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { QuestionEditor } from "@/components/question-editor";
import { ErrorState, SourceModeNotice } from "@/components/ui";
import { ApiError, getEditableQuiz, startReview } from "@/lib/api";
import type { Question, Quiz } from "@/lib/types";

const questionTypeLabels: Record<Question["question_type"], string> = {
  single: "单项选择题",
  multiple: "多项选择题",
  short: "问答题",
};

export default function QuizOverviewPage() {
  const params = useParams<{ quizId: string }>();
  const router = useRouter();
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [starting, setStarting] = useState(false);
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

  async function handleStart() {
    if (!quiz) return;
    setStarting(true);
    setError("");
    try {
      const review = await startReview(quiz.id);
      router.push(`/reviews/${review.id}`);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "复习任务创建失败");
      setStarting(false);
    }
  }

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

  if (loading) return <div className="page-wrap"><div className="loading-state">正在打开复习试卷……</div></div>;
  if (!quiz) return <div className="page-wrap"><ErrorState message={error || "未找到这套复习试卷"} /></div>;

  return (
    <div className="page-wrap">
      <Link className="back-link" href={`/books/${quiz.book_id}`}><ArrowLeft size={14} />返回《{quiz.book_title}》</Link>
      {error && <div className="toast-error">{error}</div>}
      <SourceModeNotice sourceMode={quiz.source_mode} />
      <header className="page-header">
        <div><div className="eyebrow">Review paper</div><h1 className="page-title">{quiz.title}</h1><p className="page-description">从这套试卷开始一次新的复习任务。同一套试卷可以反复作答，每次结果都会单独记录。</p></div>
        <button className="button button-primary" disabled={starting} onClick={() => void handleStart()} type="button"><Play size={15} />{starting ? "正在准备……" : "开始本次复习"}</button>
      </header>

      <div className="quiz-choice-layout">
        <section className="content-panel">
          <div className="section-title"><h2>试卷内容</h2><span>原文依据默认折叠</span></div>
          <div className="quiz-choice-items">
            {counts.map(({ type, count }) => <div className="quiz-choice-item" key={type}><div className="count-icon"><FileQuestion size={17} /></div><div><strong>{questionTypeLabels[type]}</strong><span>{count} 道</span></div></div>)}
          </div>
          <div className="quiz-choice-note"><CheckCircle2 size={16} />{quiz.source_mode === "model_knowledge" ? "本套试卷基于模型知识生成，没有 PDF 页码和逐句原文依据；提交后仍可查看 AI 参考答案与评分反馈。" : "每道题都保留对应的 PDF 页码和原文依据，提交后还可以查看 AI 参考答案与评分反馈。"}</div>
        </section>
        <aside className="quiz-settings-summary">
          <div className="eyebrow">本套试卷</div>
          <strong>{quiz.questions.length} 道题</strong>
          <p>选择开始后会创建一次独立的复习任务。你可以中途离开，之后从复习记录继续。</p>
          <dl><div><dt>目标时长</dt><dd><Clock3 size={13} />{quiz.duration_minutes} 分钟</dd></div><div><dt>难度</dt><dd>{quiz.difficulty === "easy" ? "基础" : quiz.difficulty === "hard" ? "深入" : "适中"}</dd></div><div><dt>答题次数</dt><dd>每次单独记录</dd></div></dl>
        </aside>
      </div>

      <section className="content-panel quiz-question-list-panel">
        <div className="section-title"><h2>题目列表</h2><span>可逐题调整题干、选项和标准答案</span></div>
        <div className="quiz-question-list">
          {quiz.questions.map((question) => (
            <article className="quiz-question-row" key={question.id}>
              <div className="quiz-question-main">
                <div className="question-card-header">
                  <span className="question-number">第 {question.position} 题 · {question.knowledge_point}</span>
                  <span className="question-type">{questionTypeLabels[question.question_type]}</span>
                </div>
                <h3 className="quiz-question-title">{question.prompt}</h3>
                {question.question_type === "short" ? (
                  <p className="quiz-question-answer">标准答案：{question.reference_answer || "未设置"}</p>
                ) : (
                  <div className="quiz-question-options">
                    {question.options.map((option) => (
                      <span className={question.correct_answers?.includes(option.id) ? "is-correct" : ""} key={option.id}>
                        {option.id}. {option.text}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <QuestionEditor
                className="button button-secondary question-edit-trigger"
                onSaved={handleQuestionSaved}
                question={question}
                quizId={quiz.id}
              />
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
