"use client";

import { ArrowLeft, CheckCircle2, ChevronDown, Clock3, Code2, Copy, FileText, LoaderCircle, MessageSquareText, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { EmptyState, ErrorState } from "@/components/ui";
import { ApiError, getQuizGenerationDebug } from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import { formatDateTime } from "@/lib/format";
import type { QuizGenerationCall, QuizGenerationDebug, QuizQuestionGenerationTrace } from "@/lib/types";

export default function QuizGenerationDebugPage() {
  const params = useParams<{ quizId: string }>();
  const [report, setReport] = useState<QuizGenerationDebug | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      setReport(await getQuizGenerationDebug(params.quizId));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "出题过程加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [params.quizId]);

  if (loading) return <div className="page-wrap"><div className="loading-state">正在读取出题过程……</div></div>;
  if (!report) return <div className="page-wrap"><ErrorState message={error || "未找到出题过程"} /></div>;

  return (
    <div className="page-wrap">
      <Link className="back-link" href={`/quizzes/${report.quiz_id}`}><ArrowLeft size={14} />返回试卷</Link>
      {error && <div className="toast-error">{error}</div>}
      <header className="page-header generation-debug-header">
        <div><div className="eyebrow">Generation trace</div><h1 className="page-title">出题过程 Prompt</h1><p className="page-description">{report.quiz_title} · 查看每道题的模型输入、原始回复和 token 用量。</p></div>
        <button className="button button-secondary" onClick={() => void load()} type="button"><RefreshCw size={15} />刷新记录</button>
      </header>

      <div className="metrics-grid generation-debug-metrics">
        <div className="metric"><div className="metric-label">题目</div><div className="metric-value">{report.questions.length}<span className="metric-detail">道</span></div></div>
        <div className="metric"><div className="metric-label">模型调用</div><div className="metric-value">{report.questions.reduce((sum, item) => sum + item.calls.length, 0) + report.unassigned_calls.length}<span className="metric-detail">次</span></div></div>
        <div className="metric"><div className="metric-label">输入 token</div><div className="metric-value">{report.input_tokens.toLocaleString()}</div></div>
        <div className="metric"><div className="metric-label">输出 token</div><div className="metric-value">{report.output_tokens.toLocaleString()}</div></div>
        <div className="metric"><div className="metric-label">总 token</div><div className="metric-value">{report.total_tokens.toLocaleString()}</div></div>
      </div>

      {!report.questions.some((item) => item.calls.length) && !report.unassigned_calls.length ? <EmptyState title="没有保存的模型调用记录" detail="历史试卷或模拟模式生成的题目可能没有可回看的原始 prompt。" /> : <section className="generation-debug-list">{report.questions.map((question, index) => <QuestionTrace key={question.question_id} question={question} quizTitle={report.quiz_title} defaultOpen={index === 0} />)}{report.unassigned_calls.length > 0 && <section className="generation-debug-unassigned"><div className="section-title"><div><h2>未关联题目调用</h2><span>这些记录没有题目位置标记，通常来自旧版本任务。</span></div></div>{report.unassigned_calls.map((call) => <GenerationCall key={call.id} call={call} />)}</section>}</section>}
    </div>
  );
}

function QuestionTrace({ question, quizTitle, defaultOpen }: { question: QuizQuestionGenerationTrace; quizTitle: string; defaultOpen: boolean }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState("");
  async function copyQuestionTrace() {
    setCopyError("");
    try {
      await copyText(formatQuestionTrace(quizTitle, question));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch (reason: unknown) {
      setCopyError(reason instanceof Error ? reason.message : "复制失败");
    }
  }

  return <article className="generation-debug-question"><div className="generation-debug-question-heading"><div><span className="question-number">第 {question.position} 题</span><h2>{question.prompt}</h2></div><div className="generation-debug-question-tokens"><span>{question.calls.length} 次调用</span><strong>{question.total_tokens.toLocaleString()} token</strong><button aria-label={copied ? "本题调试信息已复制" : "复制本题调试信息"} className="button button-quiet" onClick={() => void copyQuestionTrace()} title="复制本题调试信息" type="button"><Copy size={13} />{copied ? "已复制" : "复制本题"}</button></div></div>{copyError && <div className="generation-debug-error">{copyError}</div>}{question.calls.length === 0 ? <div className="generation-debug-no-call"><FileText size={15} />这道题没有保存到模型调用记录，可能由旧版本任务生成。</div> : <div className="generation-debug-calls">{question.calls.map((call, index) => <GenerationCall call={call} defaultOpen={defaultOpen && index === 0} key={call.id} />)}</div>}</article>;
}

function formatQuestionTrace(quizTitle: string, question: QuizQuestionGenerationTrace): string {
  const lines = [
    `试卷：${quizTitle}`,
    `第 ${question.position} 题`,
    `题干：${question.prompt}`,
    `source_chunk_ids：${question.source_chunk_ids.length ? question.source_chunk_ids.join(", ") : "无"}`,
    `quote_entry_ids：${question.quote_entry_ids.length ? question.quote_entry_ids.join(", ") : "无"}`,
    `调用次数：${question.calls.length}`,
    `输入 token：${question.input_tokens.toLocaleString()}`,
    `输出 token：${question.output_tokens.toLocaleString()}`,
    `总 token：${question.total_tokens.toLocaleString()}`,
  ];
  question.calls.forEach((call, index) => {
    lines.push(
      "",
      `===== 第 ${index + 1} 次模型调用 =====`,
      `阶段：${call.phase}`,
      `时间：${formatDateTime(call.created_at)}`,
      `模型：${call.model_name || "未记录"}`,
      `状态：${call.status === "success" ? "成功" : "失败"}`,
      `延迟：${call.latency_ms.toLocaleString()} ms`,
      `输入 token：${call.input_tokens === null ? "未返回" : call.input_tokens.toLocaleString()}`,
      `输出 token：${call.output_tokens === null ? "未返回" : call.output_tokens.toLocaleString()}`,
      `总 token：${call.total_tokens === null ? "未返回" : call.total_tokens.toLocaleString()}`,
      "",
      "--- 输入 Prompt ---",
    );
    call.request_messages.forEach((message) => lines.push(`[${message.role}]`, message.content));
    lines.push("", "--- 模型回复 ---", call.model_response || "模型没有返回可用文本");
    if (call.error_message) lines.push("", "--- 错误 ---", call.error_message);
  });
  return lines.join("\n");
}

function GenerationCall({ call, defaultOpen = false }: { call: QuizGenerationCall; defaultOpen?: boolean }) {
  const [copied, setCopied] = useState(false);
  async function copyResponse() {
    if (!call.model_response) return;
    await copyText(call.model_response);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }
  return <details className={`generation-debug-call ${call.status === "failed" ? "failed" : ""}`} open={defaultOpen}><summary><span><ChevronDown size={14} /><strong>第 {call.call_number} 次调用</strong><small>{call.phase} · {formatDateTime(call.created_at)}</small></span><span className="generation-debug-call-summary"><b>{call.total_tokens === null ? "token 未返回" : `${call.total_tokens.toLocaleString()} token`}</b><em>{call.status === "success" ? "成功" : "失败"}</em></span></summary><div className="generation-debug-call-body"><div className="generation-debug-call-meta"><span><Clock3 size={13} />{call.latency_ms.toLocaleString()} ms</span><span>输入 {call.input_tokens === null ? "—" : call.input_tokens.toLocaleString()}</span><span>输出 {call.output_tokens === null ? "—" : call.output_tokens.toLocaleString()}</span><span>总计 {call.total_tokens === null ? "—" : call.total_tokens.toLocaleString()}</span></div><div className="generation-debug-block"><div className="generation-debug-block-heading"><strong><MessageSquareText size={14} />输入 Prompt</strong><span>{call.request_messages.length} 条消息</span></div>{call.request_messages.length ? call.request_messages.map((message, index) => <div className="generation-debug-message" key={`${call.id}-message-${index}`}><span>{message.role}</span><pre>{message.content}</pre></div>) : <pre className="generation-debug-empty-code">未保存输入消息</pre>}</div><div className="generation-debug-block"><div className="generation-debug-block-heading"><strong><Code2 size={14} />模型回复</strong>{call.model_response && <button aria-label={copied ? "模型回复已复制" : "复制模型回复"} className="button button-quiet" onClick={(event) => { event.preventDefault(); void copyResponse(); }} title="复制模型回复" type="button"><Copy size={13} />{copied ? "已复制" : "复制"}</button>}</div>{call.model_response ? <pre className="generation-debug-response">{call.model_response}</pre> : <pre className="generation-debug-empty-code">模型没有返回可用文本</pre>}</div>{call.error_message && <div className="generation-debug-error">{call.error_message}</div>}</div></details>;
}
