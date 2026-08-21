"use client";

import { AlertTriangle, ArrowLeft, Clock3, FileQuestion, LoaderCircle, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { QuizQuestionEditList } from "@/components/quiz-question-edit-list";
import { ErrorState } from "@/components/ui";
import {
  ApiError,
  deleteExamShareVersion,
  getEditableExamShare,
  regenerateExamShareQuestion,
  updateExamShareQuestion,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { ExamShareEdit, Question } from "@/lib/types";

const questionTypeLabels = {
  single: "单项选择题",
  multiple: "多项选择题",
  short: "问答题",
} as const;

export default function ExamShareEditPage() {
  const params = useParams<{ shareId: string }>();
  const [share, setShare] = useState<ExamShareEdit | null>(null);
  const [loading, setLoading] = useState(true);
  const [workingVersion, setWorkingVersion] = useState<number | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setShare(await getEditableExamShare(params.shareId));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "考试编辑页加载失败");
    } finally {
      setLoading(false);
    }
  }, [params.shareId]);

  useEffect(() => {
    void load();
  }, [load]);

  const overview = useMemo(() => {
    if (!share) return [];
    return (["single", "multiple", "short"] as const)
      .map((type) => {
        const items = share.questions.filter((question) => question.question_type === type);
        return {
          type,
          label: questionTypeLabels[type],
          count: items.length,
          score: items.reduce((sum, question) => sum + question.max_score, 0),
        };
      })
      .filter((item) => item.count > 0);
  }, [share]);

  function handleQuestionSaved(_: Question) {
    void load();
  }

  async function handleDeleteVersion(version: number) {
    if (!window.confirm(`确认删除历史版本 v${version} 吗？已开始或已完成的答卷不会受影响。`)) return;
    setWorkingVersion(version);
    setError("");
    try {
      await deleteExamShareVersion(share?.id || params.shareId, version);
      await load();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "历史版本删除失败");
    } finally {
      setWorkingVersion(null);
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在打开考试编辑器……</div></div>;
  if (!share) return <div className="page-wrap"><ErrorState message={error || "未找到这场考试"} /></div>;

  return (
    <div className="page-wrap">
      <Link className="back-link" href={`/exam-management/${share.id}`}><ArrowLeft size={14} />返回考试详情</Link>
      {error && <div className="toast-error">{error}</div>}
      <header className="page-header">
        <div>
          <div className="eyebrow">Exam editor</div>
          <h1 className="page-title">{share.name}</h1>
          <p className="page-description">{share.book_title} · {share.quiz_title}</p>
        </div>
        <div className="quiz-editor-summary">
          <div><Clock3 size={16} />v{share.snapshot_version}</div>
          <div><FileQuestion size={16} />{share.questions.length} 道题</div>
        </div>
      </header>

      <div className="quiz-choice-layout">
        <section className="content-panel">
          <div className="section-title"><h2>题型概览</h2><span>逐题修改题干、选项和标准答案</span></div>
          <div className="quiz-choice-items">
            {overview.map((item) => (
              <div className="quiz-choice-item" key={item.type}>
                <div className="count-icon"><FileQuestion size={17} /></div>
                <div><strong>{item.label}</strong><span>{item.count} 道 · {item.score} 分</span></div>
              </div>
            ))}
          </div>
          <div className="quiz-choice-note"><AlertTriangle size={16} />当前编辑的是考试快照版本，新版本会只影响后续开始的答题。</div>
        </section>
        <aside className="quiz-settings-summary">
          <div className="eyebrow">编辑模式</div>
          <strong>v{share.snapshot_version}</strong>
          <p>历史版本会保留，单题重出和保存后会生成新的版本。</p>
          <dl>
            <div><dt>题目数</dt><dd>{share.questions.length} 题</dd></div>
            <div><dt>难度</dt><dd>{share.difficulty === "easy" ? "基础" : share.difficulty === "hard" ? "深入" : "适中"}</dd></div>
            <div><dt>状态</dt><dd>{share.status === "active" ? "分享中" : share.status === "stopped" ? "已停止" : share.status === "expired" ? "已过期" : "原试卷已删除"}</dd></div>
          </dl>
        </aside>
      </div>

      <section className="content-panel quiz-question-edit-panel">
        <div className="section-title"><h2>题目编辑</h2><span>直接修改每道题的题干、选项和标准答案</span></div>
        <QuizQuestionEditList
          onRegenerateQuestion={(questionId) => regenerateExamShareQuestion(share.id, questionId)}
          onSaved={handleQuestionSaved}
          onUpdateQuestion={(questionId, payload) => updateExamShareQuestion(share.id, questionId, payload)}
          questions={share.questions}
        />
      </section>

      <section className="content-panel">
        <div className="section-title"><h2>历史版本</h2><span>{share.versions.length} 个版本</span></div>
        {share.versions.length === 0 ? (
          <div className="loading-state">还没有版本记录。</div>
        ) : (
          <div className="exam-table-wrap">
            <table className="exam-table">
              <thead>
                <tr>
                  <th>版本</th>
                  <th>题目数</th>
                  <th>总分</th>
                  <th>创建时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {share.versions.map((version) => (
                  <tr key={version.version}>
                    <td>
                      <div className="exam-cell-stack">
                        <strong>v{version.version} {version.is_current ? "· 当前" : ""}</strong>
                        <span>单选 {version.single_count} · 多选 {version.multiple_count} · 问答 {version.short_count}</span>
                      </div>
                    </td>
                    <td>{version.question_count} 题</td>
                    <td>{version.max_score} 分</td>
                    <td>{formatDateTime(version.created_at)}</td>
                    <td>
                      <div className="table-actions">
                        {version.is_current ? (
                          <span className="exam-disabled-icon" title="当前版本不能删除"><Trash2 size={15} /></span>
                        ) : (
                          <button
                            aria-label={`删除历史版本 v${version.version}`}
                            className="button button-quiet danger-action"
                            disabled={workingVersion === version.version}
                            onClick={() => void handleDeleteVersion(version.version)}
                            title="删除历史版本"
                            type="button"
                          >
                            {workingVersion === version.version ? <LoaderCircle className="spin" size={15} /> : <Trash2 size={15} />}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
