"use client";

import { ArrowLeft, BarChart3, Check, CircleX, Copy, Download, Eye, LoaderCircle, Monitor, PencilLine, RefreshCw, RotateCcw, ShieldAlert, Smartphone, Tablet, UserRound, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ExamAttemptReport } from "@/components/exam-attempt-report";
import { EmptyState, ErrorState, EvidenceList } from "@/components/ui";
import { ExamLearningAnalysis } from "@/components/exam-learning-analysis";
import { ApiError, getAdminExamAttempt, getAdminExamShare, getExamAttemptForOwner, getExamShare, retryAdminExamAttemptGrading, retryExamAttemptGrading } from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import { downloadElementAsPng } from "@/lib/export-image";
import { formatDateTime, formatDuration, formatScore } from "@/lib/format";
import type { ExamAttempt, ExamAttemptSummary, ExamDeviceType, ExamQuestion, ExamShare, ExamShareStatus } from "@/lib/types";

const statusLabels: Record<ExamShareStatus, string> = {
  active: "分享中",
  stopped: "已停止",
  source_deleted: "原试卷已删除",
  expired: "已过期",
};

const attemptStatusLabels: Record<ExamAttemptSummary["status"], string> = {
  in_progress: "答题中",
  grading: "评分中",
  completed: "已完成",
  grading_failed: "评分失败",
};

const deviceTypeLabels: Record<ExamDeviceType, string> = {
  desktop: "电脑",
  mobile: "手机",
  tablet: "平板",
  unknown: "未知终端",
};

export function ExamShareDetailView({ shareId, admin = false }: { shareId: string; admin?: boolean }) {
  const [share, setShare] = useState<ExamShare | null>(null);
  const [selectedAttempt, setSelectedAttempt] = useState<ExamAttempt | null>(null);
  const [loading, setLoading] = useState(true);
  const [attemptLoading, setAttemptLoading] = useState(false);
  const [exportingAttemptId, setExportingAttemptId] = useState<string | null>(null);
  const [reportAttempt, setReportAttempt] = useState<ExamAttempt | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const reportRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setError("");
    try {
      setShare(await (admin ? getAdminExamShare(shareId) : getExamShare(shareId)));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "考试详情加载失败");
    } finally {
      setLoading(false);
    }
  }, [admin, shareId]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!share?.attempts?.some((attempt) => attempt.status === "grading")) return;
    const timer = window.setInterval(() => { void load(); }, 2500);
    return () => window.clearInterval(timer);
  }, [load, share?.attempts]);
  useEffect(() => {
    if (selectedAttempt?.status !== "grading") return;
    const attemptId = selectedAttempt.id;
    const refresh = async () => {
      try {
        const nextAttempt = await (admin ? getAdminExamAttempt(shareId, attemptId) : getExamAttemptForOwner(shareId, attemptId));
        setSelectedAttempt((currentAttempt) => currentAttempt?.id === attemptId ? nextAttempt : currentAttempt);
      } catch {
        // Keep the current answer visible; the manual refresh action reports request errors.
      }
    };
    const timer = window.setInterval(() => { void refresh(); }, 2500);
    return () => window.clearInterval(timer);
  }, [admin, selectedAttempt?.id, selectedAttempt?.status, shareId]);

  const completedAttempts = useMemo(
    () => share?.attempts?.filter((attempt) => attempt.status === "completed") || [],
    [share?.attempts],
  );

  async function copyLink() {
    if (!share) return;
    setError("");
    try {
      await copyText(`${window.location.origin}/exams/${share.share_code}`);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("链接复制失败，请手动选择下方分享链接进行复制");
    }
  }

  async function openAttempt(attemptId: string) {
    setAttemptLoading(true);
    setError("");
    try {
      setSelectedAttempt(await (admin ? getAdminExamAttempt(shareId, attemptId) : getExamAttemptForOwner(shareId, attemptId)));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "答卷详情加载失败");
    } finally {
      setAttemptLoading(false);
    }
  }

  async function retryGrading() {
    if (!selectedAttempt) return;
    setRetrying(true);
    setError("");
    try {
      setSelectedAttempt(await (admin ? retryAdminExamAttemptGrading(shareId, selectedAttempt.id) : retryExamAttemptGrading(shareId, selectedAttempt.id)));
      await load();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "重新评分失败");
    } finally {
      setRetrying(false);
    }
  }

  async function exportAttempt(attemptId: string) {
    setExportingAttemptId(attemptId);
    setError("");
    try {
      const attempt = selectedAttempt?.id === attemptId
        ? selectedAttempt
        : await (admin ? getAdminExamAttempt(shareId, attemptId) : getExamAttemptForOwner(shareId, attemptId));
      setReportAttempt(attempt);
      await waitForReportRender();
      if (!reportRef.current) throw new Error("报告内容尚未完成渲染");
      await downloadElementAsPng(reportRef.current, `${attempt.exam_name}-${attempt.participant_name}-答题报告`);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "答题报告导出失败");
    } finally {
      setExportingAttemptId(null);
      setReportAttempt(null);
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在读取考试详情……</div></div>;
  if (!share) return <div className="page-wrap"><ErrorState message={error || "未找到这个考试活动"} /></div>;

  return (
    <div className="page-wrap">
      <Link className="back-link" href={admin ? "/settings/exams" : "/exam-management"}><ArrowLeft size={14} />返回{admin ? "全平台考试" : "考试管理"}</Link>
      {error && <div className="toast-error">{error}</div>}
      <header className="exam-detail-header">
        <div><div className="eyebrow">Exam detail</div><h1 className="page-title">{share.name}</h1><p className="page-description">{share.book_title} · {share.quiz_title}{admin ? ` · 分享者：${share.owner_display_name}（${share.owner_username}）` : ""}</p></div>
        <div className="header-actions"><span className={`exam-status exam-status-${share.status}`}>{statusLabels[share.status]}</span><Link className="button button-secondary" href={`/exam-management/${share.id}/edit`}><PencilLine size={15} />编辑题目</Link><button className="button button-secondary" onClick={() => void copyLink()} type="button">{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? "已复制" : "复制链接"}</button></div>
      </header>

      <div className="share-link-strip"><span>{`${typeof window === "undefined" ? "" : window.location.origin}/exams/${share.share_code}`}</span><small>创建于 {formatDateTime(share.created_at)} · {share.expires_at ? `截止 ${formatDateTime(share.expires_at)}` : "长期有效"}</small></div>

      <div className="metrics-grid exam-detail-metrics">
        <div className="metric"><div className="metric-label">开始答题</div><div className="metric-value">{share.started_count}<span className="metric-detail">人次</span></div></div>
        <div className="metric"><div className="metric-label">已经交卷</div><div className="metric-value">{share.submitted_count}<span className="metric-detail">份</span></div></div>
        <div className="metric"><div className="metric-label">平均得分率</div><div className="metric-value">{share.average_score === null ? "—" : `${share.average_score}%`}</div></div>
        <div className="metric"><div className="metric-label">最高得分率</div><div className="metric-value">{share.highest_score === null ? "—" : `${share.highest_score}%`}</div></div>
      </div>

      <ExamScoreChart attempts={completedAttempts} />

      <section className="content-panel exam-attempt-panel">
        <div className="section-title"><h2>答题记录</h2><span>{completedAttempts.length} 份已完成 · {share.grading_count} 份评分中</span></div>
        {!share.attempts?.length ? <EmptyState title="还没有参与者" detail="分享链接被打开并开始答题后，记录会出现在这里。" /> : <div className="exam-table-wrap"><table className="exam-table attempt-table"><thead><tr><th>参与者</th><th>身份</th><th>终端 / IP</th><th>状态</th><th>得分</th><th>用时</th><th>开始时间</th><th>提交时间</th><th className="attempt-actions-cell">操作</th></tr></thead><tbody>{share.attempts.map((attempt) => <tr key={attempt.id}>
          <td><div className="attempt-participant-cell"><span className="participant-avatar">{attempt.participant_avatar_url ? <img alt="" src={attempt.participant_avatar_url} /> : <UserRound size={14} />}</span><strong>{attempt.participant_name}</strong></div></td>
          <td><span className={`participant-type ${attempt.participant_type === "wechat" ? "wechat" : ""}`}><UserRound size={13} />{attempt.participant_type === "user" ? "平台用户" : attempt.participant_type === "wechat" ? "微信认证" : "匿名参与者"}</span></td>
          <td><div className="attempt-device-cell"><span>{deviceIcon(attempt.device_type)}{attempt.device_type ? deviceTypeLabels[attempt.device_type] : "历史记录未采集"}</span><small>{attempt.started_ip_address || "IP 未采集"}</small>{attempt.ip_changed && <small className="ip-change-warning"><ShieldAlert size={11} />提交 IP 已变化</small>}</div></td>
          <td><div className="exam-cell-stack"><span className={`exam-status attempt-status-${attempt.status}`}>{attemptStatusLabels[attempt.status]}</span>{attempt.grading_error && <small className="score-low" title={attempt.grading_error}>需要重新评分</small>}</div></td>
          <td className={`attempt-score-cell ${attempt.score_percentage !== null && attempt.score_percentage < 60 ? "score-low" : "score-good"}`}>{attempt.total_score === null ? "—" : `${formatScore(attempt.total_score)} / ${formatScore(attempt.max_score)}`}</td>
          <td>{formatDuration(attempt.elapsed_seconds)}</td><td>{formatDateTime(attempt.started_at)}</td><td>{formatDateTime(attempt.submitted_at)}</td>
          <td className="attempt-actions-cell"><div className="attempt-action-buttons"><button aria-label={`查看${attempt.participant_name}的答卷`} className="button button-quiet" disabled={attemptLoading} onClick={() => void openAttempt(attempt.id)} title="查看答卷" type="button"><Eye size={15} /></button>{attempt.status === "completed" && <button aria-label={`下载${attempt.participant_name}的答题报告`} className="button button-quiet" disabled={exportingAttemptId !== null} onClick={() => void exportAttempt(attempt.id)} title="下载报告长图" type="button">{exportingAttemptId === attempt.id ? <LoaderCircle className="spin" size={15} /> : <Download size={15} />}</button>}</div></td>
        </tr>)}</tbody></table></div>}
      </section>

      {selectedAttempt && <div className="modal-backdrop attempt-modal-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) setSelectedAttempt(null); }} role="presentation"><section aria-labelledby="attempt-detail-title" aria-modal="true" className="modal-panel attempt-detail-modal" role="dialog">
        <div className="modal-heading"><div><span className="eyebrow">Answer detail</span><h2 id="attempt-detail-title">{selectedAttempt.participant_name}的答卷</h2></div><button aria-label="关闭答卷详情" className="modal-close" onClick={() => setSelectedAttempt(null)} title="关闭" type="button"><X size={18} /></button></div>
        <div className="attempt-summary-strip"><span>{attemptStatusLabels[selectedAttempt.status]}</span><strong>{formatScore(selectedAttempt.total_score)} / {formatScore(selectedAttempt.max_score)} 分</strong><span>用时 {formatDuration(selectedAttempt.elapsed_seconds)}</span></div>
        <div className="attempt-security-strip">
          <div><span>答题终端</span><strong>{deviceIcon(selectedAttempt.device_type)}{selectedAttempt.device_type ? deviceTypeLabels[selectedAttempt.device_type] : "历史记录未采集"}</strong></div>
          <div><span>开始 IP</span><strong>{selectedAttempt.started_ip_address || "未采集"}</strong></div>
          <div><span>提交 IP</span><strong className={selectedAttempt.ip_changed ? "score-low" : ""}>{selectedAttempt.submitted_ip_address || "未采集"}{selectedAttempt.ip_changed && <ShieldAlert size={13} />}</strong></div>
        </div>
        {selectedAttempt.user_agent && <details className="attempt-user-agent"><summary>查看浏览器终端信息</summary><code>{selectedAttempt.user_agent}</code></details>}
        {selectedAttempt.status === "grading_failed" && <div className="toast-error">{selectedAttempt.grading_error || "问答题评分失败。"}<button className="button button-secondary" disabled={retrying} onClick={() => void retryGrading()} type="button"><RotateCcw size={14} />{retrying ? "正在重试……" : "重新评分"}</button></div>}
        {selectedAttempt.status === "grading" && <div className="grading-state"><LoaderCircle className="spin" size={18} />问答题正在评分，结果会自动更新。</div>}
        {selectedAttempt.status === "completed" && <ExamLearningAnalysis recommendedDirection={selectedAttempt.recommended_direction} weakPoints={selectedAttempt.weak_knowledge_points || []} />}
        <div className="attempt-question-list">{selectedAttempt.questions.map((question, index) => <AttemptQuestion key={question.id} question={question} answer={selectedAttempt.answers.find((item) => item.question_id === question.id)} index={index} sourceMode={selectedAttempt.source_mode} />)}</div>
        <div className="modal-actions"><button className="button button-secondary" onClick={() => setSelectedAttempt(null)} type="button">关闭</button>{selectedAttempt.status === "completed" && <button className="button button-secondary" disabled={exportingAttemptId !== null} onClick={() => void exportAttempt(selectedAttempt.id)} type="button">{exportingAttemptId === selectedAttempt.id ? <LoaderCircle className="spin" size={15} /> : <Download size={15} />}导出报告</button>}<button aria-label="刷新答卷" className="button button-primary" onClick={() => void openAttempt(selectedAttempt.id)} type="button"><RefreshCw size={15} />刷新结果</button></div>
      </section></div>}
      {reportAttempt && <ExamAttemptReport attempt={reportAttempt} includeSecurity ref={reportRef} />}
    </div>
  );
}

function waitForReportRender() {
  return new Promise<void>((resolve) => {
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => resolve()));
  });
}

function deviceIcon(deviceType: ExamDeviceType | null) {
  if (deviceType === "mobile") return <Smartphone aria-hidden="true" size={13} />;
  if (deviceType === "tablet") return <Tablet aria-hidden="true" size={13} />;
  return <Monitor aria-hidden="true" size={13} />;
}

function ExamScoreChart({ attempts }: { attempts: ExamAttemptSummary[] }) {
  const chartWidth = Math.max(560, attempts.length * 86);
  return (
    <section className="content-panel exam-score-panel">
      <div className="section-title"><h2><BarChart3 size={17} />参与者得分</h2><span>仅统计已完成评分的答卷</span></div>
      {attempts.length === 0 ? (
        <EmptyState title="暂无可统计成绩" detail="参与者完成答题和评分后，成绩会显示在这里。" />
      ) : (
        <div className="score-chart-layout" role="img" aria-label="已完成参与者实际得分柱状图">
          <div className="score-chart-axis" aria-hidden="true">{[100, 75, 50, 25, 0].map((value) => <span key={value}>{value}</span>)}</div>
          <div className="score-chart-scroll">
            <div className="score-chart-plot" style={{ minWidth: chartWidth }}>
              <div className="score-chart-grid" aria-hidden="true">{[100, 75, 50, 25, 0].map((value) => <i key={value} style={{ top: `${100 - value}%` }} />)}</div>
              <div className="score-chart-bars">
                {attempts.map((attempt) => {
                  const percentage = Math.max(0, Math.min(100, attempt.score_percentage || 0));
                  const scoreClass = percentage < 60 ? "low" : percentage < 80 ? "medium" : "high";
                  return <div className="score-chart-item" key={attempt.id} title={`${attempt.participant_name}：${formatScore(attempt.total_score)} 分`}><div className="score-bar-track"><div className={`score-bar ${scoreClass}`} style={{ height: `${Math.max(percentage, 1)}%` }}><strong>{formatScore(attempt.total_score)}</strong></div></div><span>{attempt.participant_name}</span></div>;
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function AttemptQuestion({ question, answer, index, sourceMode }: { question: ExamQuestion; answer: ExamAttempt["answers"][number] | undefined; index: number; sourceMode: ExamAttempt["source_mode"] }) {
  const selectedText = answer ? question.question_type === "short" ? answer.text_answer || "未作答" : question.options.filter((option) => answer.selected_answers.includes(option.id)).map((option) => `${option.id}. ${option.text}`).join("；") || "未作答" : "尚未提交";
  const correctText = question.question_type === "short" ? question.reference_answer : question.options.filter((option) => question.correct_answers?.includes(option.id)).map((option) => `${option.id}. ${option.text}`).join("；");
  return <article className={`result-question ${answer?.is_correct ? "correct" : "incorrect"}`}>
    <div className="question-card-header"><span className="question-number">第 {index + 1} 题 · {question.knowledge_point}</span><span className={answer && answer.score / answer.max_score >= 0.6 ? "score-good" : "score-low"}>{answer ? `${formatScore(answer.score)} / ${formatScore(answer.max_score)} 分` : "等待提交"}</span></div>
    <h3>{question.prompt}</h3>
    <div className="result-answer-row"><div><strong>参与者答案：</strong>{selectedText}</div><div><strong>{question.question_type === "short" ? "参考答案" : "正确答案"}：</strong>{correctText || "—"}</div></div>
    {answer && <div className="result-feedback">{answer.is_correct ? <Check size={14} /> : <CircleX size={14} />}{answer.feedback} {question.explanation}</div>}
    {question.grading_rubric.length > 0 && <div className="rubric-list">{question.grading_rubric.map((rubric) => <div className={`rubric-row ${answer?.matched_points.includes(rubric.point) ? "hit" : ""}`} key={rubric.point}>{answer?.matched_points.includes(rubric.point) ? "已覆盖" : "待补充"}：{rubric.point}</div>)}</div>}
    <EvidenceList evidence={question.source_evidence} sourceMode={sourceMode} />
  </article>;
}
