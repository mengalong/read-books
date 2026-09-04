"use client";

import { ArrowLeft, BarChart3, Check, ChevronLeft, ChevronRight, CircleX, Copy, Download, Eye, LoaderCircle, Monitor, PencilLine, RefreshCw, RotateCcw, ShieldAlert, Smartphone, Tablet, UserRound, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { ExamAttemptReport } from "@/components/exam-attempt-report";
import { EmptyState, ErrorState, EvidenceList } from "@/components/ui";
import { ExamLearningAnalysis } from "@/components/exam-learning-analysis";
import { ApiError, getAdminExamAttempt, getAdminExamShare, getExamAttemptForOwner, getExamShare, retryAdminExamAttemptGrading, retryExamAttemptGrading } from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import { downloadElementAsPng } from "@/lib/export-image";
import { formatDateTime, formatDuration, formatScore } from "@/lib/format";
import type { ExamAttempt, ExamAttemptStatus, ExamAttemptSummary, ExamDeviceType, ExamQuestion, ExamShare, ExamShareStatus } from "@/lib/types";

const ATTEMPTS_PAGE_SIZE = 20;
type AttemptStatusFilter = "" | ExamAttemptStatus;
type AttemptSort = "latest" | "score_desc" | "score_asc";

function isAttemptStatus(value: string): value is ExamAttemptStatus {
  return ["in_progress", "grading", "completed", "grading_failed"].includes(value);
}

function isAttemptSort(value: string): value is AttemptSort {
  return ["latest", "score_desc", "score_asc"].includes(value);
}

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
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialPage = Math.max(1, Number(searchParams.get("page") || 1) || 1);
  const initialStatusParam = searchParams.get("status") || "";
  const initialStatus: AttemptStatusFilter = isAttemptStatus(initialStatusParam) ? initialStatusParam : "";
  const initialSortParam = searchParams.get("sort") || "latest";
  const initialSort: AttemptSort = isAttemptSort(initialSortParam) ? initialSortParam : "latest";
  const [share, setShare] = useState<ExamShare | null>(null);
  const [selectedAttempt, setSelectedAttempt] = useState<ExamAttempt | null>(null);
  const [loading, setLoading] = useState(true);
  const [attemptsLoading, setAttemptsLoading] = useState(false);
  const [attemptLoading, setAttemptLoading] = useState(false);
  const [exportingAttemptId, setExportingAttemptId] = useState<string | null>(null);
  const [reportAttempt, setReportAttempt] = useState<ExamAttempt | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [attemptPage, setAttemptPage] = useState(initialPage);
  const [attemptStatus, setAttemptStatus] = useState<AttemptStatusFilter>(initialStatus);
  const [attemptSort, setAttemptSort] = useState<AttemptSort>(initialSort);
  const reportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const nextPage = Math.max(1, Number(searchParams.get("page") || 1) || 1);
    const nextStatusParam = searchParams.get("status") || "";
    const nextStatus: AttemptStatusFilter = isAttemptStatus(nextStatusParam) ? nextStatusParam : "";
    const nextSortParam = searchParams.get("sort") || "latest";
    const nextSort: AttemptSort = isAttemptSort(nextSortParam) ? nextSortParam : "latest";
    setAttemptPage(nextPage);
    setAttemptStatus(nextStatus);
    setAttemptSort(nextSort);
  }, [searchParams]);

  function updateAttemptUrl(page: number, status: AttemptStatusFilter, sort: AttemptSort) {
    const params = new URLSearchParams(searchParams.toString());
    if (page > 1) params.set("page", String(page)); else params.delete("page");
    if (status) params.set("status", status); else params.delete("status");
    if (sort !== "latest") params.set("sort", sort); else params.delete("sort");
    const query = params.toString();
    router.replace(`${pathname}${query ? `?${query}` : ""}`, { scroll: false });
  }

  const load = useCallback(async () => {
    setError("");
    setAttemptsLoading(true);
    try {
      const options = {
        ...(attemptPage > 1 ? { page: attemptPage } : {}),
        ...(attemptStatus ? { status: attemptStatus } : {}),
        ...(attemptSort !== "latest" ? { sort: attemptSort } : {}),
      };
      setShare(await (admin ? getAdminExamShare(shareId, options) : getExamShare(shareId, options)));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "考试详情加载失败");
    } finally {
      setLoading(false);
      setAttemptsLoading(false);
    }
  }, [admin, attemptPage, attemptSort, attemptStatus, shareId]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!share?.grading_count) return;
    const timer = window.setInterval(() => { void load(); }, 2500);
    return () => window.clearInterval(timer);
  }, [load, share?.grading_count]);
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

  const attempts = share.attempts || [];
  const attemptsTotal = share.attempts_total ?? share.started_count;
  const attemptsPage = share.attempts_page ?? attemptPage;
  const attemptsPageSize = share.attempts_page_size ?? ATTEMPTS_PAGE_SIZE;
  const totalAttemptPages = Math.max(1, Math.ceil(attemptsTotal / attemptsPageSize));
  const hasAttemptFilter = Boolean(attemptStatus);

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
        <div className="metric"><div className="metric-label">完成率</div><div className="metric-value">{share.completion_rate}<span className="metric-detail">%</span></div></div>
        <div className="metric"><div className="metric-label">已完成评分</div><div className="metric-value">{share.graded_count ?? 0}<span className="metric-detail">份</span></div></div>
        <div className="metric"><div className="metric-label">平均分</div><div className="metric-value">{share.average_points === null || share.average_points === undefined ? "—" : formatScore(share.average_points)}<span className="metric-detail">/ {formatScore(share.max_score)} 分</span></div></div>
        <div className="metric"><div className="metric-label">中位数分数</div><div className="metric-value">{share.median_points === null || share.median_points === undefined ? "—" : formatScore(share.median_points)}<span className="metric-detail">/ {formatScore(share.max_score)} 分</span></div></div>
      </div>

      <ExamScoreDistribution distribution={share.score_distribution || []} gradedCount={share.graded_count || 0} aboveThresholdCount={share.above_threshold_count || 0} aboveThresholdRate={share.above_threshold_rate ?? null} />

      <section className="content-panel exam-attempt-panel">
        <div className="section-title attempt-table-heading"><div><h2>答题记录</h2><span>{hasAttemptFilter ? `${attemptsTotal} 份匹配记录` : `${share.graded_count || 0} 份已完成评分 · ${share.grading_count} 份评分中`}</span></div><div className="attempt-table-controls"><label>状态<select aria-label="按答卷状态筛选" onChange={(event) => { const next = event.target.value as AttemptStatusFilter; setAttemptStatus(next); setAttemptPage(1); updateAttemptUrl(1, next, attemptSort); }} value={attemptStatus}><option value="">全部状态</option><option value="in_progress">答题中</option><option value="grading">评分中</option><option value="completed">已完成</option><option value="grading_failed">评分失败</option></select></label><label>排序<select aria-label="答卷排序" onChange={(event) => { const next = event.target.value as AttemptSort; setAttemptSort(next); setAttemptPage(1); updateAttemptUrl(1, attemptStatus, next); }} value={attemptSort}><option value="latest">最近提交</option><option value="score_desc">得分从高到低</option><option value="score_asc">得分从低到高</option></select></label></div></div>
        {!attempts.length ? <EmptyState title={hasAttemptFilter ? "没有符合条件的答卷" : "还没有参与者"} detail={hasAttemptFilter ? "调整状态筛选后再试。" : "分享链接被打开并开始答题后，记录会出现在这里。"} /> : <div className={`exam-table-wrap${attemptsLoading ? " is-refreshing" : ""}`}><table className="exam-table attempt-table"><thead><tr><th>参与者</th><th>身份</th><th>终端 / IP</th><th>状态</th><th>得分</th><th>用时</th><th>开始时间</th><th>提交时间</th><th className="attempt-actions-cell">操作</th></tr></thead><tbody>{attempts.map((attempt) => <tr key={attempt.id}>
          <td><div className="attempt-participant-cell"><span className="participant-avatar">{attempt.participant_avatar_url ? <img alt="" src={attempt.participant_avatar_url} /> : <UserRound size={14} />}</span><strong>{attempt.participant_name}</strong></div></td>
          <td><span className={`participant-type ${attempt.participant_type === "wechat" ? "wechat" : ""}`}><UserRound size={13} />{attempt.participant_type === "user" ? "平台用户" : attempt.participant_type === "wechat" ? "微信认证" : "匿名参与者"}</span></td>
          <td><div className="attempt-device-cell"><span>{deviceIcon(attempt.device_type)}{attempt.device_type ? deviceTypeLabels[attempt.device_type] : "历史记录未采集"}</span><small>{attempt.started_ip_address || "IP 未采集"}</small>{attempt.ip_changed && <small className="ip-change-warning"><ShieldAlert size={11} />提交 IP 已变化</small>}</div></td>
          <td><div className="exam-cell-stack"><span className={`exam-status attempt-status-${attempt.status}`}>{attemptStatusLabels[attempt.status]}</span>{attempt.grading_error && <small className="score-low" title={attempt.grading_error}>需要重新评分</small>}</div></td>
          <td className={`attempt-score-cell ${attempt.score_percentage !== null && attempt.score_percentage < 60 ? "score-low" : "score-good"}`}>{attempt.total_score === null ? "—" : `${formatScore(attempt.total_score)} / ${formatScore(attempt.max_score)}`}</td>
          <td>{formatDuration(attempt.elapsed_seconds)}</td><td>{formatDateTime(attempt.started_at)}</td><td>{formatDateTime(attempt.submitted_at)}</td>
          <td className="attempt-actions-cell"><div className="attempt-action-buttons"><button aria-label={`查看${attempt.participant_name}的答卷`} className="button button-quiet" disabled={attemptLoading} onClick={() => void openAttempt(attempt.id)} title="查看答卷" type="button"><Eye size={15} /></button>{attempt.status === "completed" && <button aria-label={`下载${attempt.participant_name}的答题报告`} className="button button-quiet" disabled={exportingAttemptId !== null} onClick={() => void exportAttempt(attempt.id)} title="下载报告长图" type="button">{exportingAttemptId === attempt.id ? <LoaderCircle className="spin" size={15} /> : <Download size={15} />}</button>}</div></td>
        </tr>)}</tbody></table></div>}
        {attemptsTotal > 0 && <div className="attempt-pagination"><span aria-live="polite">{attemptsLoading ? "正在刷新…" : `第 ${attemptsPage} / ${totalAttemptPages} 页 · 共 ${attemptsTotal} 份`}</span><div><button aria-label="上一页" className="button button-quiet" disabled={attemptsPage <= 1 || attemptsLoading} onClick={() => { const next = attemptsPage - 1; setAttemptPage(next); updateAttemptUrl(next, attemptStatus, attemptSort); }} title="上一页" type="button"><ChevronLeft size={16} /></button><button aria-label="下一页" className="button button-quiet" disabled={attemptsPage >= totalAttemptPages || attemptsLoading} onClick={() => { const next = attemptsPage + 1; setAttemptPage(next); updateAttemptUrl(next, attemptStatus, attemptSort); }} title="下一页" type="button"><ChevronRight size={16} /></button></div></div>}
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

function ExamScoreDistribution({ distribution, gradedCount, aboveThresholdCount, aboveThresholdRate }: { distribution: { label: string; min_score: number; max_score: number; count: number; percentage: number }[]; gradedCount: number; aboveThresholdCount: number; aboveThresholdRate: number | null }) {
  const maxCount = Math.max(1, ...distribution.map((bucket) => bucket.count));
  return (
    <section className="content-panel exam-score-panel">
      <div className="section-title"><h2><BarChart3 size={17} />成绩分布</h2><span>按得分区间统计已完成评分的答卷</span></div>
      {gradedCount === 0 ? (
        <EmptyState title="暂无可统计成绩" detail="参与者完成答题和评分后，成绩会显示在这里。" />
      ) : (
        <div className="score-distribution-layout">
          <figure className="score-distribution-figure" aria-label="已完成评分答卷的成绩区间分布">
            <div className="score-distribution-bars" role="img" aria-label={`已评分 ${gradedCount} 份，成绩分布为 ${distribution.map((bucket) => `${bucket.label} ${bucket.count} 人`).join("，")}`}>
              {distribution.map((bucket) => <div className="score-distribution-item" key={bucket.label}><div className="score-distribution-track"><div className={`score-distribution-bar ${bucket.min_score < 60 ? "low" : bucket.min_score < 80 ? "medium" : "high"}`} style={{ height: `${Math.max(bucket.count / maxCount * 100, 2)}%` }}><strong>{bucket.count}</strong></div></div><span>{bucket.label}</span><small>{bucket.percentage}%</small></div>)}
            </div>
            <figcaption>每根柱显示人数，下方为该区间占已评分答卷的比例。</figcaption>
          </figure>
          <div className="score-distribution-summary"><dl><div><dt>已完成评分</dt><dd>{gradedCount} 份</dd></div><div><dt>60 分以上</dt><dd>{aboveThresholdRate === null ? "—" : `${aboveThresholdRate}%`}<small>{aboveThresholdCount} 份</small></dd></div></dl><table className="score-distribution-table"><caption>成绩区间明细</caption><thead><tr><th>区间</th><th>人数</th><th>占比</th></tr></thead><tbody>{distribution.map((bucket) => <tr key={bucket.label}><th scope="row">{bucket.label}</th><td>{bucket.count}</td><td>{bucket.percentage}%</td></tr>)}</tbody></table></div>
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
