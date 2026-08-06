"use client";

import { Check, CircleX, Clock3, LoaderCircle } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ErrorState } from "@/components/ui";
import { ExamLearningAnalysis } from "@/components/exam-learning-analysis";
import { ApiError, getPublicExamResult } from "@/lib/api";
import { readExamAccess } from "@/lib/exam-access";
import { formatDuration, formatScore, scorePercentage } from "@/lib/format";
import type { ExamAttempt } from "@/lib/types";

export default function PublicExamResultPage() {
  const params = useParams<{ shareCode: string; attemptId: string }>();
  const [result, setResult] = useState<ExamAttempt | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const access = readExamAccess(params.shareCode);
    const token = access?.attemptId === params.attemptId ? access.token : null;
    const load = async () => {
      try {
        const data = await getPublicExamResult(params.attemptId, token);
        if (cancelled) return;
        setResult(data);
        setError("");
        if (data.status === "grading") timer = window.setTimeout(() => { void load(); }, 1800);
      } catch (reason: unknown) {
        if (!cancelled) setError(reason instanceof ApiError ? reason.message : "考试结果加载失败");
      }
    };
    void load();
    return () => { cancelled = true; if (timer) window.clearTimeout(timer); };
  }, [params.attemptId, params.shareCode]);

  const answerMap = useMemo(() => new Map(result?.answers.map((answer) => [answer.question_id, answer]) || []), [result?.answers]);
  if (!result && !error) return <div className="public-exam-center"><div className="loading-state">正在读取考试结果……</div></div>;
  if (!result) return <div className="public-exam-center"><ErrorState message={error} /></div>;

  if (result.status === "grading") return <div className="public-exam-center"><div className="public-grading-panel"><LoaderCircle className="spin" size={30} /><h1>正在评分</h1><p>客观题已经完成判分，问答题正在由模型评分。</p><span><Clock3 size={14} />页面会自动更新结果</span></div></div>;
  if (result.status === "grading_failed") return <div className="public-exam-center"><div className="public-grading-panel grading-failed"><CircleX size={30} /><h1>问答题评分暂时失败</h1><p>你的答案已经保存，请联系考试分享者重新发起评分。</p></div></div>;

  const percent = scorePercentage(result.total_score, result.max_score) || 0;
  const low = percent < 60;
  return <div className="public-exam-page public-result-page">
    {error && <div className="toast-error">{error}</div>}
    <section className="result-header"><div className={`result-score ${low ? "low" : ""}`}><div className="score-number"><strong>{formatScore(result.total_score)}</strong><span>/ {formatScore(result.max_score)}</span></div><div className="score-copy"><div className="eyebrow">Exam complete</div><h1>{percent >= 80 ? "完成得很好" : percent >= 60 ? "考试已经完成" : "还有一些内容值得再复习"}</h1><p>{result.exam_name} · {result.participant_name}<br />用时 {formatDuration(result.elapsed_seconds)} · 得分率 {percent}%</p></div></div></section>
    <div className="public-result-note">公开结果不展示 PDF 文件名、页码和原文摘录。</div>
    <ExamLearningAnalysis recommendedDirection={result.recommended_direction} weakPoints={result.weak_knowledge_points || []} />
    <div className="section-title"><h2>逐题结果</h2><span>{result.questions.length} 道题</span></div>
    {result.questions.map((question, index) => { const answer = answerMap.get(question.id); if (!answer) return null; const selectedText = question.question_type === "short" ? answer.text_answer || "未作答" : question.options.filter((option) => answer.selected_answers.includes(option.id)).map((option) => `${option.id}. ${option.text}`).join("；") || "未作答"; const correctText = question.question_type === "short" ? question.reference_answer : question.options.filter((option) => question.correct_answers?.includes(option.id)).map((option) => `${option.id}. ${option.text}`).join("；"); return <article className={`result-question ${answer.is_correct ? "correct" : "incorrect"}`} key={question.id}><div className="question-card-header"><span className="question-number">第 {index + 1} 题 · {question.knowledge_point}</span><span className={answer.score / answer.max_score >= 0.6 ? "score-good" : "score-low"}>{formatScore(answer.score)} / {formatScore(answer.max_score)} 分</span></div><h3>{question.prompt}</h3><div className="result-answer-row"><div><strong>你的答案：</strong>{selectedText}</div><div><strong>{question.question_type === "short" ? "参考答案" : "正确答案"}：</strong>{correctText || "—"}</div></div><div className="result-feedback">{answer.is_correct ? <Check size={14} /> : <CircleX size={14} />}{answer.feedback} {question.explanation}</div></article>; })}
  </div>;
}
