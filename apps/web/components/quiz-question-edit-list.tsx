"use client";

import { AlertTriangle, CheckCircle2, LibraryBig, LoaderCircle, RotateCcw, Save } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { ApiError } from "@/lib/api";
import type { Question, QuestionBankEntry, QuestionUpdatePayload, QuizQualityReview, QuizQualityReviewResult } from "@/lib/types";

const OPTION_IDS = ["A", "B", "C", "D"] as const;

const questionTypeLabels: Record<Question["question_type"], string> = {
  single: "单项选择题",
  multiple: "多项选择题",
  short: "问答题",
};

type QuizQuestionEditListProps = {
  questions: Question[];
  onSaved: (question: Question) => void;
  onUpdateQuestion: (questionId: string, payload: QuestionUpdatePayload) => Promise<Question>;
  onRegenerateQuestion: (questionId: string) => Promise<Question>;
  qualityReviewResult?: QuizQualityReviewResult | null;
  onReviewQuestion?: (questionId: string) => Promise<QuizQualityReview>;
  onPromoteQuestion?: (questionId: string) => Promise<QuestionBankEntry>;
};

export function QuizQuestionEditList({
  questions,
  onSaved,
  onUpdateQuestion,
  onRegenerateQuestion,
  qualityReviewResult,
  onReviewQuestion,
  onPromoteQuestion,
}: QuizQuestionEditListProps) {
  return (
    <div className="quiz-question-edit-list">
      {questions.map((question) => (
        <QuestionEditForm
          key={question.id}
          onRegenerateQuestion={onRegenerateQuestion}
          onSaved={onSaved}
          onUpdateQuestion={onUpdateQuestion}
          question={question}
          qualityReview={qualityReviewResult?.question_reviews?.find((item) => item.question_position === question.position) || null}
          onReviewQuestion={onReviewQuestion}
          onPromoteQuestion={onPromoteQuestion}
        />
      ))}
    </div>
  );
}

function QuestionEditForm({
  question,
  onSaved,
  onUpdateQuestion,
  onRegenerateQuestion,
  qualityReview,
  onReviewQuestion,
  onPromoteQuestion,
}: {
  question: Question;
  onSaved: (question: Question) => void;
  onUpdateQuestion: (questionId: string, payload: QuestionUpdatePayload) => Promise<Question>;
  onRegenerateQuestion: (questionId: string) => Promise<Question>;
  qualityReview: QuizQualityReviewResult["question_reviews"][number] | null;
  onReviewQuestion?: (questionId: string) => Promise<QuizQualityReview>;
  onPromoteQuestion?: (questionId: string) => Promise<QuestionBankEntry>;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [banked, setBanked] = useState(Boolean(question.question_bank_entry_id));
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
    setBanked(Boolean(question.question_bank_entry_id));
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
      const nextQuestion = await onUpdateQuestion(question.id, payload);
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
      const nextQuestion = await onRegenerateQuestion(question.id);
      onSaved(nextQuestion);
      setSaved(true);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "重出失败");
    } finally {
      setRegenerating(false);
    }
  }

  async function handleReview() {
    if (!onReviewQuestion || reviewing || submitting || regenerating) return;
    setReviewing(true);
    setError("");
    try {
      await onReviewQuestion(question.id);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "本题审查失败");
    } finally {
      setReviewing(false);
    }
  }

  async function handlePromote() {
    if (!onPromoteQuestion || promoting || banked) return;
    if (!window.confirm("确认将这道题加入本资源题库吗？题目会保留当前版本，后续可在题库中继续修改。")) return;
    setPromoting(true);
    setError("");
    try {
      await onPromoteQuestion(question.id);
      setBanked(true);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "加入题库失败");
    } finally {
      setPromoting(false);
    }
  }

  return (
    <form className="question-edit-form" onSubmit={(event) => void handleSubmit(event)}>
      <div className="question-card-header">
        <span className="question-number">第 {question.position} 题 · {question.knowledge_point}</span>
        <div className="question-card-actions">
          <span className="question-type">{questionTypeLabels[question.question_type]}</span>
          {onPromoteQuestion && <button className="button button-secondary question-edit-trigger" disabled={submitting || regenerating || promoting || banked} onClick={() => void handlePromote()} title={banked ? "已加入题库" : "加入题库"} type="button"><LibraryBig size={14} /><span>{banked ? "已在题库" : promoting ? "加入中……" : "加入题库"}</span></button>}
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
      {(qualityReview || onReviewQuestion) && <QuestionQualityReviewCard review={qualityReview} reviewing={reviewing} onReview={onReviewQuestion ? () => void handleReview() : undefined} />}
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

const qualityReviewVerdictLabels: Record<"pass" | "needs_revision" | "high_risk", string> = {
  pass: "建议通过",
  needs_revision: "建议修改",
  high_risk: "高风险",
};

const qualityReviewCategoryLabels: Record<QuizQualityReviewResult["issues"][number]["category"], string> = {
  fact: "事实",
  answer: "答案",
  source: "来源",
  ambiguity: "歧义",
  duplicate: "重复",
  wording: "措辞",
  difficulty: "难度",
  other: "其他",
};

function QuestionQualityReviewCard({
  review,
  reviewing,
  onReview,
}: {
  review: QuizQualityReviewResult["question_reviews"][number] | null;
  reviewing: boolean;
  onReview?: () => void;
}) {
  if (!review) {
    return <aside className="question-quality-review"><div className="question-quality-review-heading"><div><strong>本题尚未审查</strong></div>{onReview && <button className="button button-quiet" disabled={reviewing} onClick={onReview} type="button"><RotateCcw size={14} />{reviewing ? "审查中……" : "审查本题"}</button>}</div><p className="question-quality-review-summary">保存题目后可以只针对本题发起模型审查。</p></aside>;
  }
  return <aside className={`question-quality-review ${review.verdict}`}>
    <div className="question-quality-review-heading"><div><strong>模型审查：{review.score}/100</strong><span className="question-quality-review-verdict">{qualityReviewVerdictLabels[review.verdict]}</span></div>{onReview && <button className="button button-quiet" disabled={reviewing} onClick={onReview} type="button"><RotateCcw size={14} />{reviewing ? "审查中……" : "重新审查本题"}</button>}</div>
    {review.summary && <p className="question-quality-review-summary">{review.summary}</p>}
    {review.issues.length > 0 ? <div className="question-quality-review-issues">{review.issues.map((issue, index) => <div className="question-quality-review-issue" key={`${issue.category}-${index}`}><div className="question-quality-review-issue-meta"><span>{qualityReviewCategoryLabels[issue.category]}</span><span>{issue.severity === "high" ? "高风险" : issue.severity === "medium" ? "建议修改" : "措辞优化"}</span></div><p><strong>问题：</strong>{issue.problem}</p><p><strong>修改建议：</strong>{issue.suggestion}</p>{issue.suggested_prompt && <p><strong>建议题干：</strong>{issue.suggested_prompt}</p>}{issue.suggested_options.length > 0 && <div className="question-quality-review-options"><strong>建议选项：</strong>{issue.suggested_options.map((option) => <span className={issue.suggested_correct_answers.includes(option.id) ? "correct" : ""} key={option.id}>{option.id}. {option.text}{issue.suggested_correct_answers.includes(option.id) ? "（答案）" : ""}</span>)}</div>}{issue.suggested_explanation && <p><strong>建议解析：</strong>{issue.suggested_explanation}</p>}{issue.suggested_knowledge_point && <p><strong>建议知识点：</strong>{issue.suggested_knowledge_point}</p>}{issue.suggested_reference_answer && <p><strong>建议参考答案：</strong>{issue.suggested_reference_answer}</p>}{issue.evidence && <p className="question-quality-review-evidence"><strong>审查依据：</strong>{issue.evidence}</p>}</div>)}</div> : <div className="question-quality-review-ok"><CheckCircle2 size={15} />未发现需要修改的问题</div>}
  </aside>;
}
