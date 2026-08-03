"use client";

import { AlertCircle, CircleCheck, Clock3, Eye, EyeOff, KeyRound, LoaderCircle, PlugZap, Save, ServerCog } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { ErrorState } from "@/components/ui";
import {
  ApiError,
  getModelConfiguration,
  testModelConnection,
  updateModelConfiguration,
} from "@/lib/api";
import type { ModelConfiguration, ModelProviderMode } from "@/lib/types";
import { formatDateTimeLong } from "@/lib/format";

const MASKED_API_KEY = "****************";

export default function ModelSettingsPage() {
  const [configuration, setConfiguration] = useState<ModelConfiguration | null>(null);
  const [providerMode, setProviderMode] = useState<ModelProviderMode>("mock");
  const [baseUrl, setBaseUrl] = useState("");
  const [modelName, setModelName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [timeoutMs, setTimeoutMs] = useState(180_000);
  const [temperature, setTemperature] = useState(0.2);
  const [showApiKey, setShowApiKey] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string; latencyMs: number; modelResponse?: string; testedAt: string } | null>(null);
  const [testError, setTestError] = useState("");
  const [curlPreview, setCurlPreview] = useState("");

  useEffect(() => {
    getModelConfiguration()
      .then((data) => {
        setConfiguration(data);
        setProviderMode(data.provider_mode);
        setBaseUrl(data.base_url);
        setModelName(data.model_name);
        setApiKey(data.api_key_configured ? MASKED_API_KEY : "");
        setTimeoutMs(data.timeout_ms);
        setTemperature(data.temperature);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof ApiError ? reason.message : "模型配置加载失败");
      })
      .finally(() => setLoading(false));
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setSaved(false);
    setError("");
    try {
      const updated = await updateModelConfiguration({
        provider_mode: providerMode,
        base_url: baseUrl,
        model_name: modelName,
        api_key: apiKey && apiKey !== MASKED_API_KEY ? apiKey : undefined,
        clear_api_key: false,
        timeout_ms: timeoutMs,
        temperature,
      });
      setConfiguration(updated);
      setApiKey(updated.api_key_configured ? MASKED_API_KEY : "");
      setSaved(true);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "模型配置保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleTestConnection() {
    setTesting(true);
    setError("");
    setTestResult(null);
    setTestError("");
    setCurlPreview(buildCurlPreview());
    try {
      const result = await testModelConnection({
        base_url: baseUrl,
        model_name: modelName,
        api_key: apiKey && apiKey !== MASKED_API_KEY ? apiKey : undefined,
        clear_api_key: false,
        timeout_ms: timeoutMs,
      });
      setTestResult({ ok: result.ok, message: result.message, latencyMs: result.latency_ms, modelResponse: result.model_response || undefined, testedAt: result.tested_at });
      setTestError(result.ok ? "" : result.message);
      setConfiguration((current) => current ? {
        ...current,
        last_test_status: result.ok ? "success" : "failed",
        last_test_message: result.message,
        last_tested_at: result.tested_at,
        last_test_latency_ms: result.latency_ms,
      } : current);
    } catch (reason: unknown) {
      setTestError(reason instanceof ApiError ? reason.message : "模型接口测试失败");
    } finally {
      setTesting(false);
    }
  }

  function formatTestTime(value: string | null) {
    if (!value) return "尚未测试连接";
    return formatDateTimeLong(value);
  }

  function buildCurlPreview() {
    const normalizedBaseUrl = baseUrl.trim().replace(/\/$/, "");
    const endpoint = normalizedBaseUrl.endsWith("/chat/completions")
      ? normalizedBaseUrl
      : `${normalizedBaseUrl}/chat/completions`;
    const requestBody = JSON.stringify({
      model: modelName.trim(),
      messages: [{ role: "user", content: "请只回复：连接成功" }],
      max_tokens: 16,
      temperature: 0,
      stream: false,
    });
    const shellQuote = (value: string) => `'${value.replaceAll("'", "'\\''")}'`;
    const headers = [
      `  -H ${shellQuote("Content-Type: application/json")}`,
      ...((apiKey.trim() && apiKey !== MASKED_API_KEY) || configuration?.api_key_configured
        ? [`  -H ${shellQuote("Authorization: Bearer ***")}`]
        : []),
    ];
    return [`curl ${shellQuote(endpoint)} \\`, ...headers.map((line) => `${line} \\`), `  --data-raw ${shellQuote(requestBody)}`].join("\n");
  }

  if (loading) {
    return <div className="page-wrap"><div className="loading-state">正在读取模型配置……</div></div>;
  }

  return (
    <div className="page-wrap">
      <header className="page-header compact-header">
        <div>
          <div className="eyebrow">Model provider</div>
          <h1 className="page-title">模型设置</h1>
        </div>
        <span className={`status-badge status-${providerMode === "mock" ? "processing" : "completed"}`}>
          {providerMode === "mock" ? "内部模拟接口" : "已配置模型"}
        </span>
      </header>

      {error && <ErrorState message={error} />}
      <form className="form-panel model-settings-form" onSubmit={(event) => void handleSubmit(event)}>
        <div className={`model-link-status ${configuration?.last_test_status || "untested"}`}>
          {configuration?.last_test_status === "success" ? <CircleCheck size={19} /> : configuration?.last_test_status === "failed" ? <AlertCircle size={18} /> : <Clock3 size={18} />}
          <div>
            <strong>模型链接状态</strong>
            <span>{configuration?.last_test_status === "success" ? "最近一次测试连接成功" : configuration?.last_test_status === "failed" ? "最近一次测试连接失败" : "尚未测试连接"}</span>
            {configuration?.last_tested_at && <small>{formatTestTime(configuration.last_tested_at)}{configuration.last_test_latency_ms === null ? "" : ` · ${configuration.last_test_latency_ms} ms`}</small>}
          </div>
        </div>
        <div className="settings-block model-provider-block">
          <div className="model-switch-copy">
            <label htmlFor="use-configured-model">出题与评分模式</label>
            <span>{providerMode === "openai_compatible" ? "使用已配置模型" : "使用内部模拟接口"}</span>
          </div>
          <label className="switch-control" htmlFor="use-configured-model">
            <input
              checked={providerMode === "openai_compatible"}
              id="use-configured-model"
              onChange={(event) => setProviderMode(event.target.checked ? "openai_compatible" : "mock")}
              type="checkbox"
            />
            <span className="switch-track" aria-hidden="true"><span className="switch-thumb" /></span>
            <span className="switch-label">{providerMode === "openai_compatible" ? "已开启" : "已关闭"}</span>
          </label>
          <div className="model-mode-hint">
            {providerMode === "openai_compatible"
              ? "开启后，后续出题和评分会使用下面保存的模型配置。"
              : "关闭后，出题和评分使用站内模拟接口，不会访问外部服务。"}
          </div>
        </div>

        {providerMode === "openai_compatible" && (
          <div className="provider-notice" role="status">
            已支持 OpenAI 兼容模型出题和问答评分，建议启用前先完成连接测试。
          </div>
        )}

        <div className="form-grid model-fields">
          <div className="field field-full">
            <label htmlFor="model-base-url">接口地址</label>
            <input id="model-base-url" onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://api.example.com/v1" type="url" value={baseUrl} />
          </div>
          <div className="field field-full">
            <label htmlFor="model-name">模型名称</label>
            <input id="model-name" onChange={(event) => setModelName(event.target.value)} placeholder="model-name" value={modelName} />
          </div>
          <div className="field field-full">
            <label htmlFor="model-api-key">API Key</label>
            <div className="secret-input">
              <input
                autoComplete="off"
                id="model-api-key"
                onChange={(event) => setApiKey(event.target.value)}
                onBlur={() => {
                  if (!apiKey && configuration?.api_key_configured) setApiKey(MASKED_API_KEY);
                }}
                onFocus={() => {
                  if (apiKey === MASKED_API_KEY) setApiKey("");
                }}
                placeholder="输入 API Key"
                type={showApiKey ? "text" : "password"}
                value={apiKey}
              />
              <button aria-label={showApiKey ? "隐藏 API Key" : "显示 API Key"} onClick={() => setShowApiKey((value) => !value)} title={showApiKey ? "隐藏 API Key" : "显示 API Key"} type="button">
                {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <div className="key-status"><KeyRound size={13} />{configuration?.api_key_configured ? "已保存密钥，输入新值后保存即可更新" : "未保存密钥"}</div>
          </div>
          <div className="field">
            <label htmlFor="model-timeout">请求超时（毫秒）</label>
            <input id="model-timeout" max={300000} min={1000} onChange={(event) => setTimeoutMs(Number(event.target.value))} step={1000} type="number" value={timeoutMs} />
          </div>
          <div className="field">
            <label htmlFor="model-temperature">温度：{temperature.toFixed(1)}</label>
            <input id="model-temperature" max={2} min={0} onChange={(event) => setTemperature(Number(event.target.value))} step={0.1} type="range" value={temperature} />
          </div>
        </div>

        <div className="form-actions">
          {saved && <span className="save-confirmation"><ServerCog size={14} />配置已保存</span>}
          {testResult && <span className={`connection-result ${testResult.ok ? "success" : "failure"}`}><PlugZap size={14} />{testResult.message}{testResult.latencyMs === undefined ? "" : ` · ${testResult.latencyMs} ms`}</span>}
          <button className="button button-secondary" disabled={testing} onClick={() => void handleTestConnection()} type="button">
            {testing ? <LoaderCircle className="spin" size={15} /> : <PlugZap size={15} />}
            {testing ? "测试中……" : "测试连接"}
          </button>
          <button className="button button-primary" disabled={saving} type="submit"><Save size={15} />{saving ? "保存中……" : "保存配置"}</button>
        </div>
        {curlPreview && (
          <div className="curl-preview">
            {testError && <div className="connection-error"><AlertCircle size={15} />{testError}</div>}
            <div className="curl-preview-title">本次测试命令 <span>API Key 已脱敏</span></div>
            <pre>{curlPreview}</pre>
            {testResult?.modelResponse && (
              <>
                <div className="curl-response-title">模型实际返回</div>
                <pre className="curl-response">{testResult.modelResponse}</pre>
              </>
            )}
          </div>
        )}
      </form>
    </div>
  );
}
