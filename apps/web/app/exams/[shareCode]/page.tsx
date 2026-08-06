"use client";

import { ArrowRight, BookOpenText, CalendarClock, Clock3, ListChecks, LogOut, ScanLine, ShieldCheck, UserRound } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ErrorState } from "@/components/ui";
import { ApiError, getPublicExam, getWechatLoginUrl, logoutWechat, startPublicExam } from "@/lib/api";
import { readExamAccess, saveExamAccess } from "@/lib/exam-access";
import { formatDateTime } from "@/lib/format";
import type { PublicExam } from "@/lib/types";

const difficultyLabels: Record<string, string> = { easy: "基础", medium: "适中", hard: "深入" };
const unavailableMessages: Record<string, string> = {
  stopped: "分享者已经停止这场考试。",
  source_deleted: "这场考试关联的原试卷已经删除。",
  expired: "你来晚了，考试已经结束",
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
    const wechatError = new URLSearchParams(window.location.search).get("wechat_error");
    if (wechatError) setError(wechatError);
    getPublicExam(params.shareCode, saved?.token)
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
    if (exam.identity_type === "anonymous" && participantName.trim().length < 2) {
      setError("请填写 2-50 个字符的答题名称");
      return;
    }
    setStarting(true);
    setError("");
    try {
      const attempt = await startPublicExam(params.shareCode, exam.identity_type === "anonymous" ? participantName.trim() : undefined);
      saveExamAccess(params.shareCode, { attemptId: attempt.id, token: attempt.access_token });
      openAttempt(attempt.id, attempt.status);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "考试开始失败");
      setStarting(false);
    }
  }

  function handleWechatLogin() {
    window.location.assign(getWechatLoginUrl(params.shareCode));
  }

  async function handleWechatLogout() {
    setError("");
    try {
      await logoutWechat();
      window.location.reload();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "微信身份退出失败");
    }
  }

  if (loading) return <div className="public-exam-center"><div className="loading-state">正在读取考试信息……</div></div>;
  if (!exam) return <div className="public-exam-center"><ErrorState message={error || "考试链接不存在"} /></div>;

  const existingAttemptId = exam.existing_attempt_id || savedAttemptId;
  const unavailable = exam.status !== "active";
  const historicalAttempt = Boolean(existingAttemptId && exam.existing_attempt_status && exam.existing_attempt_status !== "in_progress");
  const canOpenExisting = Boolean(existingAttemptId && (historicalAttempt || exam.status !== "expired"));
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
          <div><CalendarClock size={18} /><span><small>答题期限</small>{exam.expires_at ? formatDateTime(exam.expires_at) : "长期有效"}</span></div>
        </div>

        {error && <div className="toast-error">{error}</div>}
        {canOpenExisting && existingAttemptId ? <div className="public-exam-action"><div><strong>{historicalAttempt ? "你参加过这场考试" : "发现尚未结束的答题记录"}</strong><span>{historicalAttempt ? "可以继续查看之前的答题记录和学习报告。" : unavailable ? "分享已经停止，但已开始的答卷仍可继续完成。" : "同一考试只保留一份有效答卷。"}</span></div><button className="button button-primary" onClick={() => openAttempt(existingAttemptId, exam.existing_attempt_status)} type="button">{historicalAttempt ? "查看答题记录" : "继续答题"}<ArrowRight size={15} /></button></div> : unavailable ? <div className="public-exam-unavailable"><strong>{unavailableMessages[exam.status] || "这场考试当前不能开始答题。"}</strong>{exam.status === "expired" && <span>已提交的参与者仍可通过原答题身份查看历史记录。</span>}</div> : <div className="public-exam-action public-exam-identity-action">
          <div className="public-participant-field"><label htmlFor="participant-name">答题身份</label>
            {exam.identity_type === "user" && <div className="signed-participant"><UserRound size={15} />{exam.participant_name}<span>平台用户</span></div>}
            {exam.identity_type === "wechat" && <div className="wechat-participant"><span className="wechat-avatar">{exam.participant_avatar_url ? <img alt="" src={exam.participant_avatar_url} /> : <UserRound size={17} />}</span><span><strong>{exam.participant_name}</strong><small><ScanLine size={12} />微信认证</small></span><button aria-label="退出微信身份" className="button button-quiet" onClick={() => void handleWechatLogout()} title="退出微信身份" type="button"><LogOut size={14} /></button></div>}
            {exam.identity_type === "anonymous" && <>{exam.wechat_login_enabled && <button className="button wechat-login-button" onClick={handleWechatLogin} type="button"><ScanLine size={17} />微信登录答题</button>}{exam.wechat_login_enabled && !exam.wechat_login_required && <div className="identity-divider"><span>或使用答题名称</span></div>}{!exam.wechat_login_required && <input autoComplete="name" id="participant-name" maxLength={50} onChange={(event) => setParticipantName(event.target.value)} placeholder="填写你的答题名称" value={participantName} />}</>}
          </div>
          {!(exam.identity_type === "anonymous" && exam.wechat_login_required) && <button className="button button-primary" disabled={starting} onClick={() => void handleStart()} type="button">{starting ? "正在准备……" : "开始答题"}<ArrowRight size={15} /></button>}
        </div>}
        <div className="public-privacy-note"><ShieldCheck size={16} /><span>你的身份名称、头像、答案、成绩、提交时间、终端和 IP 将对考试分享者可见。微信认证用于识别同一微信账号，不等同于实名身份认证。</span></div>
      </main>
    </div>
  );
}
