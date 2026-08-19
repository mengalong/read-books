"use client";

import { ArrowLeft, CalendarClock, Check, CircleX, History, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ErrorState, EvidenceList, SourceModeNotice } from "@/components/ui";
import { ApiError, getQuizResult } from "@/lib/api";
import { formatDate, formatDuration, formatScore, scorePercentage } from "@/lib/format";
import type { QuizResult } from "@/lib/types";

export default function QuizResultPage() {
  const params = useParams<{ quizId: string }>();
  const [result, setResult] = useState<QuizResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getQuizResult(params.quizId).then(setResult).catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "结果加载失败"));
  }, [params.quizId]);

  const answerMap = useMemo(() => new Map(result?.answers.map((answer) => [answer.question_id, answer]) || []), [result]);

  if (!result && !error) return <div className="page-wrap"><div className="loading-state">正在整理复习结果……</div></div>;
  if (!result) return <div className="page-wrap"><ErrorState message={error} /></div>;

  const percent = scorePercentage(result.total_score, result.max_score) ?? 0;
  const isLowScore = result.max_score > 0 && (result.total_score || 0) / result.max_score < 0.6;
  return (
    <div className="page-wrap">
      <Link className="back-link" href={`/books/${result.book_id}`}><ArrowLeft size={14} />返回《{result.book_title}》</Link>
      <SourceModeNotice sourceMode={result.source_mode} compact />
      <section className="result-header">
        <div className={`result-score ${isLowScore ? "low" : ""}`}>
          <div className="score-number"><strong>{formatScore(result.total_score)}</strong><span>/ {formatScore(result.max_score)}</span></div>
          <div className="score-copy"><div className="eyebrow">Review complete</div><h1>{percent >= 80 ? "掌握得不错，继续保持" : percent >= 60 ? "已经记住一部分" : "找到需要重读的地方了"}</h1><p>{result.title} · 用时 {formatDuration(result.elapsed_seconds)}<br />得分 {formatScore(result.total_score)} / {formatScore(result.max_score)} · 得分率 {percent}%</p></div>
        </div>
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
          <div className="question-card-header"><span className="question-number">第 {index + 1} 题 · {question.knowledge_point}</span><span className={answer.score / answer.max_score >= 0.6 ? "score-good" : "score-low"}>{answer.score} / {answer.max_score} 分</span></div>
          <h3 style={{ marginTop: 11 }}>{question.prompt}</h3>
          <div className="result-answer-row"><div><strong>你的答案：</strong>{selectedText}</div><div><strong>{question.question_type === "short" ? "AI 参考答案" : "正确答案"}：</strong>{correctText}</div></div>
          <div className="result-feedback">{answer.is_correct ? <Check size={14} style={{ verticalAlign: "-3px", marginRight: 5 }} /> : <CircleX size={14} style={{ verticalAlign: "-3px", marginRight: 5 }} />}{answer.feedback} {question.explanation}</div>
          {question.question_type === "short" && <div className="rubric-list">{question.grading_rubric.map((rubric) => {
            const matched = answer.matched_points.includes(rubric.point);
            return <div className={`rubric-row ${matched ? "hit" : ""}`} key={rubric.point}>{matched ? "已覆盖" : "待补充"}：{rubric.point}</div>;
          })}</div>}
          <EvidenceList evidence={question.source_evidence} open sourceMode={result.source_mode} />
        </article>;
      })}

      <div className="form-actions" style={{ borderTop: 0 }}><Link className="button button-secondary" href={`/books/${result.book_id}/history`}><History size={15} />查看历史</Link><Link className="button button-primary" href={`/books/${result.book_id}/quiz/new`}><RotateCcw size={15} />再生成一套</Link></div>
    </div>
  );
}
