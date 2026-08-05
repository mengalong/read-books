"use client";

import { ArrowLeft, ArrowRight, CheckCircle2, Clock3, Send } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ErrorState, EvidenceList, SourceModeNotice } from "@/components/ui";
import { ApiError, getReview, submitReview } from "@/lib/api";
import type { Question, ReviewTask } from "@/lib/types";

type DraftAnswer = { selected: string[]; text: string };

function questionTypeLabel(type: Question["question_type"]) {
  return { single: "单项选择", multiple: "多项选择", short: "问答" }[type];
}

export default function ReviewPage() {
  const params = useParams<{ reviewId: string }>();
  const router = useRouter();
  const [review, setReview] = useState<ReviewTask | null>(null);
  const [answers, setAnswers] = useState<Record<string, DraftAnswer>>({});
  const [current, setCurrent] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getReview(params.reviewId)
      .then((data) => {
        if (data.status === "submitted") {
          router.replace(`/reviews/${data.id}/result`);
          return;
        }
        setReview(data);
        setAnswers(Object.fromEntries(data.questions.map((question) => [question.id, { selected: [], text: "" }])));
      })
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "复习任务加载失败"))
      .finally(() => setLoading(false));
  }, [params.reviewId, router]);

  useEffect(() => {
    if (!review || review.status === "submitted") return;
    const timer = window.setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [review]);

  const question = review?.questions[current];
  const answeredCount = useMemo(() => Object.values(answers).filter((answer) => answer.selected.length > 0 || answer.text.trim().length > 0).length, [answers]);
  const totalSeconds = (review?.duration_minutes || 15) * 60;
  const remaining = Math.max(0, totalSeconds - elapsed);
  const timerText = `${String(Math.floor(remaining / 60)).padStart(2, "0")}:${String(remaining % 60).padStart(2, "0")}`;

  function selectOption(currentQuestion: Question, optionId: string) {
    setAnswers((currentAnswers) => {
      const previous = currentAnswers[currentQuestion.id] || { selected: [], text: "" };
      const selected = currentQuestion.question_type === "single"
        ? [optionId]
        : previous.selected.includes(optionId)
          ? previous.selected.filter((id) => id !== optionId)
          : [...previous.selected, optionId];
      return { ...currentAnswers, [currentQuestion.id]: { ...previous, selected } };
    });
  }

  async function handleSubmit(mode: "regular" | "early" = "regular") {
    if (!review) return;
    const unanswered = review.questions.length - answeredCount;
    if (unanswered) {
      const message = mode === "early"
        ? `还有 ${unanswered} 道题未作答，提前交卷后这些题将按 0 分处理，且提交后不能修改。确认提前交卷吗？`
        : `还有 ${unanswered} 道题未作答，提交后这些题将按 0 分处理。仍然提交吗？`;
      if (!window.confirm(message)) return;
    }
    setSubmitting(true);
    setError("");
    try {
      await submitReview(review.id, {
        elapsed_seconds: elapsed,
        answers: review.questions.map((item) => ({
          question_id: item.id,
          selected_answers: answers[item.id]?.selected || [],
          text_answer: answers[item.id]?.text || "",
        })),
      });
      router.push(`/reviews/${review.id}/result`);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "提交失败，请稍后重试");
      setSubmitting(false);
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在打开复习任务……</div></div>;
  if (!review || !question) return <div className="page-wrap"><ErrorState message={error || "未找到这次复习任务"} /></div>;

  const draft = answers[question.id] || { selected: [], text: "" };
  return (
    <div className="page-wrap">
      {error && <div className="toast-error">{error}</div>}
      <SourceModeNotice sourceMode={review.source_mode} compact />
      <div className="quiz-layout">
        <aside className="quiz-sidebar">
          <div className="quiz-sidebar-card">
            <div className="quiz-sidebar-title">{review.title}</div>
            <div className="quiz-sidebar-meta">第 {review.attempt_number} 次复习 · {review.questions.length} 道题</div>
            <div className={`quiz-timer ${remaining < 120 ? "warning" : ""}`}><Clock3 size={16} />{timerText}</div>
            <div className="question-nav">{review.questions.map((item, index) => {
              const draftItem = answers[item.id];
              const done = draftItem && (draftItem.selected.length > 0 || draftItem.text.trim());
              return <button aria-label={`前往第${index + 1}题`} className={`${done ? "done" : ""} ${index === current ? "current" : ""}`} key={item.id} onClick={() => setCurrent(index)} type="button">{index + 1}</button>;
            })}</div>
            <p className="quiz-sidebar-meta" style={{ marginTop: 13 }}>已答 {answeredCount} / {review.questions.length}</p>
            <button className="button button-secondary quiz-early-submit" disabled={submitting} onClick={() => void handleSubmit("early")} type="button"><Send size={15} />提前交卷</button>
          </div>
        </aside>

        <main>
          <div className="quiz-main-header"><div><Link className="back-link" href={`/books/${review.book_id}`} style={{ marginBottom: 8 }}><ArrowLeft size={13} />暂时离开</Link><h1>{review.book_title}</h1></div><span className="quiz-progress-label">第 {current + 1} / {review.questions.length} 题</span></div>
          <div className="progress-track"><div className="progress-fill" style={{ width: `${((current + 1) / review.questions.length) * 100}%` }} /></div>
          <article className="question-card" style={{ marginTop: 15 }}>
            <header className="question-card-header"><span className="question-number">QUESTION {String(current + 1).padStart(2, "0")}</span><span className="question-type">{questionTypeLabel(question.question_type)} · {question.max_score} 分</span></header>
            <h2 className="question-prompt">{question.prompt}</h2>
            <p className="question-hint">知识点：{question.knowledge_point}{question.question_type === "multiple" ? " · 本题有多个正确答案" : ""}</p>
            {question.question_type !== "short" ? <div className="option-list">{question.options.map((option) => {
              const selected = draft.selected.includes(option.id);
              return <label className={`option-label ${selected ? "selected" : ""}`} key={option.id}><input checked={selected} name={question.id} onChange={() => selectOption(question, option.id)} type={question.question_type === "single" ? "radio" : "checkbox"} /><span className="option-id">{option.id}</span><span className="option-text">{option.text}</span></label>;
            })}</div> : <textarea className="answer-textarea" onChange={(event) => setAnswers((currentAnswers) => ({ ...currentAnswers, [question.id]: { ...(currentAnswers[question.id] || { selected: [] }), text: event.target.value } }))} placeholder="请用自己的语言回答，不要求逐字复述原文……" value={draft.text} />}
            <EvidenceList evidence={question.source_evidence} sourceMode={review.source_mode} />
          </article>
          <footer className="quiz-footer">
            <button className="button button-secondary" disabled={current === 0} onClick={() => setCurrent((index) => index - 1)} type="button"><ArrowLeft size={15} />上一题</button>
            {current < review.questions.length - 1 ? <button className="button button-primary" onClick={() => setCurrent((index) => index + 1)} type="button">下一题<ArrowRight size={15} /></button> : <button className="button button-primary" disabled={submitting} onClick={() => void handleSubmit()} type="button"><Send size={15} />{submitting ? "评分中……" : "提交本次复习"}</button>}
          </footer>
          {answeredCount === review.questions.length && current < review.questions.length - 1 && <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}><button className="button button-quiet" onClick={() => void handleSubmit()} type="button"><CheckCircle2 size={15} />全部作答，直接提交</button></div>}
        </main>
      </div>
    </div>
  );
}
