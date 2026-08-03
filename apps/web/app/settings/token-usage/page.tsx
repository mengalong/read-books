"use client";

import { BarChart3, CheckCircle2, Clock3, RefreshCw, XCircle } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ApiError, getTokenUsage } from "@/lib/api";
import { formatDateTimeLong } from "@/lib/format";
import type { TokenUsageReport, TokenUsageStage, TokenUsageTask } from "@/lib/types";

const FILTERS = [
  { value: "", label: "全部任务" },
  { value: "manual_quiz_generation", label: "手动出题" },
  { value: "pre_generation", label: "后台预出题" },
  { value: "quiz_submission", label: "问答评分" },
  { value: "model_connection_test", label: "连接测试" },
];

const TASK_LABELS: Record<string, string> = Object.fromEntries(
  FILTERS.filter((item) => item.value).map((item) => [item.value, item.label]),
);

const PHASE_LABELS: Record<string, string> = {
  quiz_generation: "出题",
  quiz_generation_repair: "出题格式修正",
  short_answer_grading: "问答题评分",
  connection_test: "连接测试",
};

function formatTokens(value: number | null) {
  return value === null ? "未报告" : new Intl.NumberFormat("zh-CN").format(value);
}

function formatTime(value: string) {
  return formatDateTimeLong(value);
}

function stageUsage(stage: TokenUsageStage) {
  return `${formatTokens(stage.input_tokens)} / ${formatTokens(stage.output_tokens)} / ${formatTokens(stage.total_tokens)}`;
}

function TaskLinks({ task }: { task: TokenUsageTask }) {
  return (
    <span className="usage-task-links">
      {task.book_id && <Link href={`/admin/books/${task.book_id}`}>查看书籍</Link>}
      {task.quiz_id && <Link href={`/quizzes/${task.quiz_id}`}>查看题目</Link>}
    </span>
  );
}

function UsageTask({ task }: { task: TokenUsageTask }) {
  return (
    <details className="usage-task">
      <summary>
        <span className="usage-task-title">
          {task.status === "success" ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
          <span>
            <strong>{task.task_label}</strong>
            <small>{task.display_name || "历史未归属用户"} · {TASK_LABELS[task.task_type] || task.task_type} · {formatTime(task.started_at)}</small>
          </span>
        </span>
        <span className="usage-task-summary">
          <span>{formatTokens(task.total_tokens)} tokens</span>
          <span>{task.stages.length} 个阶段</span>
        </span>
      </summary>
      <div className="usage-task-detail">
        <div className="usage-task-meta">
          <span>输入 {formatTokens(task.input_tokens)}</span>
          <span>输出 {formatTokens(task.output_tokens)}</span>
          {task.username && <span>用户 {task.username}</span>}
          {task.unreported_calls > 0 && <span>{task.unreported_calls} 次未报告用量</span>}
          <TaskLinks task={task} />
        </div>
        <div className="usage-stage-table-wrap">
          <table className="usage-stage-table">
            <thead><tr><th>阶段</th><th>模型</th><th>输入 / 输出 / 总计</th><th>耗时</th><th>结果</th><th>调用时间</th></tr></thead>
            <tbody>
              {task.stages.map((stage) => (
                <tr key={stage.id}>
                  <td>{PHASE_LABELS[stage.phase] || stage.phase}<small>第 {stage.call_number} 次</small></td>
                  <td>{stage.model_name || "未填写"}</td>
                  <td className="usage-number">{stageUsage(stage)}</td>
                  <td>{stage.latency_ms} ms</td>
                  <td><span className={`usage-status ${stage.status}`}>{stage.status === "success" ? "成功" : stage.error_message || "失败"}</span></td>
                  <td>{formatTime(stage.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </details>
  );
}

export default function TokenUsagePage() {
  const [report, setReport] = useState<TokenUsageReport | null>(null);
  const [taskType, setTaskType] = useState("");
  const [userId, setUserId] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    else setRefreshing(true);
    setError("");
    try {
      setReport(await getTokenUsage(taskType || undefined, userId || undefined));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "Token 用量加载失败");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [taskType, userId]);

  useEffect(() => { void load(true); }, [load]);

  if (loading) return <div className="page-wrap"><div className="loading-state">正在读取 Token 用量……</div></div>;
  if (error && !report) return <div className="page-wrap"><div className="toast-error">{error}</div></div>;

  const summary = report?.summary || {
    task_count: 0,
    total_calls: 0,
    successful_calls: 0,
    failed_calls: 0,
    unreported_calls: 0,
    input_tokens: 0,
    output_tokens: 0,
    total_tokens: 0,
  };

  return (
    <div className="page-wrap">
      <header className="page-header compact-header">
        <div>
          <div className="eyebrow">System management</div>
          <h1 className="page-title">Token 用量</h1>
          <p className="page-description">按任务查看模型在出题、修正、评分等阶段的调用消耗</p>
        </div>
        <button aria-label="刷新 Token 用量" className="button button-secondary" disabled={refreshing} onClick={() => void load()} title="刷新 Token 用量" type="button">
          <RefreshCw className={refreshing ? "spin" : ""} size={15} />刷新
        </button>
      </header>

      {error && <div className="toast-error">{error}</div>}
      <div className="metrics-grid usage-metrics">
        <div className="metric"><div className="metric-label">任务数</div><div className="metric-value">{summary.task_count}<span className="metric-detail">项</span></div></div>
        <div className="metric"><div className="metric-label">总 Token</div><div className="metric-value">{formatTokens(summary.total_tokens)}</div></div>
        <div className="metric"><div className="metric-label">输入 Token</div><div className="metric-value">{formatTokens(summary.input_tokens)}</div></div>
        <div className="metric"><div className="metric-label">输出 Token</div><div className="metric-value">{formatTokens(summary.output_tokens)}</div></div>
      </div>

      <section className="content-panel usage-user-panel">
        <div className="section-title"><div><h2>用户用量</h2><span>按用户汇总当前任务类型下的模型消耗</span></div><label className="usage-user-filter">查看用户<select aria-label="按用户筛选 Token 用量" onChange={(event) => setUserId(event.target.value)} value={userId}><option value="">全部用户</option>{report?.users.map((user) => <option key={user.user_id} value={user.user_id}>{user.display_name}（{user.username}）</option>)}</select></label></div>
        <div className="usage-user-list">{report?.users.map((user) => <button className={userId === user.user_id ? "active" : ""} key={user.user_id} onClick={() => setUserId(userId === user.user_id ? "" : user.user_id)} type="button"><span><strong>{user.display_name}</strong><small>{user.username} · {user.task_count} 项任务 / {user.total_calls} 次调用</small></span><b>{formatTokens(user.total_tokens)}<small> tokens</small></b></button>)}{!report?.users.length && <span className="meta-text">尚无已归属用户的用量记录</span>}</div>
      </section>

      <section className="content-panel usage-panel">
        <div className="section-title">
          <div><h2><BarChart3 size={16} />任务明细</h2><span>{summary.total_calls} 次模型调用 · {summary.failed_calls} 次失败 · {summary.unreported_calls} 次未返回用量</span></div>
          <Clock3 size={16} />
        </div>
        <div className="usage-filter-row" role="tablist" aria-label="任务类型">
          {FILTERS.map((filter) => <button aria-selected={taskType === filter.value} className={taskType === filter.value ? "active" : ""} key={filter.value} onClick={() => setTaskType(filter.value)} role="tab" type="button">{filter.label}</button>)}
        </div>
        {!report?.tasks.length ? <div className="empty-usage"><BarChart3 size={22} /><strong>暂时没有模型用量记录</strong><span>开启真实模型并完成一次出题、评分或连接测试后，记录会显示在这里。</span></div> : <div className="usage-task-list">{report.tasks.map((task) => <UsageTask key={task.task_id} task={task} />)}</div>}
      </section>
    </div>
  );
}
