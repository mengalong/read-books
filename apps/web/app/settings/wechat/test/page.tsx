"use client";

import {
  ArrowLeft,
  CircleCheck,
  Clock3,
  LogOut,
  RefreshCw,
  ScanLine,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { ErrorState } from "@/components/ui";
import {
  ApiError,
  getWechatDiagnosticLoginUrl,
  getWechatIdentity,
  getWechatLoginConfiguration,
  logoutWechat,
} from "@/lib/api";
import { formatDateTimeLong } from "@/lib/format";
import type { WechatIdentityResponse, WechatLoginConfiguration } from "@/lib/types";
import { useSearchParams } from "next/navigation";

export default function WechatLoginDiagnosticPage() {
  const searchParams = useSearchParams();
  const callbackError = searchParams.get("wechat_error") || "";

  const [configuration, setConfiguration] = useState<WechatLoginConfiguration | null>(null);
  const [identity, setIdentity] = useState<WechatIdentityResponse | null>(null);
  const [loadingConfiguration, setLoadingConfiguration] = useState(true);
  const [loadingIdentity, setLoadingIdentity] = useState(true);
  const [loggingOut, setLoggingOut] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getWechatLoginConfiguration()
      .then((data) => setConfiguration(data))
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "微信登录配置读取失败"))
      .finally(() => setLoadingConfiguration(false));
  }, []);

  useEffect(() => {
    void refreshIdentity();
  }, []);

  async function refreshIdentity() {
    setLoadingIdentity(true);
    try {
      const current = await getWechatIdentity();
      setIdentity(current);
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.status === 401) {
        setIdentity(null);
      } else {
        setError(reason instanceof ApiError ? reason.message : "微信会话读取失败");
      }
    } finally {
      setLoadingIdentity(false);
    }
  }

  async function handleLogout() {
    setLoggingOut(true);
    setError("");
    try {
      await logoutWechat();
      setIdentity(null);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "微信退出失败");
    } finally {
      setLoggingOut(false);
    }
  }

  function handleLogin() {
    window.location.assign(getWechatDiagnosticLoginUrl());
  }

  const ready = Boolean(configuration?.configuration_complete);

  return (
    <div className="page-wrap">
      <header className="page-header compact-header">
        <div>
          <div className="eyebrow">Wechat identity</div>
          <h1 className="page-title">微信登录自检</h1>
          <p className="page-description">独立测试微信开放平台扫码登录、回调落库和当前浏览器的微信会话，不依赖考试链接。</p>
        </div>
        <span className={`status-badge status-${ready ? "completed" : "processing"}`}>{ready ? "配置可用" : "等待配置"}</span>
      </header>

      {callbackError && <ErrorState message={callbackError} />}
      {error && <ErrorState message={error} />}

      <section className="content-panel wechat-settings-form wechat-diagnostic-panel">
        <div className="wechat-configuration-status">
          {ready ? <CircleCheck size={19} /> : <ShieldCheck size={19} />}
          <div>
            <strong>{ready ? "微信登录配置已准备好" : "微信登录配置尚未完整"}</strong>
            <span>{ready ? "点击下面的按钮会直接发起真实扫码登录。" : "请先回到微信登录配置页补齐 AppID、AppSecret 和站点地址。"} </span>
          </div>
        </div>

        <div className="settings-block">
          <div className="model-switch-copy">
            <label>微信授权回调地址</label>
            <span><code className="wechat-callback-url">{configuration?.callback_url || "暂无"}</code></span>
          </div>
          <div className="model-switch-copy">
            <label>启用状态</label>
            <span>{loadingConfiguration ? "正在读取……" : configuration?.enabled ? "已开启微信登录" : "未开启微信登录"}</span>
          </div>
          <div className="model-switch-copy">
            <label>公开考试限制</label>
            <span>{loadingConfiguration ? "正在读取……" : configuration?.required_for_public_exams ? "匿名考试会被微信认证拦截" : "公开考试可继续匿名答题"}</span>
          </div>
        </div>

        <div className="settings-block">
          <div className="section-title">
            <h2>当前微信会话</h2>
            <span>{loadingIdentity ? "检查中" : identity ? "已登录" : "尚未登录"}</span>
          </div>
          {loadingIdentity ? (
            <div className="loading-state">正在读取当前浏览器的微信会话……</div>
          ) : identity ? (
            <div className="wechat-participant">
              <span className="wechat-avatar">{identity.user.avatar_url ? <img alt="" src={identity.user.avatar_url} /> : <UserRound size={17} />}</span>
              <span>
                <strong>{identity.user.nickname}</strong>
                <small><UserRound size={12} />OpenID：{identity.user.openid}</small>
                {identity.user.unionid && <small>UnionID：{identity.user.unionid}</small>}
                <small><Clock3 size={12} />会话到期：{formatDateTimeLong(identity.session.expires_at)}</small>
                {identity.user.last_login_at && <small>最近登录：{formatDateTimeLong(identity.user.last_login_at)}</small>}
              </span>
              <button aria-label="退出微信会话" className="button button-quiet" disabled={loggingOut} onClick={() => void handleLogout()} title="退出微信会话" type="button">
                <LogOut size={14} />
              </button>
            </div>
          ) : (
            <div className="empty-state" style={{ padding: 28 }}>
              <strong>当前浏览器还没有微信会话</strong>
              <p style={{ marginTop: 8 }}>点击“开始微信登录自检”后，扫码成功会回到这个页面并显示微信身份。</p>
            </div>
          )}
        </div>

        <div className="form-actions">
          <Link className="button button-secondary" href="/settings/wechat"><ArrowLeft size={15} />返回配置</Link>
          <button className="button button-secondary" disabled={loadingIdentity} onClick={() => void refreshIdentity()} type="button">
            <RefreshCw className={loadingIdentity ? "spin" : ""} size={15} />
            重新检查
          </button>
          <button className="button button-primary" disabled={!ready} onClick={handleLogin} type="button">
            <ScanLine size={15} />
            开始微信登录自检
          </button>
        </div>
      </section>
    </div>
  );
}
