"use client";

import { PencilLine, X } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { ApiError, updateQuizQuestion } from "@/lib/api";
import type { Question, QuestionUpdatePayload } from "@/lib/types";

const OPTION_IDS = ["A", "B", "C", "D"] as const;

type QuestionEditorProps = {
  quizId: string;
  question: Question;
  onSaved: (question: Question) => void;
  className?: string;
};

export function QuestionEditor({ quizId, question, onSaved, className = "button button-secondary" }: QuestionEditorProps) {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [prompt, setPrompt] = useState(question.prompt);
  const [knowledgePoint, setKnowledgePoint] = useState(question.knowledge_point);
  const [explanation, setExplanation] = useState(question.explanation || "");
  const [referenceAnswer, setReferenceAnswer] = useState(question.reference_answer || "");
  const [optionTexts, setOptionTexts] = useState<string[]>(
    OPTION_IDS.map((id) => question.options.find((option) => option.id === id)?.text || ""),
  );
  const [correctAnswers, setCorrectAnswers] = useState<string[]>(question.correct_answers || []);

  useEffect(() => {
    if (!open) return;
    setPrompt(question.prompt);
    setKnowledgePoint(question.knowledge_point);
    setExplanation(question.explanation || "");
    setReferenceAnswer(question.reference_answer || "");
    setOptionTexts(OPTION_IDS.map((id) => question.options.find((option) => option.id === id)?.text || ""));
    setCorrectAnswers(question.correct_answers || []);
    setError("");
  }, [open, question]);

  const canSave = useMemo(() => {
    if (!prompt.trim() || !knowledgePoint.trim()) return false;
    if (question.question_type === "short") {
      return Boolean(referenceAnswer.trim());
    }
    return optionTexts.every((text) => text.trim()) && correctAnswers.length > 0;
  }, [correctAnswers.length, knowledgePoint, optionTexts, prompt, question.question_type, referenceAnswer]);

  function toggleAnswer(optionId: string) {
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
      const saved = await updateQuizQuestion(quizId, question.id, payload);
      onSaved(saved);
      setOpen(false);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "保存失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <button className={className} onClick={() => setOpen(true)} type="button">
        <PencilLine size={15} />
        编辑题目
      </button>
      {open && (
        <div
          className="modal-backdrop"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target && !submitting) setOpen(false);
          }}
          role="presentation"
        >
          <section
            aria-labelledby={`question-editor-title-${question.id}`}
            aria-modal="true"
            className="modal-panel question-editor-modal"
            role="dialog"
          >
            <div className="modal-heading">
              <div>
                <span className="eyebrow">Question editor</span>
                <h2 id={`question-editor-title-${question.id}`}>调整第 {question.position} 题</h2>
                <p>{question.question_type === "short" ? "问答题" : question.question_type === "multiple" ? "多选题" : "单选题"} · {question.knowledge_point}</p>
              </div>
              <button
                aria-label="关闭题目编辑弹窗"
                className="modal-close"
                disabled={submitting}
                onClick={() => setOpen(false)}
                title="关闭"
                type="button"
              >
                <X size={18} />
              </button>
            </div>
            {error && <div className="toast-error">{error}</div>}
            <form onSubmit={(event) => void handleSubmit(event)}>
              <div className="form-grid question-editor-grid">
                <label className="field field-full">
                  <span>题干</span>
                  <textarea
                    autoFocus
                    onChange={(event) => setPrompt(event.target.value)}
                    required
                    value={prompt}
                  />
                </label>
                <label className="field">
                  <span>知识点</span>
                  <input onChange={(event) => setKnowledgePoint(event.target.value)} required value={knowledgePoint} />
                </label>
                <label className="field">
                  <span>解析说明</span>
                  <textarea onChange={(event) => setExplanation(event.target.value)} value={explanation} />
                </label>
                {question.question_type === "short" ? (
                  <label className="field field-full">
                    <span>标准答案</span>
                    <textarea
                      onChange={(event) => setReferenceAnswer(event.target.value)}
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
                              onChange={(event) => setOptionTexts((current) => {
                                const next = [...current];
                                next[index] = event.target.value;
                                return next;
                              })}
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
              <div className="modal-actions">
                <button className="button button-secondary" disabled={submitting} onClick={() => setOpen(false)} type="button">
                  取消
                </button>
                <button className="button button-primary" disabled={submitting || !canSave} type="submit">
                  <PencilLine size={15} />
                  {submitting ? "正在保存……" : "保存修改"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </>
  );
}
