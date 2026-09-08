"use client";

import { CalendarRange, CheckCircle2, ChevronLeft, ChevronRight, NotebookPen } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ErrorState } from "@/components/ui";
import { ApiError, getJournalSummaries } from "@/lib/api";
import type { JournalDaySummary } from "@/lib/types";

function localToday() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
}

function shiftAnchor(value: string, period: "week" | "month", direction: number) {
  const date = new Date(`${value}T12:00:00Z`);
  if (period === "week") date.setUTCDate(date.getUTCDate() + direction * 7);
  else date.setUTCMonth(date.getUTCMonth() + direction);
  return date.toISOString().slice(0, 10);
}

function periodLabel(value: string, period: "week" | "month") {
  const date = new Date(`${value}T12:00:00`);
  if (period === "month") return date.toLocaleDateString("zh-CN", { year: "numeric", month: "long" });
  const start = new Date(date);
  start.setDate(start.getDate() - start.getDay() + 1);
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  return `${start.toLocaleDateString("zh-CN", { month: "short", day: "numeric" })} - ${end.toLocaleDateString("zh-CN", { month: "short", day: "numeric" })}`;
}

export default function JournalReviewsPage() {
  const [period, setPeriod] = useState<"week" | "month">("week");
  const [anchor, setAnchor] = useState(localToday);
  const [summaries, setSummaries] = useState<JournalDaySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setSummaries(await getJournalSummaries(period, anchor));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "周期回顾加载失败");
    } finally {
      setLoading(false);
    }
  }, [anchor, period]);

  useEffect(() => { void load(); }, [load]);

  const metrics = useMemo(() => ({
    captures: summaries.reduce((total, day) => total + day.capture_count, 0),
    items: summaries.reduce((total, day) => total + day.item_count, 0),
    completed: summaries.reduce((total, day) => total + day.completed_todo_count, 0),
    mood: summaries.filter((day) => day.mood_score !== null),
  }), [summaries]);
  const averageMood = metrics.mood.length ? (metrics.mood.reduce((total, day) => total + (day.mood_score || 0), 0) / metrics.mood.length).toFixed(1) : "-";

  return <div className="page-wrap journal-page">
    <header className="page-header journal-header">
      <div><div className="eyebrow">Reflection</div><h1 className="page-title">周期回顾</h1><p className="page-description">把每天的记录放在一起，看见这一段时间真正反复出现的事情。</p></div>
      <Link className="button button-secondary" href="/journal"><NotebookPen size={15} />回到今天</Link>
    </header>
    {error && <ErrorState message={error} />}
    <div className="journal-review-toolbar"><div className="journal-review-tabs"><button className={period === "week" ? "active" : ""} onClick={() => setPeriod("week")} type="button">本周</button><button className={period === "month" ? "active" : ""} onClick={() => setPeriod("month")} type="button">本月</button></div><div className="journal-period-nav"><button aria-label="上一个周期" className="button button-quiet" onClick={() => setAnchor((value) => shiftAnchor(value, period, -1))} title="上一个周期" type="button"><ChevronLeft size={16} /></button><span><CalendarRange size={14} />{periodLabel(anchor, period)}</span><button aria-label="下一个周期" className="button button-quiet" onClick={() => setAnchor((value) => shiftAnchor(value, period, 1))} title="下一个周期" type="button"><ChevronRight size={16} /></button></div></div>
    {loading ? <div className="loading-state">正在汇总周期记录……</div> : <>
      <section className="metrics-grid journal-review-metrics"><div className="metric"><div className="metric-label">快速记录</div><div className="metric-value">{metrics.captures}<span className="metric-detail">条</span></div></div><div className="metric"><div className="metric-label">归集项目</div><div className="metric-value">{metrics.items}<span className="metric-detail">项</span></div></div><div className="metric"><div className="metric-label">完成待办</div><div className="metric-value">{metrics.completed}<span className="metric-detail">项</span></div></div><div className="metric"><div className="metric-label">平均心情</div><div className="metric-value">{averageMood}<span className="metric-detail">/ 10</span></div></div></section>
      {summaries.length === 0 ? <div className="journal-empty journal-empty-large"><NotebookPen size={22} /><strong>这个周期还没有记录</strong><span>从今天开始留下几条记录，下次回顾时就会有内容可看。</span></div> : <section className="journal-review-table-panel form-panel"><div className="section-title"><h2>每日轨迹</h2><span>{summaries.length} 天有记录</span></div><div className="journal-review-table-wrap"><table className="journal-review-table"><thead><tr><th>日期</th><th>记录</th><th>归集</th><th>完成待办</th><th>心情</th><th>日记</th></tr></thead><tbody>{summaries.map((day) => <tr key={day.local_date}><td><Link href={`/journal?date=${day.local_date}`}>{new Date(`${day.local_date}T12:00:00`).toLocaleDateString("zh-CN", { month: "short", day: "numeric", weekday: "short" })}</Link></td><td>{day.capture_count}</td><td>{day.item_count}</td><td>{day.completed_todo_count > 0 ? <span className="journal-completed-mark"><CheckCircle2 size={14} />{day.completed_todo_count}</span> : "-"}</td><td>{day.mood_score === null ? "-" : `${day.mood_score} / 10`}</td><td className="journal-review-preview">{day.journal_preview || "尚未生成"}</td></tr>)}</tbody></table></div></section>}
    </>}
  </div>;
}
