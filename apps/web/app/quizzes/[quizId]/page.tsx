"use client";

import { ArrowLeft, CheckCircle2, Clock3, Code2, Download, Eye, FileQuestion, Play } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ErrorState, SourceModeNotice } from "@/components/ui";
import { ApiError, getQuiz, getQuizExport, startReview } from "@/lib/api";
import type { Quiz } from "@/lib/types";

const questionTypeLabels = {
  single: "单项选择题",
  multiple: "多项选择题",
  short: "问答题",
} as const;

export default function QuizOverviewPage() {
  const params = useParams<{ quizId: string }>();
  const router = useRouter();
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [starting, setStarting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getQuiz(params.quizId)
      .then(setQuiz)
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "试卷加载失败"))
      .finally(() => setLoading(false));
  }, [params.quizId]);

  const overview = useMemo(() => {
    if (!quiz) return [];
    return (["single", "multiple", "short"] as const)
      .map((type) => {
        const items = quiz.questions.filter((question) => question.question_type === type);
        return {
          type,
          label: questionTypeLabels[type],
          count: items.length,
          score: items.reduce((sum, question) => sum + question.max_score, 0),
        };
      })
      .filter((item) => item.count > 0);
  }, [quiz]);

  async function handleStart() {
    if (!quiz) return;
    setStarting(true);
    setError("");
    try {
      const review = await startReview(quiz.id);
      router.push(`/reviews/${review.id}`);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "复习任务创建失败");
      setStarting(false);
    }
  }

  async function handleExport() {
    if (!quiz) return;
    setExporting(true);
    setError("");
    try {
      const payload = await getQuizExport(quiz.id);
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${quiz.title.replace(/[\\/:*?"<>|]/g, "_")}-题目答案校验.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "试卷导出失败");
    } finally {
      setExporting(false);
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在打开试卷概览……</div></div>;
  if (!quiz) return <div className="page-wrap"><ErrorState message={error || "未找到这套试卷"} /></div>;

  return (
    <div className="page-wrap">
      <Link className="back-link" href={`/books/${quiz.book_id}`}><ArrowLeft size={14} />返回《{quiz.book_title}》</Link>
      {error && <div className="toast-error">{error}</div>}
      <SourceModeNotice sourceMode={quiz.source_mode} />
      <header className="page-header">
        <div><div className="eyebrow">Review paper</div><h1 className="page-title">{quiz.title}</h1><p className="page-description">先查看这套试卷的概览，确认后再开始答题。只有点击开始按钮后才会创建复习记录。</p></div>
        <div className="quiz-overview-actions"><Link className="button button-secondary" href={`/quizzes/${quiz.id}/generation-debug`}><Code2 size={15} />查看出题过程</Link><Link className="button button-secondary" href={`/quizzes/${quiz.id}/preview`}><Eye size={15} />预览题目与答案</Link><button className="button button-secondary" disabled={exporting} onClick={() => void handleExport()} type="button"><Download size={15} />{exporting ? "正在导出……" : "导出题目与答案"}</button><button className="button button-primary" disabled={starting} onClick={() => void handleStart()} type="button"><Play size={15} />{starting ? "正在进入……" : "开始答题"}</button></div>
      </header>

      <div className="quiz-choice-layout">
        <section className="content-panel">
          <div className="section-title"><h2>试卷概述</h2><span>题型分布与总分</span></div>
          <div className="quiz-choice-items">
            {overview.map((item) => <div className="quiz-choice-item" key={item.type}><div className="count-icon"><FileQuestion size={17} /></div><div><strong>{item.label}</strong><span>{item.count} 道 · {item.score} 分</span></div></div>)}
          </div>
          <div className="quiz-choice-note"><CheckCircle2 size={16} />{quiz.source_mode === "model_knowledge" ? "本套试卷基于模型知识生成，没有 PDF 页码和逐句原文依据。" : quiz.source_mode === "combined" ? "每道题都保留对应的 PDF 或可信台词来源。" : quiz.source_mode === "material" ? "每道题都保留对应的可信台词来源。" : "每道题都保留对应的 PDF 页码和原文依据。"}</div>
        </section>
        <aside className="quiz-settings-summary">
          <div className="eyebrow">本套试卷</div>
          <strong>{quiz.questions.length} 道题 · {quiz.max_score} 分</strong>
          <p>点击开始答题后，系统才会创建本次复习记录并进入答题详情页。</p>
          <dl><div><dt>目标时长</dt><dd><Clock3 size={13} />{quiz.duration_minutes} 分钟</dd></div><div><dt>难度</dt><dd>{quiz.difficulty === "easy" ? "基础" : quiz.difficulty === "hard" ? "深入" : "适中"}</dd></div><div><dt>复习记录</dt><dd>开始后生成</dd></div></dl>
        </aside>
      </div>
    </div>
  );
}
