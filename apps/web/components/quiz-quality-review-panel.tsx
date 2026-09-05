"use client";

import { AlertTriangle, CheckCircle2, ClipboardCheck, LoaderCircle } from "lucide-react";

import type { Quiz } from "@/lib/types";

type QuizQualityReviewPanelProps = {
  quiz: Quiz;
  busy: boolean;
  onRequest: () => void;
};

export function QuizQualityReviewPanel({ quiz, busy, onRequest }: QuizQualityReviewPanelProps) {
  const status = quiz.quality_review_status || "not_started";
  const result = quiz.quality_review_result;
  const statusLabel = status === "processing" ? "审查中" : status === "pending" ? "排队中" : status === "completed" ? "已完成" : status === "failed" ? "审查失败" : "尚未审查";
  const verdictLabel = result?.overall_verdict === "pass" ? "建议通过" : result?.overall_verdict === "high_risk" ? "存在高风险" : "建议修改";
  return <section className="content-panel quiz-quality-review">
    <div className="section-title"><div className="quality-review-title"><ClipboardCheck size={18} /><h2>模型合理性审查</h2></div><span>{statusLabel}</span></div>
    {status === "not_started" && <div className="quality-review-empty"><p>让模型逐题核对题干、答案、解析、来源和题意，结果只作为人工修改建议，不会自动改题。</p><button className="button button-secondary" disabled={busy} onClick={onRequest} type="button"><ClipboardCheck size={15} />{busy ? "正在提交……" : "一键审核全部题目"}</button></div>}
    {(status === "pending" || status === "processing") && <div className="quality-review-progress"><LoaderCircle className="spin" size={17} /><span>模型正在逐题检查，页面会自动更新结果。</span></div>}
    {status === "failed" && <div className="quality-review-failed"><AlertTriangle size={17} /><span>{quiz.quality_review_error || "模型审查失败，请稍后重试。"}</span><button className="button button-secondary" disabled={busy} onClick={onRequest} type="button">重新审核全部题目</button></div>}
    {status === "completed" && result && <div className="quality-review-result">
      <div className={`quality-review-verdict ${result.overall_verdict}`}><div><strong>整套评分 {result.score}/100</strong><span className="quality-review-verdict-label">{verdictLabel}</span></div><span>{result.summary || "审查已完成。"}</span></div>
      {(result.question_reviews || []).length > 0 && <div className="quality-review-question-scores"><strong>逐题评分</strong><div>{result.question_reviews.map((review) => <article className={`quality-review-question-score ${review.verdict}`} key={review.question_position}><span>第 {review.question_position} 题</span><strong>{review.score}</strong><small>{review.verdict === "pass" ? "通过" : review.verdict === "high_risk" ? "高风险" : "建议修改"}</small></article>)}</div></div>}
      {result.strengths.length > 0 && <div className="quality-review-strengths"><strong>做得较好的地方</strong><ul>{result.strengths.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
      {result.issues.length > 0 ? <div className="quality-review-issues"><strong>需要人工确认或修改（{result.issues.length}）</strong>{result.issues.map((issue, index) => <article className={`quality-review-issue ${issue.severity}`} key={`${issue.question_position || "all"}-${index}`}><div><span className="quality-review-issue-position">{issue.question_position ? `第 ${issue.question_position} 题` : "整套试卷"}</span><span className="quality-review-issue-category">{qualityReviewCategoryLabels[issue.category]}</span><span className="quality-review-issue-severity">{qualityReviewSeverityLabels[issue.severity]}</span></div><p><strong>问题：</strong>{issue.problem}</p><p><strong>建议：</strong>{issue.suggestion}</p>{issue.suggested_prompt && <p><strong>建议题干：</strong>{issue.suggested_prompt}</p>}{(issue.suggested_options || []).length > 0 && <div className="quality-review-suggested-options"><strong>建议选项：</strong>{(issue.suggested_options || []).map((option) => <span className={(issue.suggested_correct_answers || []).includes(option.id) ? "correct" : ""} key={option.id}>{option.id}. {option.text}{(issue.suggested_correct_answers || []).includes(option.id) ? "（答案）" : ""}</span>)}</div>}{issue.suggested_explanation && <p><strong>建议解析：</strong>{issue.suggested_explanation}</p>}{issue.suggested_knowledge_point && <p><strong>建议知识点：</strong>{issue.suggested_knowledge_point}</p>}{issue.suggested_reference_answer && <p><strong>建议参考答案：</strong>{issue.suggested_reference_answer}</p>}{issue.evidence && <p className="quality-review-issue-evidence"><strong>依据：</strong>{issue.evidence}</p>}</article>)}</div> : <div className="quality-review-no-issues"><CheckCircle2 size={17} /><span>未发现需要立即修改的问题，仍建议人工抽查高风险事实。</span></div>}
      <button className="button button-secondary quality-review-rerun" disabled={busy} onClick={onRequest} type="button"><ClipboardCheck size={15} />{busy ? "正在提交……" : "重新审核全部题目"}</button>
    </div>}
  </section>;
}

const qualityReviewCategoryLabels: Record<NonNullable<Quiz["quality_review_result"]>["issues"][number]["category"], string> = {
  fact: "事实",
  answer: "答案",
  source: "来源",
  ambiguity: "歧义",
  duplicate: "重复",
  distractor: "干扰项",
  wording: "措辞",
  difficulty: "难度",
  other: "其他",
};

const qualityReviewSeverityLabels: Record<NonNullable<Quiz["quality_review_result"]>["issues"][number]["severity"], string> = {
  high: "高风险",
  medium: "建议修改",
  low: "措辞优化",
};
