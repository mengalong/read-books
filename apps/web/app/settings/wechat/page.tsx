"use client";

import { CircleCheck, Eye, EyeOff, KeyRound, Save, ScanLine, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { ErrorState } from "@/components/ui";
import { ApiError, getWechatLoginConfiguration, updateWechatLoginConfiguration } from "@/lib/api";
import type { WechatLoginConfiguration } from "@/lib/types";

const MASKED_SECRET = "****************";

export default function WechatLoginSettingsPage() {
  const [configuration, setConfiguration] = useState<WechatLoginConfiguration | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [required, setRequired] = useState(false);
  const [appId, setAppId] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [callbackBaseUrl, setCallbackBaseUrl] = useState("");
  const [showSecret, setShowSecret] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getWechatLoginConfiguration()
      .then((data) => {
        setConfiguration(data);
        setEnabled(data.enabled);
        setRequired(data.required_for_public_exams);
        setAppId(data.app_id);
        setAppSecret(data.app_secret_configured ? MASKED_SECRET : "");
        setCallbackBaseUrl(data.callback_base_url);
      })
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "微信登录配置加载失败"))
      .finally(() => setLoading(false));
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setSaved(false);
    setError("");
    try {
      const updated = await updateWechatLoginConfiguration({
        enabled,
        required_for_public_exams: enabled && required,
        app_id: appId.trim(),
        app_secret: appSecret && appSecret !== MASKED_SECRET ? appSecret : undefined,
        callback_base_url: callbackBaseUrl.trim(),
      });
      setConfiguration(updated);
      setEnabled(updated.enabled);
      setRequired(updated.required_for_public_exams);
      setAppSecret(updated.app_secret_configured ? MASKED_SECRET : "");
      setSaved(true);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "微信登录配置保存失败");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在读取微信登录配置……</div></div>;

  const ready = Boolean(configuration?.configuration_complete);
  return (
    <div className="page-wrap">
      <header className="page-header compact-header">
        <div><div className="eyebrow">Wechat identity</div><h1 className="page-title">微信登录</h1><p className="page-description">维护公开考试参与者的微信认证配置</p></div>
        <span className={`status-badge status-${enabled && ready ? "completed" : "processing"}`}>{enabled && ready ? "已启用" : ready ? "已配置" : "未配置"}</span>
      </header>

      {error && <ErrorState message={error} />}
      <form className="form-panel model-settings-form wechat-settings-form" onSubmit={(event) => void handleSubmit(event)}>
        <div className="wechat-configuration-status">
          {ready ? <CircleCheck size={19} /> : <ScanLine size={19} />}
          <div><strong>{ready ? "微信开放平台参数已保存" : "等待配置微信开放平台参数"}</strong><span>{enabled && ready ? "公开考试页面已经可以使用微信扫码登录" : "当前不会在公开考试中强制使用微信身份"}</span></div>
        </div>

        <div className="settings-block model-provider-block">
          <div className="model-switch-copy"><label htmlFor="wechat-login-enabled">微信登录</label><span>{enabled ? "在公开考试中提供微信认证" : "不显示微信登录入口"}</span></div>
          <label className="switch-control" htmlFor="wechat-login-enabled"><input checked={enabled} id="wechat-login-enabled" onChange={(event) => { setEnabled(event.target.checked); if (!event.target.checked) setRequired(false); }} type="checkbox" /><span aria-hidden="true" className="switch-track"><span className="switch-thumb" /></span><span className="switch-label">{enabled ? "已开启" : "已关闭"}</span></label>
        </div>

        <div className="settings-block model-provider-block">
          <div className="model-switch-copy"><label htmlFor="wechat-login-required">要求微信认证</label><span>未登录平台账号的参与者必须先微信登录</span></div>
          <label className="switch-control" htmlFor="wechat-login-required"><input checked={required} disabled={!enabled} id="wechat-login-required" onChange={(event) => setRequired(event.target.checked)} type="checkbox" /><span aria-hidden="true" className="switch-track"><span className="switch-thumb" /></span><span className="switch-label">{required ? "已开启" : "已关闭"}</span></label>
        </div>

        <div className="form-grid model-fields">
          <div className="field"><label htmlFor="wechat-app-id">AppID</label><input id="wechat-app-id" onChange={(event) => setAppId(event.target.value)} placeholder="微信开放平台网站应用 AppID" value={appId} /></div>
          <div className="field"><label htmlFor="wechat-app-secret">AppSecret</label><div className="secret-input"><input autoComplete="off" id="wechat-app-secret" onBlur={() => { if (!appSecret && configuration?.app_secret_configured) setAppSecret(MASKED_SECRET); }} onChange={(event) => setAppSecret(event.target.value)} onFocus={() => { if (appSecret === MASKED_SECRET) setAppSecret(""); }} placeholder="输入 AppSecret" type={showSecret ? "text" : "password"} value={appSecret} /><button aria-label={showSecret ? "隐藏 AppSecret" : "显示 AppSecret"} onClick={() => setShowSecret((value) => !value)} title={showSecret ? "隐藏 AppSecret" : "显示 AppSecret"} type="button">{showSecret ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></div>
          <div className="key-status field-full"><KeyRound size={13} />{configuration?.app_secret_configured ? "已保存密钥，输入新值后保存即可更新" : "未保存密钥"}</div>
          <div className="field field-full"><label htmlFor="wechat-callback-base-url">站点地址</label><input id="wechat-callback-base-url" onChange={(event) => setCallbackBaseUrl(event.target.value)} placeholder="https://books.example.com" type="url" value={callbackBaseUrl} /></div>
          <div className="field field-full"><label>微信授权回调地址</label><code className="wechat-callback-url">{callbackBaseUrl.trim().replace(/\/$/, "") || "https://books.example.com"}/api/public/wechat/callback</code></div>
        </div>

        <div className="wechat-platform-note"><ShieldCheck size={17} /><span>启用前需要在微信开放平台完成网站应用审核，并将上方回调域名加入授权回调域。公网环境必须使用 HTTPS。</span></div>
        <div className="form-actions">
          <Link className="button button-secondary" href="/settings/wechat/test"><ScanLine size={15} />微信登录自检</Link>
          {saved && <span className="save-confirmation"><CircleCheck size={14} />配置已保存</span>}
          <button className="button button-primary" disabled={saving} type="submit"><Save size={15} />{saving ? "保存中……" : "保存配置"}</button>
        </div>
      </form>
    </div>
  );
}
