"use client";

import { ArrowRight, BookOpenText, Clock3, ListChecks, ShieldCheck, UserRound } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ErrorState } from "@/components/ui";
import { ApiError, getPublicExam, startPublicExam } from "@/lib/api";
import { readExamAccess, saveExamAccess } from "@/lib/exam-access";
import type { PublicExam } from "@/lib/types";

const difficultyLabels: Record<string, string> = { easy: "基础", medium: "适中", hard: "深入" };
const unavailableMessages: Record<string, string> = {
  stopped: "分享者已经停止这场考试。",
  source_deleted: "这场考试关联的原试卷已经删除。",
  expired: "这场考试已经过期。",
};

export default function PublicExamEntryPage() {
  const params = useParams<{ shareCode: string }>();
  const router = useRouter();
  const [exam, setExam] = useState<PublicExam | null>(null);
  const [participantName, setParticipantName] = useState("");
  const [savedAttemptId, setSavedAttemptId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const saved = readExamAccess(params.shareCode);
    setSavedAttemptId(saved?.attemptId || null);
    getPublicExam(params.shareCode)
      .then((data) => {
        setExam(data);
        setParticipantName(data.participant_name || "");
      })
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "考试链接加载失败"))
      .finally(() => setLoading(false));
  }, [params.shareCode]);

  function openAttempt(attemptId: string, status?: string | null) {
    const segment = status && status !== "in_progress" ? "results" : "attempts";
    router.push(`/exams/${params.shareCode}/${segment}/${attemptId}`);
  }

  async function handleStart() {
    if (!exam) return;
    if (!exam.authenticated && participantName.trim().length < 2) {
      setError("请填写 2-50 个字符的答题名称");
      return;
    }
    setStarting(true);
    setError("");
    try {
      const attempt = await startPublicExam(params.shareCode, exam.authenticated ? undefined : participantName.trim());
      saveExamAccess(params.shareCode, { attemptId: attempt.id, token: attempt.access_token });
      openAttempt(attempt.id, attempt.status);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "考试开始失败");
      setStarting(false);
    }
  }

  if (loading) return <div className="public-exam-center"><div className="loading-state">正在读取考试信息……</div></div>;
  if (!exam) return <div className="public-exam-center"><ErrorState message={error || "考试链接不存在"} /></div>;

  const existingAttemptId = exam.existing_attempt_id || savedAttemptId;
  const unavailable = exam.status !== "active";
  return (
    <div className="public-exam-page">
      <header className="public-exam-brand"><span className="brand-mark">卷</span><div><strong>回卷</strong><span>分享考试</span></div></header>
      <main className="public-exam-entry">
        <div className="public-exam-heading"><span className={`exam-status exam-status-${exam.status}`}>{exam.status === "active" ? "可以答题" : "当前不可答题"}</span><h1>{exam.name}</h1><p>{exam.book_title}{exam.book_author ? ` · ${exam.book_author}` : ""}</p></div>
        <div className="public-exam-facts">
          <div><BookOpenText size={18} /><span><small>试卷</small>{exam.quiz_title}</span></div>
          <div><ListChecks size={18} /><span><small>题目构成</small>{exam.question_count} 题 · 单选 {exam.single_count} · 多选 {exam.multiple_count} · 问答 {exam.short_count}</span></div>
          <div><Clock3 size={18} /><span><small>预计用时</small>{exam.duration_minutes} 分钟 · {difficultyLabels[exam.difficulty] || exam.difficulty}难度</span></div>
          <div><UserRound size={18} /><span><small>分享者</small>{exam.owner_display_name}</span></div>
        </div>

        {error && <div className="toast-error">{error}</div>}
        {existingAttemptId ? <div className="public-exam-action"><div><strong>{exam.existing_attempt_status === "completed" ? "你已经完成这场考试" : "发现尚未结束的答题记录"}</strong><span>{unavailable ? "分享已经停止，但已开始的答卷仍可继续完成。" : "同一考试只保留一份有效答卷。"}</span></div><button className="button button-primary" onClick={() => openAttempt(existingAttemptId, exam.existing_attempt_status)} type="button">{exam.existing_attempt_status === "completed" ? "查看结果" : "继续答题"}<ArrowRight size={15} /></button></div> : unavailable ? <div className="public-exam-unavailable">{unavailableMessages[exam.status] || "这场考试当前不能开始答题。"}</div> : <div className="public-exam-action">
          <div className="public-participant-field"><label htmlFor="participant-name">答题身份</label>{exam.authenticated ? <div className="signed-participant"><UserRound size={15} />{exam.participant_name}<span>登录用户</span></div> : <input autoComplete="name" id="participant-name" maxLength={50} onChange={(event) => setParticipantName(event.target.value)} placeholder="填写你的答题名称" value={participantName} />}</div>
          <button className="button button-primary" disabled={starting} onClick={() => void handleStart()} type="button">{starting ? "正在准备……" : "开始答题"}<ArrowRight size={15} /></button>
        </div>}
        <div className="public-privacy-note"><ShieldCheck size={16} /><span>你的答题名称、答案、成绩和提交时间将对考试分享者可见。公开结果不会展示书籍 PDF 的文件名、页码或原文摘录。</span></div>
      </main>
    </div>
  );
}
