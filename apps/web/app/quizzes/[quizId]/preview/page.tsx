"use client";

import { AlertTriangle, ArrowLeft, Check, CheckCircle2, Code2, Eye, FileQuestion, LibraryBig, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ErrorState, SourceModeNotice } from "@/components/ui";
import { ApiError, getQuizExport, promoteQuestionToBank } from "@/lib/api";
import type { Question, Quiz } from "@/lib/types";

const questionTypeLabels: Record<Question["question_type"], string> = {
  single: "单项选择题",
  multiple: "多项选择题",
  short: "问答题",
};

export default function QuizPreviewPage() {
  const params = useParams<{ quizId: string }>();
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [bankedQuestionIds, setBankedQuestionIds] = useState<Set<string>>(new Set());
  const [promotingQuestionIds, setPromotingQuestionIds] = useState<Set<string>>(new Set());
  const [bulkPromoting, setBulkPromoting] = useState(false);
  const [bulkProgress, setBulkProgress] = useState({ completed: 0, total: 0 });
  const [bankError, setBankError] = useState("");

  useEffect(() => {
    getQuizExport(params.quizId)
      .then((payload) => {
        setQuiz(payload.quiz);
        setBankedQuestionIds(new Set(payload.quiz.questions.filter((question) => question.question_bank_entry_id).map((question) => question.id)));
      })
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "试卷预览加载失败"))
      .finally(() => setLoading(false));
  }, [params.quizId]);

  if (loading) return <div className="page-wrap"><div className="loading-state">正在打开试卷预览……</div></div>;
  if (!quiz) return <div className="page-wrap"><ErrorState message={error || "未找到这套试卷"} /></div>;

  const quizId = quiz.id;
  const remainingQuestions = quiz.questions.filter((question) => !bankedQuestionIds.has(question.id));

  async function promoteOne(question: Question) {
    if (bankedQuestionIds.has(question.id) || promotingQuestionIds.has(question.id)) return;
    setPromotingQuestionIds((current) => new Set(current).add(question.id));
    setBankError("");
    try {
      await promoteQuestionToBank(quizId, question.id);
      setBankedQuestionIds((current) => new Set(current).add(question.id));
    } catch (reason: unknown) {
      setBankError(reason instanceof ApiError ? reason.message : `第 ${question.position} 题回流失败`);
    } finally {
      setPromotingQuestionIds((current) => {
        const next = new Set(current);
        next.delete(question.id);
        return next;
      });
    }
  }

  async function promoteAll() {
    if (remainingQuestions.length === 0 || bulkPromoting) return;
    if (!window.confirm(`确认将这套试卷剩余的 ${remainingQuestions.length} 道题全部加入题库吗？已有题库题目会自动跳过。`)) return;
    setBulkPromoting(true);
    setBankError("");
    setBulkProgress({ completed: 0, total: remainingQuestions.length });
    const failures: string[] = [];
    for (const question of remainingQuestions) {
      setPromotingQuestionIds((current) => new Set(current).add(question.id));
      try {
        await promoteQuestionToBank(quizId, question.id);
        setBankedQuestionIds((current) => new Set(current).add(question.id));
      } catch (reason: unknown) {
        failures.push(`第 ${question.position} 题：${reason instanceof ApiError ? reason.message : "回流失败"}`);
      } finally {
        setPromotingQuestionIds((current) => {
          const next = new Set(current);
          next.delete(question.id);
          return next;
        });
        setBulkProgress((current) => ({ ...current, completed: current.completed + 1 }));
      }
    }
    if (failures.length > 0) setBankError(`已完成 ${remainingQuestions.length - failures.length}/${remainingQuestions.length} 道题。${failures.join("；")}`);
    setBulkPromoting(false);
  }

  return (
    <div className="page-wrap">
      <Link className="back-link" href={`/quizzes/${quiz.id}`}><ArrowLeft size={14} />返回试卷概览</Link>
      {error && <div className="toast-error">{error}</div>}
      <SourceModeNotice sourceMode={quiz.source_mode} />
      <header className="page-header quiz-preview-header">
        <div><div className="eyebrow"><Eye size={13} />Quiz preview</div><h1 className="page-title">{quiz.title}</h1><p className="page-description">快速查看整套试卷的题目、答案和解析，不会创建复习记录。</p></div>
        <div className="quiz-overview-actions"><Link className="button button-secondary" href={`/quizzes/${quiz.id}/generation-debug`}><Code2 size={15} />查看出题过程</Link><Link className="button button-secondary" href={`/quizzes/${quiz.id}/edit?return_to=preview`}><LibraryBig size={15} />管理题库题目</Link><Link className="button button-secondary" href={`/quizzes/${quiz.id}`}><ArrowLeft size={15} />返回概览</Link></div>
      </header>

      <div className="quiz-preview-bank-toolbar"><div className="quiz-preview-summary"><FileQuestion size={16} /><strong>{quiz.questions.length} 道题</strong><span>{quiz.max_score} 分 · {quiz.duration_minutes} 分钟</span></div><button className="button button-primary" disabled={bulkPromoting || remainingQuestions.length === 0} onClick={() => void promoteAll()} type="button">{bulkPromoting ? <><LoaderCircle className="spin" size={15} />正在回流 {bulkProgress.completed}/{bulkProgress.total}</> : remainingQuestions.length === 0 ? <><Check size={15} />已全部回流题库</> : <><LibraryBig size={15} />一键回流剩余 {remainingQuestions.length} 题</>}</button></div>
      {bankError && <div className="quiz-preview-bank-error"><AlertTriangle size={16} /><span>{bankError}</span></div>}
      <section className="quiz-preview-list">
        {quiz.questions.map((question) => <PreviewQuestion key={question.id} question={question} banked={bankedQuestionIds.has(question.id)} promoting={promotingQuestionIds.has(question.id)} disabled={bulkPromoting} onPromote={() => void promoteOne(question)} />)}
      </section>
    </div>
  );
}

function PreviewQuestion({ question, banked, promoting, disabled, onPromote }: { question: Question; banked: boolean; promoting: boolean; disabled: boolean; onPromote: () => void }) {
  const correctAnswers = new Set(question.correct_answers || []);
  return <article className="quiz-preview-question"><header className="quiz-preview-question-header"><div><span className="question-number">第 {question.position} 题</span><span className="question-type">{questionTypeLabels[question.question_type]}</span></div><div className="quiz-preview-question-header-actions"><strong>{question.max_score} 分</strong><button aria-label={banked ? `第${question.position}题已在题库` : `将第${question.position}题加入题库`} className={`button button-quiet quiz-preview-bank-action${banked ? " banked" : ""}`} disabled={banked || promoting || disabled} onClick={onPromote} title={banked ? "已在题库" : "加入题库"} type="button">{promoting ? <LoaderCircle className="spin" size={14} /> : banked ? <Check size={14} /> : <LibraryBig size={14} />}{banked ? "已在题库" : promoting ? "回流中" : "加入题库"}</button></div></header><h2>{question.prompt}</h2>{question.options.length > 0 && <ol className="quiz-preview-options">{question.options.map((option) => <li className={correctAnswers.has(option.id) ? "correct" : ""} key={option.id}><span>{option.id}</span>{option.text}{correctAnswers.has(option.id) && <CheckCircle2 size={14} />}</li>)}</ol>}<div className="quiz-preview-answer"><strong>正确答案</strong><span>{question.question_type === "short" ? "见下方参考答案" : (question.correct_answers || []).join("、") || "未设置"}</span></div>{question.explanation && <div className="quiz-preview-field"><strong>解析</strong><p>{question.explanation}</p></div>}<div className="quiz-preview-field"><strong>知识点</strong><p>{question.knowledge_point || "未设置"}</p></div>{question.reference_answer && <div className="quiz-preview-field"><strong>参考答案</strong><p>{question.reference_answer}</p></div>}{question.grading_rubric.length > 0 && <div className="quiz-preview-field"><strong>评分要点</strong><ul>{question.grading_rubric.map((item, index) => <li key={index}>{item.point}{item.score !== undefined ? `（${item.score} 分）` : ""}</li>)}</ul></div>}{question.source_evidence.length > 0 && <details className="quiz-preview-sources"><summary>查看来源依据（{question.source_evidence.length} 条）</summary>{question.source_evidence.map((source, index) => <div key={`${source.chunk_id || source.material_id || "source"}-${index}`}><span>{source.speaker || source.file_name || "可信来源"}</span><p>{source.excerpt}</p></div>)}</details>}</article>;
}
