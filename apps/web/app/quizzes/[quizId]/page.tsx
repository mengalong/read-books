"use client";

import { ArrowLeft, ArrowRight, CheckCircle2, Clock3, Send } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ErrorState, EvidenceList } from "@/components/ui";
import { ApiError, getQuiz, submitQuiz } from "@/lib/api";
import type { Question, Quiz } from "@/lib/types";

type DraftAnswer = { selected: string[]; text: string };

function questionTypeLabel(type: Question["question_type"]) {
  return { single: "单项选择", multiple: "多项选择", short: "问答" }[type];
}

export default function QuizPage() {
  const params = useParams<{ quizId: string }>();
  const router = useRouter();
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [answers, setAnswers] = useState<Record<string, DraftAnswer>>({});
  const [current, setCurrent] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getQuiz(params.quizId)
      .then((data) => {
        if (data.status === "submitted") router.replace(`/quizzes/${data.id}/result`);
        setQuiz(data);
        setAnswers(Object.fromEntries(data.questions.map((question) => [question.id, { selected: [], text: "" }])));
      })
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "测试加载失败"))
      .finally(() => setLoading(false));
  }, [params.quizId, router]);

  useEffect(() => {
    if (!quiz || quiz.status === "submitted") return;
    const timer = window.setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [quiz]);

  const question = quiz?.questions[current];
  const answeredCount = useMemo(() => Object.values(answers).filter((answer) => answer.selected.length > 0 || answer.text.trim().length > 0).length, [answers]);
  const totalSeconds = (quiz?.duration_minutes || 15) * 60;
  const remaining = Math.max(0, totalSeconds - elapsed);
  const timerText = `${String(Math.floor(remaining / 60)).padStart(2, "0")}:${String(remaining % 60).padStart(2, "0")}`;

  function selectOption(question: Question, optionId: string) {
    setAnswers((currentAnswers) => {
      const previous = currentAnswers[question.id];
      const selected = question.question_type === "single"
        ? [optionId]
        : previous.selected.includes(optionId)
          ? previous.selected.filter((id) => id !== optionId)
          : [...previous.selected, optionId];
      return { ...currentAnswers, [question.id]: { ...previous, selected } };
    });
  }

  async function handleSubmit() {
    if (!quiz) return;
    const unanswered = quiz.questions.length - answeredCount;
    if (unanswered && !window.confirm(`还有 ${unanswered} 道题未作答，仍然提交吗？`)) return;
    setSubmitting(true);
    setError("");
    try {
      await submitQuiz(quiz.id, {
        elapsed_seconds: elapsed,
        answers: quiz.questions.map((item) => ({ question_id: item.id, selected_answers: answers[item.id].selected, text_answer: answers[item.id].text })),
      });
      router.push(`/quizzes/${quiz.id}/result`);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "提交失败，请稍后重试");
      setSubmitting(false);
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在装订试卷……</div></div>;
  if (!quiz || !question) return <div className="page-wrap"><ErrorState message={error || "未找到这套测试"} /></div>;

  const draft = answers[question.id] || { selected: [], text: "" };
  return (
    <div className="page-wrap">
      {error && <div className="toast-error">{error}</div>}
      <div className="quiz-layout">
        <aside className="quiz-sidebar">
          <div className="quiz-sidebar-card">
            <div className="quiz-sidebar-title">{quiz.title}</div>
            <div className="quiz-sidebar-meta">{quiz.book_title} · {quiz.questions.length} 道题</div>
            <div className={`quiz-timer ${remaining < 120 ? "warning" : ""}`}><Clock3 size={16} />{timerText}</div>
            <div className="question-nav">{quiz.questions.map((item, index) => {
              const draftItem = answers[item.id];
              const done = draftItem && (draftItem.selected.length > 0 || draftItem.text.trim());
              return <button aria-label={`前往第${index + 1}题`} className={`${done ? "done" : ""} ${index === current ? "current" : ""}`} key={item.id} onClick={() => setCurrent(index)} type="button">{index + 1}</button>;
            })}</div>
            <p className="quiz-sidebar-meta" style={{ marginTop: 13 }}>已答 {answeredCount} / {quiz.questions.length}</p>
          </div>
        </aside>

        <main>
          <div className="quiz-main-header"><div><Link className="back-link" href={`/books/${quiz.book_id}`} style={{ marginBottom: 8 }}><ArrowLeft size={13} />暂时离开</Link><h1>{quiz.book_title}</h1></div><span className="quiz-progress-label">第 {current + 1} / {quiz.questions.length} 题</span></div>
          <div className="progress-track"><div className="progress-fill" style={{ width: `${((current + 1) / quiz.questions.length) * 100}%` }} /></div>
          <article className="question-card" style={{ marginTop: 15 }}>
            <header className="question-card-header"><span className="question-number">QUESTION {String(current + 1).padStart(2, "0")}</span><span className="question-type">{questionTypeLabel(question.question_type)} · {question.max_score} 分</span></header>
            <h2 className="question-prompt">{question.prompt}</h2>
            <p className="question-hint">知识点：{question.knowledge_point}{question.question_type === "multiple" ? " · 本题有多个正确答案" : ""}</p>

            {question.question_type !== "short" ? <div className="option-list">{question.options.map((option) => {
              const selected = draft.selected.includes(option.id);
              return <label className={`option-label ${selected ? "selected" : ""}`} key={option.id}><input checked={selected} name={question.id} onChange={() => selectOption(question, option.id)} type={question.question_type === "single" ? "radio" : "checkbox"} /><span className="option-id">{option.id}</span><span className="option-text">{option.text}</span></label>;
            })}</div> : <textarea className="answer-textarea" onChange={(event) => setAnswers((currentAnswers) => ({ ...currentAnswers, [question.id]: { ...currentAnswers[question.id], text: event.target.value } }))} placeholder="请用自己的语言回答，不要求逐字复述原文……" value={draft.text} />}

            <EvidenceList evidence={question.source_evidence} />
          </article>
          <footer className="quiz-footer">
            <button className="button button-secondary" disabled={current === 0} onClick={() => setCurrent((index) => index - 1)} type="button"><ArrowLeft size={15} />上一题</button>
            {current < quiz.questions.length - 1 ? <button className="button button-primary" onClick={() => setCurrent((index) => index + 1)} type="button">下一题<ArrowRight size={15} /></button> : <button className="button button-primary" disabled={submitting} onClick={() => void handleSubmit()} type="button"><Send size={15} />{submitting ? "评分中……" : "提交测试"}</button>}
          </footer>
          {answeredCount === quiz.questions.length && current < quiz.questions.length - 1 && <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}><button className="button button-quiet" onClick={() => void handleSubmit()} type="button"><CheckCircle2 size={15} />全部作答，直接提交</button></div>}
        </main>
      </div>
    </div>
  );
}
