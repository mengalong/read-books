"use client";

import { Activity, CalendarDays, Clock3, LogIn, RefreshCw, Timer, Users } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";

import { ApiError, getAccessStatistics } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { AccessGranularity, AccessStatisticsReport } from "@/lib/types";

const granularities: { label: string; value: AccessGranularity }[] = [
  { label: "按天", value: "day" },
  { label: "按月", value: "month" },
  { label: "按年", value: "year" },
];

const periodName: Record<AccessGranularity, string> = {
  day: "天",
  month: "月",
  year: "年",
};

function formatAccessDuration(seconds: number) {
  if (seconds <= 0) return "0 分钟";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor(seconds % 3600 / 60);
  if (hours > 0) return `${hours} 小时 ${minutes} 分钟`;
  if (minutes > 0) return `${minutes} 分钟`;
  return `${seconds} 秒`;
}

export default function AccessStatisticsPage() {
  const [report, setReport] = useState<AccessStatisticsReport | null>(null);
  const [granularity, setGranularity] = useState<AccessGranularity>("day");
  const [userId, setUserId] = useState("");
  const [startInput, setStartInput] = useState("");
  const [endInput, setEndInput] = useState("");
  const [appliedRange, setAppliedRange] = useState({ start: "", end: "" });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    else setRefreshing(true);
    setError("");
    try {
      setReport(await getAccessStatistics({
        granularity,
        startDate: appliedRange.start || undefined,
        endDate: appliedRange.end || undefined,
        userId: userId || undefined,
      }));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "访问统计加载失败");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [appliedRange.end, appliedRange.start, granularity, userId]);

  useEffect(() => { void load(true); }, [load]);

  const periods = useMemo(() => [...(report?.periods || [])].reverse(), [report?.periods]);

  function changeGranularity(next: AccessGranularity) {
    setGranularity(next);
    setStartInput("");
    setEndInput("");
    setAppliedRange({ start: "", end: "" });
  }

  function applyDateRange() {
    setAppliedRange({ start: startInput, end: endInput });
  }

  function handleDateFilterSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    applyDateRange();
  }

  function handleDateInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      applyDateRange();
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在汇总访问记录……</div></div>;
  if (error && !report) return <div className="page-wrap"><div className="toast-error">{error}</div></div>;

  const summary = report?.summary || {
    visit_count: 0,
    login_count: 0,
    active_user_count: 0,
    total_duration_seconds: 0,
    average_duration_seconds: 0,
  };

  return (
    <div className="page-wrap">
      <header className="page-header compact-header">
        <div>
          <div className="eyebrow">System management</div>
          <h1 className="page-title">访问统计</h1>
          <p className="page-description">查看不同用户进入系统的频率、活跃时间段和访问时长</p>
        </div>
        <button aria-label="刷新访问统计" className="button button-secondary" disabled={refreshing} onClick={() => void load()} title="刷新访问统计" type="button"><RefreshCw className={refreshing ? "spin" : ""} size={15} />刷新</button>
      </header>

      {error && <div className="toast-error">{error}</div>}

      <div className="access-filter-bar">
        <div aria-label="汇总粒度" className="access-granularity" role="tablist">
          {granularities.map((item) => <button aria-selected={granularity === item.value} className={granularity === item.value ? "active" : ""} key={item.value} onClick={() => changeGranularity(item.value)} role="tab" type="button">{item.label}</button>)}
        </div>
        <form className="access-date-filter" onSubmit={handleDateFilterSubmit}>
          <label>开始日期<input aria-label="访问统计开始日期" max={endInput || undefined} onChange={(event) => setStartInput(event.target.value)} onInput={(event) => setStartInput(event.currentTarget.value)} onKeyDown={handleDateInputKeyDown} type="date" value={startInput} /></label>
          <span>至</span>
          <label>结束日期<input aria-label="访问统计结束日期" min={startInput || undefined} onChange={(event) => setEndInput(event.target.value)} onInput={(event) => setEndInput(event.currentTarget.value)} onKeyDown={handleDateInputKeyDown} type="date" value={endInput} /></label>
          <button className="button button-secondary" onClick={applyDateRange} type="button"><CalendarDays size={15} />查询</button>
        </form>
        <label className="access-user-filter">用户<select aria-label="按用户筛选访问统计" onChange={(event) => setUserId(event.target.value)} value={userId}><option value="">全部用户</option>{report?.users.map((user) => <option key={user.user_id} value={user.user_id}>{user.display_name}（{user.username}）</option>)}</select></label>
      </div>

      <section aria-label="访问统计概览" className="metrics-grid access-metrics">
        <div className="metric"><div className="metric-label">访问次数</div><div className="metric-value">{summary.visit_count}<span className="metric-detail">次</span></div></div>
        <div className="metric"><div className="metric-label">登录次数</div><div className="metric-value">{summary.login_count}<span className="metric-detail">次</span></div></div>
        <div className="metric"><div className="metric-label">活跃用户</div><div className="metric-value">{summary.active_user_count}<span className="metric-detail">人</span></div></div>
        <div className="metric"><div className="metric-label">总访问时长</div><div className="metric-value access-duration-value">{formatAccessDuration(summary.total_duration_seconds)}</div></div>
        <div className="metric"><div className="metric-label">平均访问时长</div><div className="metric-value access-duration-value">{formatAccessDuration(summary.average_duration_seconds)}</div></div>
      </section>

      <section className="content-panel access-period-panel">
        <div className="section-title"><div><h2><Activity size={16} />按{periodName[granularity]}汇总</h2><span>{periods.length} 个时间段 · 北京时间</span></div><Clock3 size={16} /></div>
        <div className="access-table-wrap"><table className="access-table"><thead><tr><th>时间段</th><th>访问次数</th><th>登录次数</th><th>活跃用户</th><th>总访问时长</th><th>平均访问时长</th></tr></thead><tbody>{periods.map((period) => <tr key={period.period_key}><td><strong>{period.period_label}</strong></td><td>{period.visit_count} 次</td><td>{period.login_count} 次</td><td>{period.active_user_count} 人</td><td>{formatAccessDuration(period.total_duration_seconds)}</td><td>{formatAccessDuration(period.average_duration_seconds)}</td></tr>)}</tbody></table></div>
      </section>

      <section className="content-panel access-user-panel">
        <div className="section-title"><div><h2><Users size={16} />用户汇总</h2><span>当前查询范围内的个人访问情况</span></div><Timer size={16} /></div>
        <div className="access-table-wrap"><table className="access-table access-user-table"><thead><tr><th>用户</th><th>访问次数</th><th>登录次数</th><th>活跃{periodName[granularity]}数</th><th>总访问时长</th><th>平均访问时长</th><th>首次访问</th><th>最近访问</th></tr></thead><tbody>{report?.users.map((user) => <tr key={user.user_id}><td><strong>{user.display_name}</strong><small>{user.username}</small></td><td>{user.visit_count} 次</td><td><span className="access-login-count"><LogIn size={13} />{user.login_count} 次</span></td><td>{user.active_period_count}</td><td>{formatAccessDuration(user.total_duration_seconds)}</td><td>{formatAccessDuration(user.average_duration_seconds)}</td><td>{user.first_visit_at ? formatDateTime(user.first_visit_at) : "暂无"}</td><td>{user.last_visit_at ? formatDateTime(user.last_visit_at) : "暂无"}</td></tr>)}</tbody></table></div>
      </section>
    </div>
  );
}
