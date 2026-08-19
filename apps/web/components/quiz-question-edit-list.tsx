"use client";

import { AlertTriangle, CheckCircle2, LoaderCircle, RotateCcw, Save } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { ApiError, regenerateQuizQuestion, updateQuizQuestion } from "@/lib/api";
import type { Question, QuestionUpdatePayload } from "@/lib/types";

const OPTION_IDS = ["A", "B", "C", "D"] as const;

const questionTypeLabels: Record<Question["question_type"], string> = {
  single: "单项选择题",
  multiple: "多项选择题",
  short: "问答题",
};

type QuizQuestionEditListProps = {
  quizId: string;
  questions: Question[];
  onSaved: (question: Question) => void;
};

export function QuizQuestionEditList({ quizId, questions, onSaved }: QuizQuestionEditListProps) {
  return (
    <div className="quiz-question-edit-list">
      {questions.map((question) => (
        <QuestionEditForm key={question.id} onSaved={onSaved} question={question} quizId={quizId} />
      ))}
    </div>
  );
}

function QuestionEditForm({
  quizId,
  question,
  onSaved,
}: {
  quizId: string;
  question: Question;
  onSaved: (question: Question) => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [confirmingRegeneration, setConfirmingRegeneration] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [prompt, setPrompt] = useState(question.prompt);
  const [knowledgePoint, setKnowledgePoint] = useState(question.knowledge_point);
  const [explanation, setExplanation] = useState(question.explanation || "");
  const [referenceAnswer, setReferenceAnswer] = useState(question.reference_answer || "");
  const [optionTexts, setOptionTexts] = useState<string[]>(
    OPTION_IDS.map((id) => question.options.find((option) => option.id === id)?.text || ""),
  );
  const [correctAnswers, setCorrectAnswers] = useState<string[]>(question.correct_answers || []);

  useEffect(() => {
    setPrompt(question.prompt);
    setKnowledgePoint(question.knowledge_point);
    setExplanation(question.explanation || "");
    setReferenceAnswer(question.reference_answer || "");
    setOptionTexts(OPTION_IDS.map((id) => question.options.find((option) => option.id === id)?.text || ""));
    setCorrectAnswers(question.correct_answers || []);
    setError("");
  }, [question]);

  const canSave = useMemo(() => {
    if (!prompt.trim() || !knowledgePoint.trim()) return false;
    if (question.question_type === "short") {
      return Boolean(referenceAnswer.trim());
    }
    return optionTexts.every((text) => text.trim()) && correctAnswers.length > 0;
  }, [correctAnswers.length, knowledgePoint, optionTexts, prompt, question.question_type, referenceAnswer]);

  function toggleAnswer(optionId: string) {
    setSaved(false);
    if (question.question_type === "single") {
      setCorrectAnswers([optionId]);
      return;
    }
    setCorrectAnswers((current) =>
      current.includes(optionId)
        ? current.filter((item) => item !== optionId)
        : [...current, optionId],
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSave) return;
    setSubmitting(true);
    setError("");
    setSaved(false);
    const payload: QuestionUpdatePayload = {
      prompt: prompt.trim(),
      knowledge_point: knowledgePoint.trim(),
      explanation: explanation.trim() || null,
    };
    if (question.question_type === "short") {
      payload.reference_answer = referenceAnswer.trim();
    } else {
      payload.options = OPTION_IDS.map((id, index) => ({ id, text: optionTexts[index].trim() }));
      payload.correct_answers = OPTION_IDS.filter((id) => correctAnswers.includes(id));
    }
    try {
      const nextQuestion = await updateQuizQuestion(quizId, question.id, payload);
      onSaved(nextQuestion);
      setSaved(true);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "保存失败");
    } finally {
      setSubmitting(false);
    }
  }

  function openRegenerationConfirm() {
    if (submitting || regenerating) return;
    setConfirmingRegeneration(true);
  }

  function closeRegenerationConfirm() {
    if (regenerating) return;
    setConfirmingRegeneration(false);
  }

  async function confirmRegenerate() {
    if (submitting || regenerating) return;
    setConfirmingRegeneration(false);
    setRegenerating(true);
    setError("");
    setSaved(false);
    try {
      const nextQuestion = await regenerateQuizQuestion(quizId, question.id);
      onSaved(nextQuestion);
      setSaved(true);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "重出失败");
    } finally {
      setRegenerating(false);
    }
  }

  return (
    <form className="question-edit-form" onSubmit={(event) => void handleSubmit(event)}>
      <div className="question-card-header">
        <span className="question-number">第 {question.position} 题 · {question.knowledge_point}</span>
        <div className="question-card-actions">
          <span className="question-type">{questionTypeLabels[question.question_type]}</span>
          <button
            className="button button-secondary question-edit-trigger"
            disabled={submitting || regenerating}
            onClick={openRegenerationConfirm}
            title="重出本题"
            type="button"
          >
            {regenerating ? <LoaderCircle className="spin" size={14} /> : <RotateCcw size={14} />}
            <span>重出本题</span>
          </button>
        </div>
      </div>
      {error && <div className="toast-error">{error}</div>}
      {saved && <div className="question-edit-saved"><CheckCircle2 size={14} />已保存</div>}
      <div className="form-grid question-editor-grid">
        <label className="field field-full">
          <span>题干</span>
          <textarea
            onChange={(event) => {
              setPrompt(event.target.value);
              setSaved(false);
            }}
            required
            value={prompt}
          />
        </label>
        <label className="field">
          <span>知识点</span>
          <input
            onChange={(event) => {
              setKnowledgePoint(event.target.value);
              setSaved(false);
            }}
            required
            value={knowledgePoint}
          />
        </label>
        <label className="field">
          <span>解析说明</span>
          <textarea
            onChange={(event) => {
              setExplanation(event.target.value);
              setSaved(false);
            }}
            value={explanation}
          />
        </label>
        {question.question_type === "short" ? (
          <label className="field field-full">
            <span>标准答案</span>
            <textarea
              onChange={(event) => {
                setReferenceAnswer(event.target.value);
                setSaved(false);
              }}
              placeholder="请输入人工修正后的参考答案"
              required
              value={referenceAnswer}
            />
          </label>
        ) : (
          <>
            <div className="field field-full">
              <span>选项内容</span>
              <div className="question-option-list">
                {OPTION_IDS.map((optionId, index) => (
                  <div className="question-option-row" key={optionId}>
                    <span className="question-option-id">{optionId}</span>
                    <input
                      onChange={(event) => {
                        setOptionTexts((current) => {
                          const next = [...current];
                          next[index] = event.target.value;
                          return next;
                        });
                        setSaved(false);
                      }}
                      placeholder={`选项 ${optionId}`}
                      required
                      value={optionTexts[index]}
                    />
                  </div>
                ))}
              </div>
            </div>
            <div className="field field-full">
              <span>标准答案</span>
              <div className="question-answer-list">
                {OPTION_IDS.map((optionId, index) => {
                  const selected = correctAnswers.includes(optionId);
                  return (
                    <label className={`question-answer-choice${selected ? " selected" : ""}`} key={optionId}>
                      <input
                        checked={selected}
                        name={`correct-${question.id}`}
                        onChange={() => toggleAnswer(optionId)}
                        type={question.question_type === "single" ? "radio" : "checkbox"}
                      />
                      <span className="question-answer-id">{optionId}</span>
                      <span className="question-answer-text">
                        {optionTexts[index].trim() || `选项 ${optionId}`}
                      </span>
                    </label>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>
      <div className="question-edit-form-actions">
        <button className="button button-primary" disabled={submitting || !canSave} type="submit">
          <Save size={15} />
          {submitting ? "正在保存……" : "保存本题"}
        </button>
      </div>
      {confirmingRegeneration && (
        <div
          className="modal-backdrop"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) closeRegenerationConfirm();
          }}
          role="presentation"
        >
          <section aria-labelledby={`regenerate-${question.id}-title`} aria-modal="true" className="modal-panel confirm-modal" role="dialog">
            <div className="confirm-icon"><AlertTriangle size={22} /></div>
            <h2 id={`regenerate-${question.id}-title`}>确认重新出题</h2>
            <p>系统会重新生成这道题的题干、选项、标准答案和解析，当前手工修改会被覆盖。确认继续吗？</p>
            <div className="modal-actions">
              <button className="button button-secondary" disabled={regenerating} onClick={closeRegenerationConfirm} type="button">取消</button>
              <button className="button button-danger" disabled={regenerating} onClick={() => void confirmRegenerate()} type="button">
                {regenerating ? <LoaderCircle className="spin" size={15} /> : <RotateCcw size={15} />}
                {regenerating ? "正在重出……" : "确认重新出题"}
              </button>
            </div>
          </section>
        </div>
      )}
    </form>
  );
}
