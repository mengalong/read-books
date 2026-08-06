"use client";

import { ArrowLeft, ArrowRight, CheckCircle2, Clock3, Send } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ErrorState } from "@/components/ui";
import { ApiError, getPublicExamAttempt, submitPublicExamAttempt } from "@/lib/api";
import { readExamAccess } from "@/lib/exam-access";
import { elapsedSecondsSince } from "@/lib/format";
import type { ExamAttempt, ExamQuestion } from "@/lib/types";

type DraftAnswer = { selected: string[]; text: string };
const questionTypeLabels = { single: "单项选择", multiple: "多项选择", short: "问答" };

export default function PublicExamAttemptPage() {
  const params = useParams<{ shareCode: string; attemptId: string }>();
  const router = useRouter();
  const [attempt, setAttempt] = useState<ExamAttempt | null>(null);
  const [answers, setAnswers] = useState<Record<string, DraftAnswer>>({});
  const [token, setToken] = useState<string | null>(null);
  const [current, setCurrent] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const access = readExamAccess(params.shareCode);
    const savedToken = access?.attemptId === params.attemptId ? access.token : null;
    setToken(savedToken);
    getPublicExamAttempt(params.attemptId, savedToken)
      .then((data) => {
        if (data.status !== "in_progress") {
          router.replace(`/exams/${params.shareCode}/results/${params.attemptId}`);
          return;
        }
        setAttempt(data);
        setElapsed(elapsedSecondsSince(data.started_at));
        setAnswers(Object.fromEntries(data.questions.map((question) => [question.id, { selected: [], text: "" }])));
      })
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "答卷加载失败"))
      .finally(() => setLoading(false));
  }, [params.attemptId, params.shareCode, router]);

  useEffect(() => {
    if (!attempt) return;
    const timer = window.setInterval(() => setElapsed(elapsedSecondsSince(attempt.started_at)), 1000);
    return () => window.clearInterval(timer);
  }, [attempt]);

  const question = attempt?.questions[current];
  const answeredCount = useMemo(() => Object.values(answers).filter((answer) => answer.selected.length > 0 || answer.text.trim()).length, [answers]);
  const totalSeconds = (attempt?.duration_minutes || 15) * 60;
  const remaining = Math.max(0, totalSeconds - elapsed);
  const timerText = `${String(Math.floor(remaining / 60)).padStart(2, "0")}:${String(remaining % 60).padStart(2, "0")}`;

  function selectOption(currentQuestion: ExamQuestion, optionId: string) {
    setAnswers((currentAnswers) => {
      const previous = currentAnswers[currentQuestion.id] || { selected: [], text: "" };
      const selected = currentQuestion.question_type === "single" ? [optionId] : previous.selected.includes(optionId) ? previous.selected.filter((id) => id !== optionId) : [...previous.selected, optionId];
      return { ...currentAnswers, [currentQuestion.id]: { ...previous, selected } };
    });
  }

  async function handleSubmit(early = false) {
    if (!attempt) return;
    const unanswered = attempt.questions.length - answeredCount;
    if (unanswered && !window.confirm(`还有 ${unanswered} 道题未作答，${early ? "提前交卷" : "交卷"}后将按 0 分处理，且不能修改。确认提交吗？`)) return;
    setSubmitting(true);
    setError("");
    try {
      await submitPublicExamAttempt(attempt.id, {
        elapsed_seconds: elapsed,
        answers: attempt.questions.map((item) => ({ question_id: item.id, selected_answers: answers[item.id]?.selected || [], text_answer: answers[item.id]?.text || "" })),
      }, token);
      router.push(`/exams/${params.shareCode}/results/${attempt.id}`);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "交卷失败，请稍后重试");
      setSubmitting(false);
    }
  }

  if (loading) return <div className="public-exam-center"><div className="loading-state">正在打开答卷……</div></div>;
  if (!attempt || !question) return <div className="public-exam-center"><ErrorState message={error || "未找到这份答卷"} /></div>;
  const draft = answers[question.id] || { selected: [], text: "" };

  return <div className="public-exam-page exam-answering-page">
    {error && <div className="toast-error">{error}</div>}
    <div className="quiz-layout public-quiz-layout">
      <aside className="quiz-sidebar"><div className="quiz-sidebar-card"><div className="quiz-sidebar-title">{attempt.exam_name}</div><div className="quiz-sidebar-meta">{attempt.participant_name} · {attempt.questions.length} 道题</div><div className={`quiz-timer ${remaining < 120 ? "warning" : ""}`}><Clock3 size={16} />{timerText}</div><div className="question-nav">{attempt.questions.map((item, index) => { const value = answers[item.id]; const done = value && (value.selected.length > 0 || value.text.trim()); return <button className={`${done ? "done" : ""} ${index === current ? "current" : ""}`} key={item.id} onClick={() => setCurrent(index)} type="button">{index + 1}</button>; })}</div><p className="quiz-sidebar-meta">已答 {answeredCount} / {attempt.questions.length}</p><button className="button button-secondary quiz-early-submit" disabled={submitting} onClick={() => void handleSubmit(true)} type="button"><Send size={15} />提前交卷</button></div></aside>
      <main><div className="quiz-main-header"><div><div className="eyebrow">{attempt.book_title}</div><h1>{attempt.exam_name}</h1></div><span className="quiz-progress-label">第 {current + 1} / {attempt.questions.length} 题</span></div><div className="progress-track"><div className="progress-fill" style={{ width: `${(current + 1) / attempt.questions.length * 100}%` }} /></div><article className="question-card"><header className="question-card-header"><span className="question-number">QUESTION {String(current + 1).padStart(2, "0")}</span><span className="question-type">{questionTypeLabels[question.question_type]} · {question.max_score} 分</span></header><h2 className="question-prompt">{question.prompt}</h2><p className="question-hint">知识点：{question.knowledge_point}{question.question_type === "multiple" ? " · 本题有多个正确答案" : ""}</p>{question.question_type !== "short" ? <div className="option-list">{question.options.map((option) => { const selected = draft.selected.includes(option.id); return <label className={`option-label ${selected ? "selected" : ""}`} key={option.id}><input checked={selected} name={question.id} onChange={() => selectOption(question, option.id)} type={question.question_type === "single" ? "radio" : "checkbox"} /><span className="option-id">{option.id}</span><span className="option-text">{option.text}</span></label>; })}</div> : <textarea className="answer-textarea" onChange={(event) => setAnswers((currentAnswers) => ({ ...currentAnswers, [question.id]: { ...(currentAnswers[question.id] || { selected: [] }), text: event.target.value } }))} placeholder="请用自己的语言作答……" value={draft.text} />}</article><footer className="quiz-footer"><button className="button button-secondary" disabled={current === 0} onClick={() => setCurrent((index) => index - 1)} type="button"><ArrowLeft size={15} />上一题</button>{current < attempt.questions.length - 1 ? <button className="button button-primary" onClick={() => setCurrent((index) => index + 1)} type="button">下一题<ArrowRight size={15} /></button> : <button className="button button-primary" disabled={submitting} onClick={() => void handleSubmit()} type="button"><Send size={15} />{submitting ? "正在交卷……" : "提交答卷"}</button>}</footer>{answeredCount === attempt.questions.length && current < attempt.questions.length - 1 && <div className="public-submit-ready"><button className="button button-quiet" onClick={() => void handleSubmit()} type="button"><CheckCircle2 size={15} />全部作答，直接交卷</button></div>}</main>
    </div>
  </div>;
}
