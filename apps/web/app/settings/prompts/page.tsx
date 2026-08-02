"use client";

import { Eye, FileCode2, History, RotateCcw, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ApiError, getPromptHistory, getPromptTemplates, previewPrompt, resetPromptTemplate, updatePromptTemplate } from "@/lib/api";
import type { PromptPreview, PromptTemplate, PromptType } from "@/lib/types";

const PROMPT_LABELS: Record<PromptType, { label: string; description: string }> = {
  generation: { label: "出题提示词", description: "控制题目生成、题型结构和原文引用要求" },
  grading: { label: "问答评分提示词", description: "控制参考答案、评分要点和作答反馈" },
};

function formatTime(value: string | null) {
  if (!value) return "内置默认模板";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export default function PromptSettingsPage() {
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [history, setHistory] = useState<PromptTemplate[]>([]);
  const [promptType, setPromptType] = useState<PromptType>("generation");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [userPrompt, setUserPrompt] = useState("");
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const currentTemplate = templates.find((template) => template.prompt_type === promptType);
  const variables = currentTemplate?.available_variables || [];
  const promptTitle = PROMPT_LABELS[promptType];

  useEffect(() => {
    getPromptTemplates()
      .then((data) => {
        setTemplates(data);
        const selected = data.find((template) => template.prompt_type === promptType) || data[0];
        if (selected) {
          setPromptType(selected.prompt_type);
          setSystemPrompt(selected.system_prompt);
          setUserPrompt(selected.user_prompt);
        }
      })
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "提示词配置加载失败"))
      .finally(() => setLoading(false));
  }, [promptType]);

  useEffect(() => {
    if (!templates.length) return;
    const selected = templates.find((template) => template.prompt_type === promptType);
    if (selected) {
      setSystemPrompt(selected.system_prompt);
      setUserPrompt(selected.user_prompt);
      setPreview(null);
      setError("");
      getPromptHistory(promptType)
        .then(setHistory)
        .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "提示词历史加载失败"));
    }
  }, [promptType, templates]);

  const dirty = useMemo(() => {
    if (!currentTemplate) return false;
    return systemPrompt !== currentTemplate.system_prompt || userPrompt !== currentTemplate.user_prompt;
  }, [currentTemplate, systemPrompt, userPrompt]);

  function payload() {
    return { system_prompt: systemPrompt, user_prompt: userPrompt };
  }

  async function handleSave() {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const saved = await updatePromptTemplate(promptType, payload());
      setTemplates((current) => current.map((item) => item.prompt_type === promptType ? saved : item));
      setHistory(await getPromptHistory(promptType));
      setNotice(`已保存第 ${saved.version} 版提示词`);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "提示词保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handlePreview() {
    setPreviewing(true);
    setError("");
    setNotice("");
    try {
      setPreview(await previewPrompt(promptType, payload()));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "提示词预览失败");
    } finally {
      setPreviewing(false);
    }
  }

  async function handleReset() {
    setResetting(true);
    setError("");
    setNotice("");
    try {
      const reset = await resetPromptTemplate(promptType);
      setTemplates((current) => current.map((item) => item.prompt_type === promptType ? reset : item));
      setHistory(await getPromptHistory(promptType));
      setNotice(`已恢复默认模板，并保存为第 ${reset.version} 版`);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "默认模板恢复失败");
    } finally {
      setResetting(false);
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在读取提示词配置……</div></div>;

  return (
    <div className="page-wrap">
      <header className="page-header compact-header">
        <div>
          <div className="eyebrow">System management</div>
          <h1 className="page-title">提示词管理</h1>
          <p className="page-description">调整真实模型的出题与问答评分模板</p>
        </div>
        <span className="status-badge status-completed"><FileCode2 size={14} /> 当前版本 v{currentTemplate?.version ?? 0}</span>
      </header>

      {error && <div className="toast-error">{error}</div>}
      {notice && <div className="toast-success">{notice}</div>}

      <div className="prompt-tabs" role="tablist" aria-label="提示词类型">
        {(Object.keys(PROMPT_LABELS) as PromptType[]).map((type) => (
          <button
            aria-selected={promptType === type}
            className={promptType === type ? "active" : ""}
            key={type}
            onClick={() => setPromptType(type)}
            role="tab"
            type="button"
          >
            {PROMPT_LABELS[type].label}
          </button>
        ))}
      </div>

      <div className="prompt-management-grid">
        <section className="form-panel prompt-editor-panel">
          <div className="section-title">
            <div><h2>{promptTitle.label}</h2><span>{promptTitle.description}</span></div>
            <span className="prompt-version">v{currentTemplate?.version ?? 0} · {formatTime(currentTemplate?.updated_at || null)}</span>
          </div>

          <div className="field prompt-field">
            <label htmlFor="system-prompt">系统提示词</label>
            <textarea id="system-prompt" onChange={(event) => setSystemPrompt(event.target.value)} value={systemPrompt} />
          </div>
          <div className="field prompt-field">
            <label htmlFor="user-prompt">用户提示词</label>
            <textarea className="prompt-user-textarea" id="user-prompt" onChange={(event) => setUserPrompt(event.target.value)} value={userPrompt} />
          </div>

          <div className="prompt-variable-row">
            <span>可用变量</span>
            {variables.map((variable) => <code key={variable}>{`{{${variable}}}`}</code>)}
          </div>

          <div className="form-actions">
            <button className="button button-secondary" disabled={resetting || saving} onClick={() => void handleReset()} type="button"><RotateCcw size={15} />{resetting ? "恢复中……" : "恢复默认"}</button>
            <button className="button button-secondary" disabled={previewing || saving} onClick={() => void handlePreview()} type="button"><Eye size={15} />{previewing ? "预览中……" : "预览替换"}</button>
            <button className="button button-primary" disabled={!dirty || saving || resetting} onClick={() => void handleSave()} type="button"><Save size={15} />{saving ? "保存中……" : "保存新版本"}</button>
          </div>
        </section>

        <aside className="prompt-side-panel">
          <section className="content-panel prompt-info-panel">
            <div className="section-title"><h2><History size={16} />历史版本</h2><span>{history.length} 个已保存版本</span></div>
            {history.length === 0 ? <p className="field-hint">当前使用内置默认模板，保存修改后会从第 1 版开始记录。</p> : <div className="prompt-history-list">
              {history.map((item) => <div className={`prompt-history-item ${item.is_active ? "active" : ""}`} key={item.id}>
                <div><strong>v{item.version}{item.is_active ? " · 当前" : ""}</strong><small>{formatTime(item.updated_at)}</small></div>
                {!item.is_active && <button aria-label={`载入第 ${item.version} 版`} onClick={() => { setSystemPrompt(item.system_prompt); setUserPrompt(item.user_prompt); setPreview(null); setNotice(`已载入第 ${item.version} 版，保存后才会启用`); }} title="载入此版本" type="button">载入</button>}
              </div>)}
            </div>}
          </section>
          {preview && <section className="content-panel prompt-preview-panel">
            <div className="section-title"><h2>替换后预览</h2><span>使用示例数据</span></div>
            <div className="prompt-preview-block"><strong>系统提示词</strong><pre>{preview.rendered_system_prompt}</pre></div>
            <div className="prompt-preview-block"><strong>用户提示词</strong><pre>{preview.rendered_user_prompt}</pre></div>
          </section>}
        </aside>
      </div>
    </div>
  );
}
