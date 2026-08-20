"use client";

import { CircleCheck, Link2, Save, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { ErrorState } from "@/components/ui";
import { ApiError, getSiteFooterConfiguration, updateSiteFooterConfiguration } from "@/lib/api";
import type { SiteFooterConfiguration } from "@/lib/types";

export default function SiteFooterSettingsPage() {
  const [configuration, setConfiguration] = useState<SiteFooterConfiguration | null>(null);
  const [recordNumber, setRecordNumber] = useState("");
  const [recordUrl, setRecordUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getSiteFooterConfiguration()
      .then((data) => {
        setConfiguration(data);
        setRecordNumber(data.record_number);
        setRecordUrl(data.record_url);
      })
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "备案设置加载失败"))
      .finally(() => setLoading(false));
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setSaved(false);
    setError("");
    try {
      const updated = await updateSiteFooterConfiguration({
        record_number: recordNumber.trim(),
        record_url: recordUrl.trim(),
      });
      setConfiguration(updated);
      setRecordNumber(updated.record_number);
      setRecordUrl(updated.record_url);
      setSaved(true);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "备案设置保存失败");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在读取备案设置……</div></div>;

  const previewReady = Boolean(recordNumber.trim() && recordUrl.trim());
  const ready = Boolean(configuration?.configuration_complete);
  return (
    <div className="page-wrap">
      <header className="page-header compact-header">
        <div>
          <div className="eyebrow">Site footer</div>
          <h1 className="page-title">备案设置</h1>
          <p className="page-description">填写备案号和备案号链接后，会自动显示在网站底部。</p>
        </div>
        <span className={`status-badge status-${ready ? "completed" : "processing"}`}>{ready ? "已配置" : "未配置"}</span>
      </header>

      {error && <ErrorState message={error} />}
      <form className="form-panel model-settings-form site-settings-form" onSubmit={(event) => void handleSubmit(event)}>
        <div className="settings-block model-provider-block">
          <div className="model-switch-copy">
            <label>底部备案信息</label>
            <span>管理员保存后，公开站点与应用主站都会同步更新。</span>
          </div>
        </div>

        <div className="form-grid model-fields site-footer-fields">
          <div className="field field-full">
            <label htmlFor="site-record-number">备案号</label>
            <input
              id="site-record-number"
              onChange={(event) => setRecordNumber(event.target.value)}
              placeholder="京ICP备12345678号"
              value={recordNumber}
            />
          </div>
          <div className="field field-full">
            <label htmlFor="site-record-url">备案号链接</label>
            <input
              id="site-record-url"
              onChange={(event) => setRecordUrl(event.target.value)}
              placeholder="https://beian.miit.gov.cn/"
              type="url"
              value={recordUrl}
            />
          </div>
        </div>

        <div className="site-footer-preview">
          <div className="site-footer-preview-title">
            <Link2 size={15} />
            <span>网站底部预览</span>
          </div>
          {previewReady ? (
            <a href={recordUrl.trim()} rel="noreferrer" target="_blank">
              备案号 {recordNumber.trim()}
            </a>
          ) : (
            <span>保存后这里会显示备案链接预览。</span>
          )}
        </div>

        <div className="site-footer-note">
          <ShieldCheck size={17} />
          <span>备案号会显示在全站底部；清空两个字段并保存可移除展示。</span>
        </div>

        <div className="form-actions">
          {saved && <span className="save-confirmation"><CircleCheck size={14} />配置已保存</span>}
          <button className="button button-primary" disabled={saving} type="submit">
            <Save size={15} />
            {saving ? "保存中……" : "保存配置"}
          </button>
        </div>
      </form>
    </div>
  );
}
