"use client";

import { AlertTriangle, ArrowLeft, CheckCircle2, ClipboardCheck, Clock3, Code2, Download, Eye, FileQuestion, LoaderCircle, Play } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ErrorState, SourceModeNotice } from "@/components/ui";
import { ApiError, getQuiz, getQuizExport, requestQuizQualityReview, startReview } from "@/lib/api";
import type { Quiz } from "@/lib/types";

const questionTypeLabels = {
  single: "单项选择题",
  multiple: "多项选择题",
  short: "问答题",
} as const;

export default function QuizOverviewPage() {
  const params = useParams<{ quizId: string }>();
  const router = useRouter();
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [starting, setStarting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [qualityReviewBusy, setQualityReviewBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getQuiz(params.quizId)
      .then(setQuiz)
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "试卷加载失败"))
      .finally(() => setLoading(false));
  }, [params.quizId]);

  useEffect(() => {
    if (!quiz || !["pending", "processing"].includes(quiz.quality_review_status)) return;
    const timer = window.setInterval(() => {
      getQuiz(params.quizId).then(setQuiz).catch(() => undefined);
    }, 2200);
    return () => window.clearInterval(timer);
  }, [params.quizId, quiz?.quality_review_status]);

  const overview = useMemo(() => {
    if (!quiz) return [];
    return (["single", "multiple", "short"] as const)
      .map((type) => {
        const items = quiz.questions.filter((question) => question.question_type === type);
        return {
          type,
          label: questionTypeLabels[type],
          count: items.length,
          score: items.reduce((sum, question) => sum + question.max_score, 0),
        };
      })
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

  async function handleExport() {
    if (!quiz) return;
    setExporting(true);
    setError("");
    try {
      const payload = await getQuizExport(quiz.id);
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${quiz.title.replace(/[\\/:*?"<>|]/g, "_")}-题目答案校验.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "试卷导出失败");
    } finally {
      setExporting(false);
    }
  }

  async function handleQualityReview() {
    if (!quiz || qualityReviewBusy) return;
    setQualityReviewBusy(true);
    setError("");
    try {
      const review = await requestQuizQualityReview(quiz.id);
      setQuiz((current) => current ? {
        ...current,
        quality_review_status: review.status,
        quality_review_task_id: review.task_id,
        quality_review_result: review.result,
        quality_review_error: review.error,
        quality_review_requested_at: review.requested_at,
        quality_review_completed_at: review.completed_at,
      } : current);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "试卷审查任务创建失败");
    } finally {
      setQualityReviewBusy(false);
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在打开试卷概览……</div></div>;
  if (!quiz) return <div className="page-wrap"><ErrorState message={error || "未找到这套试卷"} /></div>;

  return (
    <div className="page-wrap">
      <Link className="back-link" href={`/books/${quiz.book_id}`}><ArrowLeft size={14} />返回《{quiz.book_title}》</Link>
      {error && <div className="toast-error">{error}</div>}
      <SourceModeNotice sourceMode={quiz.source_mode} />
      <header className="page-header">
        <div><div className="eyebrow">Review paper</div><h1 className="page-title">{quiz.title}</h1><p className="page-description">先查看这套试卷的概览，确认后再开始答题。只有点击开始按钮后才会创建复习记录。</p></div>
        <div className="quiz-overview-actions"><Link className="button button-secondary" href={`/quizzes/${quiz.id}/generation-debug`}><Code2 size={15} />查看出题过程</Link><Link className="button button-secondary" href={`/quizzes/${quiz.id}/preview`}><Eye size={15} />预览题目与答案</Link><button className="button button-secondary" disabled={exporting} onClick={() => void handleExport()} type="button"><Download size={15} />{exporting ? "正在导出……" : "导出题目与答案"}</button><button className="button button-primary" disabled={starting} onClick={() => void handleStart()} type="button"><Play size={15} />{starting ? "正在进入……" : "开始答题"}</button></div>
      </header>

      <QuizQualityReviewPanel quiz={quiz} busy={qualityReviewBusy} onRequest={() => void handleQualityReview()} />

      <div className="quiz-choice-layout">
        <section className="content-panel">
          <div className="section-title"><h2>试卷概述</h2><span>题型分布与总分</span></div>
          <div className="quiz-choice-items">
            {overview.map((item) => <div className="quiz-choice-item" key={item.type}><div className="count-icon"><FileQuestion size={17} /></div><div><strong>{item.label}</strong><span>{item.count} 道 · {item.score} 分</span></div></div>)}
          </div>
          <div className="quiz-choice-note"><CheckCircle2 size={16} />{quiz.source_mode === "model_knowledge" ? "本套试卷基于模型知识生成，没有 PDF 页码和逐句原文依据。" : quiz.source_mode === "combined" ? "综合模式按方向使用剧情事件、可信台词及可用的 PDF 原文来源。" : quiz.source_mode === "material" ? "每道题都保留对应的可信台词来源。" : quiz.source_mode === "plot" ? "每道题都保留对应的剧情梗概事件来源。" : "每道题都保留对应的 PDF 页码和原文依据。"}</div>
        </section>
        <aside className="quiz-settings-summary">
          <div className="eyebrow">本套试卷</div>
          <strong>{quiz.questions.length} 道题 · {quiz.max_score} 分</strong>
          <p>点击开始答题后，系统才会创建本次复习记录并进入答题详情页。</p>
          <dl><div><dt>目标时长</dt><dd><Clock3 size={13} />{quiz.duration_minutes} 分钟</dd></div><div><dt>难度</dt><dd>{quiz.difficulty === "easy" ? "基础" : quiz.difficulty === "hard" ? "深入" : "适中"}</dd></div><div><dt>复习记录</dt><dd>开始后生成</dd></div></dl>
        </aside>
      </div>
    </div>
  );
}

function QuizQualityReviewPanel({ quiz, busy, onRequest }: { quiz: Quiz; busy: boolean; onRequest: () => void }) {
  const status = quiz.quality_review_status || "not_started";
  const result = quiz.quality_review_result;
  const statusLabel = status === "processing" ? "审查中" : status === "pending" ? "排队中" : status === "completed" ? "已完成" : status === "failed" ? "审查失败" : "尚未审查";
  const verdictLabel = result?.overall_verdict === "pass" ? "建议通过" : result?.overall_verdict === "high_risk" ? "存在高风险" : "建议修改";
  return <section className="content-panel quiz-quality-review">
    <div className="section-title"><div className="quality-review-title"><ClipboardCheck size={18} /><h2>模型合理性审查</h2></div><span>{statusLabel}</span></div>
    {status === "not_started" && <div className="quality-review-empty"><p>让模型逐题核对题干、答案、解析、来源和题意，结果只作为人工修改建议，不会自动改题。</p><button className="button button-secondary" disabled={busy} onClick={onRequest} type="button"><ClipboardCheck size={15} />{busy ? "正在提交……" : "开始模型审查"}</button></div>}
    {(status === "pending" || status === "processing") && <div className="quality-review-progress"><LoaderCircle className="spin" size={17} /><span>模型正在逐题检查，页面会自动更新结果。</span></div>}
    {status === "failed" && <div className="quality-review-failed"><AlertTriangle size={17} /><span>{quiz.quality_review_error || "模型审查失败，请稍后重试。"}</span><button className="button button-secondary" disabled={busy} onClick={onRequest} type="button">重新审查</button></div>}
    {status === "completed" && result && <div className="quality-review-result">
      <div className={`quality-review-verdict ${result.overall_verdict}`}><div><strong>整套评分 {result.score}/100</strong><span className="quality-review-verdict-label">{verdictLabel}</span></div><span>{result.summary || "审查已完成。"}</span></div>
      {(result.question_reviews || []).length > 0 && <div className="quality-review-question-scores"><strong>逐题评分</strong><div>{result.question_reviews.map((review) => <article className={`quality-review-question-score ${review.verdict}`} key={review.question_position}><span>第 {review.question_position} 题</span><strong>{review.score}</strong><small>{review.verdict === "pass" ? "通过" : review.verdict === "high_risk" ? "高风险" : "建议修改"}</small></article>)}</div></div>}
      {result.strengths.length > 0 && <div className="quality-review-strengths"><strong>做得较好的地方</strong><ul>{result.strengths.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
      {result.issues.length > 0 ? <div className="quality-review-issues"><strong>需要人工确认或修改（{result.issues.length}）</strong>{result.issues.map((issue, index) => <article className={`quality-review-issue ${issue.severity}`} key={`${issue.question_position || "all"}-${index}`}><div><span className="quality-review-issue-position">{issue.question_position ? `第 ${issue.question_position} 题` : "整套试卷"}</span><span className="quality-review-issue-category">{qualityReviewCategoryLabels[issue.category]}</span><span className="quality-review-issue-severity">{qualityReviewSeverityLabels[issue.severity]}</span></div><p><strong>问题：</strong>{issue.problem}</p><p><strong>建议：</strong>{issue.suggestion}</p>{issue.suggested_prompt && <p><strong>建议题干：</strong>{issue.suggested_prompt}</p>}{(issue.suggested_options || []).length > 0 && <div className="quality-review-suggested-options"><strong>建议选项：</strong>{(issue.suggested_options || []).map((option) => <span className={(issue.suggested_correct_answers || []).includes(option.id) ? "correct" : ""} key={option.id}>{option.id}. {option.text}{(issue.suggested_correct_answers || []).includes(option.id) ? "（答案）" : ""}</span>)}</div>}{issue.suggested_explanation && <p><strong>建议解析：</strong>{issue.suggested_explanation}</p>}{issue.suggested_knowledge_point && <p><strong>建议知识点：</strong>{issue.suggested_knowledge_point}</p>}{issue.suggested_reference_answer && <p><strong>建议参考答案：</strong>{issue.suggested_reference_answer}</p>}{issue.evidence && <p className="quality-review-issue-evidence"><strong>依据：</strong>{issue.evidence}</p>}</article>)}</div> : <div className="quality-review-no-issues"><CheckCircle2 size={17} /><span>未发现需要立即修改的问题，仍建议人工抽查高风险事实。</span></div>}
      <button className="button button-secondary quality-review-rerun" disabled={busy} onClick={onRequest} type="button"><ClipboardCheck size={15} />{busy ? "正在提交……" : "重新审查"}</button>
    </div>}
  </section>;
}

const qualityReviewCategoryLabels: Record<NonNullable<Quiz["quality_review_result"]>["issues"][number]["category"], string> = {
  fact: "事实",
  answer: "答案",
  source: "来源",
  ambiguity: "歧义",
  duplicate: "重复",
  wording: "措辞",
  difficulty: "难度",
  other: "其他",
};

const qualityReviewSeverityLabels: Record<NonNullable<Quiz["quality_review_result"]>["issues"][number]["severity"], string> = {
  high: "高风险",
  medium: "建议修改",
  low: "措辞优化",
};
