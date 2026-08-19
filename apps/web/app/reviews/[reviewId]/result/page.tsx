"use client";

import { ArrowLeft, CalendarClock, Check, CircleX, History, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ErrorState, EvidenceList, SourceModeNotice } from "@/components/ui";
import { QuestionEditor } from "@/components/question-editor";
import { ApiError, getReviewResult, reopenReview } from "@/lib/api";
import { formatDate, formatDuration, formatScore, scorePercentage } from "@/lib/format";
import type { ReviewTask } from "@/lib/types";

export default function ReviewResultPage() {
  const params = useParams<{ reviewId: string }>();
  const router = useRouter();
  const [result, setResult] = useState<ReviewTask | null>(null);
  const [error, setError] = useState("");
  const [reopening, setReopening] = useState(false);

  useEffect(() => {
    getReviewResult(params.reviewId).then(setResult).catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "结果加载失败"));
  }, [params.reviewId]);

  const answerMap = useMemo(() => new Map(result?.answers.map((answer) => [answer.question_id, answer]) || []), [result]);

  function handleQuestionSaved(updatedQuestion: ReviewTask["questions"][number]) {
    setResult((current) => {
      if (!current) return current;
      return {
        ...current,
        questions: current.questions.map((question) =>
          question.id === updatedQuestion.id ? updatedQuestion : question,
        ),
      };
    });
  }

  async function handleReopen() {
    if (!result) return;
    setReopening(true);
    try {
      await reopenReview(result.id);
      router.push(`/reviews/${result.id}`);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "重新答题失败");
      setReopening(false);
    }
  }

  if (!result && !error) return <div className="page-wrap"><div className="loading-state">正在整理复习结果……</div></div>;
  if (!result) return <div className="page-wrap"><ErrorState message={error} /></div>;

  const percent = scorePercentage(result.total_score, result.max_score) ?? 0;
  const isLowScore = result.max_score > 0 && (result.total_score || 0) / result.max_score < 0.6;
  return (
    <div className="page-wrap">
      <Link className="back-link" href={`/books/${result.book_id}`}><ArrowLeft size={14} />返回《{result.book_title}》</Link>
      {error && <div className="toast-error">{error}</div>}
      <SourceModeNotice sourceMode={result.source_mode} compact />
      <section className="result-header">
        <div className={`result-score ${isLowScore ? "low" : ""}`}><div className="score-number"><strong>{formatScore(result.total_score)}</strong><span>/ {formatScore(result.max_score)}</span></div><div className="score-copy"><div className="eyebrow">Review complete</div><h1>{percent >= 80 ? "掌握得不错，继续保持" : percent >= 60 ? "已经记住一部分" : "找到需要重读的地方了"}</h1><p>{result.title} · 第 {result.attempt_number} 次复习 · 用时 {formatDuration(result.elapsed_seconds)}<br />得分 {formatScore(result.total_score)} / {formatScore(result.max_score)} · 得分率 {percent}%</p></div></div>
        <div className="result-next-review"><CalendarClock size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} /><strong>下次建议复习</strong>{formatDate(result.next_review_date)}</div>
      </section>

      {result.weak_points.length > 0 && <div className="weak-points"><strong>本次薄弱点：</strong>{result.weak_points.join("、")}</div>}
      <div className="section-title"><h2>逐题复盘</h2><span>{result.source_mode === "model_knowledge" ? "模型知识说明已全部展开" : "原文依据已全部展开"}</span></div>
      {result.questions.map((question, index) => {
        const answer = answerMap.get(question.id);
        if (!answer) return null;
        const selectedText = question.question_type === "short" ? answer.text_answer || "未作答" : question.options.filter((option) => answer.selected_answers.includes(option.id)).map((option) => `${option.id}. ${option.text}`).join("；") || "未作答";
        const correctText = question.question_type === "short" ? question.reference_answer : question.options.filter((option) => question.correct_answers?.includes(option.id)).map((option) => `${option.id}. ${option.text}`).join("；");
        return <article className={`result-question ${answer.is_correct ? "correct" : "incorrect"}`} key={question.id}>
          <div className="question-card-header"><span className="question-number">第 {index + 1} 题 · {question.knowledge_point}</span><div className="question-card-actions"><span className={answer.score / answer.max_score >= 0.6 ? "score-good" : "score-low"}>{answer.score} / {answer.max_score} 分</span><QuestionEditor className="button button-secondary question-edit-trigger" onSaved={handleQuestionSaved} question={question} quizId={result.id} /></div></div>
          <h3 style={{ marginTop: 11 }}>{question.prompt}</h3>
          <div className="result-answer-row"><div><strong>你的答案：</strong>{selectedText}</div><div><strong>{question.question_type === "short" ? "AI 参考答案" : "正确答案"}：</strong>{correctText}</div></div>
          <div className="result-feedback">{answer.is_correct ? <Check size={14} style={{ verticalAlign: "-3px", marginRight: 5 }} /> : <CircleX size={14} style={{ verticalAlign: "-3px", marginRight: 5 }} />}{answer.feedback} {question.explanation}</div>
          {question.question_type === "short" && <div className="rubric-list">{question.grading_rubric.map((rubric) => <div className={`rubric-row ${answer.matched_points.includes(rubric.point) ? "hit" : ""}`} key={rubric.point}>{answer.matched_points.includes(rubric.point) ? "已覆盖" : "待补充"}：{rubric.point}</div>)}</div>}
          <EvidenceList evidence={question.source_evidence} open sourceMode={result.source_mode} />
        </article>;
      })}

      <div className="form-actions" style={{ borderTop: 0 }}><Link className="button button-secondary" href="/reviews"><History size={15} />全部复习记录</Link><button className="button button-primary" disabled={reopening} onClick={() => void handleReopen()} type="button"><RotateCcw size={15} />{reopening ? "正在准备……" : "重新答这套试卷"}</button></div>
    </div>
  );
}
