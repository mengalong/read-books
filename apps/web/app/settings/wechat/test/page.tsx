"use client";

import {
  ArrowLeft,
  Clock3,
  Copy,
  LogOut,
  RefreshCw,
  ScanLine,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { ErrorState } from "@/components/ui";
import { copyText } from "@/lib/clipboard";
import {
  ApiError,
  getWechatDiagnosticLoginUrl,
  getWechatIdentity,
  getWechatLoginConfiguration,
  logoutWechat,
} from "@/lib/api";
import { formatDateTimeLong } from "@/lib/format";
import type { WechatIdentityResponse, WechatLoginConfiguration } from "@/lib/types";

const MASKED_ADMIN_COOKIE = "huijuan_session=<管理员会话>";
const WECHAT_OAUTH_COOKIE_JAR = "/tmp/huijuan-wechat-oauth.cookie";
const DEFAULT_SITE_ORIGIN = "https://books.example.com";

type DiagnosticStep = {
  id: string;
  title: string;
  request: string;
  expectation: string;
  curl: string;
  note?: string;
  kind?: "session";
};

function shellQuote(value: string) {
  return `'${value.replaceAll("'", "'\\''")}'`;
}

function getSiteBaseUrl(configuration: WechatLoginConfiguration | null) {
  const callbackUrl = configuration?.callback_url?.trim();
  if (callbackUrl) return callbackUrl.replace(/\/api\/public\/wechat\/callback$/, "");
  return configuration?.callback_base_url?.trim().replace(/\/$/, "") || DEFAULT_SITE_ORIGIN;
}

function buildCurl(url: string, options: string[]) {
  return [`curl -i \\`, ...options.map((line) => `  ${line} \\`), `  ${shellQuote(url)}`].join("\n");
}

function buildDiagnosticSteps(configuration: WechatLoginConfiguration | null): DiagnosticStep[] {
  const siteBaseUrl = getSiteBaseUrl(configuration).replace(/\/$/, "");
  const apiBaseUrl = `${siteBaseUrl}/api`;
  const configUrl = `${apiBaseUrl}/settings/wechat-login`;
  const diagnosticLoginUrl = `${apiBaseUrl}/public/wechat/diagnostic/login`;
  const callbackUrl = `${apiBaseUrl}/public/wechat/callback`;
  const identityUrl = `${apiBaseUrl}/public/wechat/me`;
  const logoutUrl = `${apiBaseUrl}/public/wechat/logout`;
  return [
    {
      id: "configuration",
      title: "读取当前配置",
      request: `GET ${configUrl}`,
      expectation: "200 OK，返回 AppID、回调地址、启用状态和 configuration_complete；不会返回 AppSecret 明文。",
      curl: buildCurl(configUrl, [`-b ${shellQuote(MASKED_ADMIN_COOKIE)}`]),
    },
    {
      id: "diagnostic-login",
      title: "发起诊断登录",
      request: `GET ${diagnosticLoginUrl}`,
      expectation: "307 Temporary Redirect，Location 指向 open.weixin.qq.com/connect/qrconnect，并写入 huijuan_wechat_oauth Cookie。",
      curl: buildCurl(diagnosticLoginUrl, [
        `-c ${shellQuote(WECHAT_OAUTH_COOKIE_JAR)}`,
        `-b ${shellQuote(WECHAT_OAUTH_COOKIE_JAR)}`,
      ]),
      note: "如果微信授权页直接提示 scope 参数错误或没有 scope 权限，通常是微信开放平台网站应用、授权域名或 Scope 权限没配好，不是回调和会话代码的问题。",
    },
    {
      id: "callback",
      title: "微信回调落库",
      request: `GET ${callbackUrl}?code=<微信回调 code>&state=<第 2 步返回的 state>`,
      expectation: "303 See Other，回跳 /settings/wechat/test，并写入 huijuan_wechat_session Cookie。",
      curl: buildCurl(`${callbackUrl}?code=<微信回调 code>&state=<第 2 步返回的 state>`, [
        `-c ${shellQuote(WECHAT_OAUTH_COOKIE_JAR)}`,
        `-b ${shellQuote(WECHAT_OAUTH_COOKIE_JAR)}`,
      ]),
    },
    {
      id: "identity",
      title: "读取当前会话",
      request: `GET ${identityUrl}`,
      expectation: "200 OK 时返回当前微信身份和会话；401 说明回调或 Cookie 还没写入成功。",
      curl: buildCurl(identityUrl, [`-b ${shellQuote(WECHAT_OAUTH_COOKIE_JAR)}`]),
      kind: "session",
    },
    {
      id: "logout",
      title: "退出当前会话",
      request: `POST ${logoutUrl}`,
      expectation: "204 No Content，撤销当前微信会话并清空 Cookie；随后再查 /api/public/wechat/me 应该返回 401。",
      curl: buildCurl(logoutUrl, [`-b ${shellQuote(WECHAT_OAUTH_COOKIE_JAR)}`, "-X POST"]),
    },
  ];
}

function StepCard({
  step,
  index,
  onCopy,
  loadingIdentity,
  identity,
  onLogout,
  loggingOut,
}: {
  step: DiagnosticStep;
  index: number;
  onCopy: (command: string) => void;
  loadingIdentity: boolean;
  identity: WechatIdentityResponse | null;
  onLogout: () => void;
  loggingOut: boolean;
}) {
  return (
    <article className="wechat-diagnostic-step">
      <div className="wechat-diagnostic-step-header">
        <div className="wechat-diagnostic-step-heading">
          <strong>第 {index + 1} 步 · {step.title}</strong>
          <span>{step.request}</span>
        </div>
        <button
          aria-label={`复制第 ${index + 1} 步命令`}
          className="button button-secondary wechat-diagnostic-step-copy"
          onClick={() => onCopy(step.curl)}
          title="复制 curl 命令"
          type="button"
        >
          <Copy size={14} />
          复制命令
        </button>
      </div>

      <div className="model-switch-copy">
        <label>预期结果</label>
        <span>{step.expectation}</span>
      </div>

      {step.note && (
        <div className="wechat-platform-note">
          <ShieldCheck size={17} />
          <span>{step.note}</span>
        </div>
      )}

      {step.kind === "session" && (
        <div className="settings-block wechat-diagnostic-session">
          <div className="model-switch-copy">
            <label>当前状态</label>
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
              <button aria-label="退出微信会话" className="button button-quiet" disabled={loggingOut} onClick={onLogout} title="退出微信会话" type="button">
                <LogOut size={14} />
              </button>
            </div>
          ) : (
            <div className="empty-state" style={{ padding: 28 }}>
              <strong>当前浏览器还没有微信会话</strong>
              <p style={{ marginTop: 8 }}>先执行第 2 步和第 3 步，再回来查第 4 步。</p>
            </div>
          )}
        </div>
      )}

      <pre className="wechat-diagnostic-command">{step.curl}</pre>
    </article>
  );
}

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

  async function handleCopy(command: string) {
    setError("");
    try {
      await copyText(command);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "命令复制失败");
    }
  }

  const ready = Boolean(configuration?.configuration_complete);
  const steps = buildDiagnosticSteps(configuration);

  return (
    <div className="page-wrap">
      <header className="page-header compact-header">
        <div>
          <div className="eyebrow">Wechat identity</div>
          <h1 className="page-title">微信登录自检</h1>
          <p className="page-description">按顺序验证配置读取、扫码授权、回调落库、会话读取和退出；自检链路不会修改正式开关。</p>
        </div>
        <span className={`status-badge status-${ready ? "completed" : "processing"}`}>{ready ? "诊断可用" : "待补配置"}</span>
      </header>

      {callbackError && <ErrorState message={callbackError} />}
      {error && <ErrorState message={error} />}

      <section className="content-panel wechat-settings-form wechat-diagnostic-panel">
        <div className="settings-block">
          <div className="model-switch-copy">
            <label>AppID</label>
            <span>{loadingConfiguration ? "正在读取……" : configuration?.app_id || "暂无"}</span>
          </div>
          <div className="model-switch-copy">
            <label>AppSecret</label>
            <span>{loadingConfiguration ? "正在读取……" : configuration ? (configuration.app_secret_configured ? "已保存" : "未保存") : "暂无"}</span>
          </div>
          <div className="model-switch-copy">
            <label>授权回调地址</label>
            <span><code className="wechat-callback-url">{configuration?.callback_url || "暂无"}</code></span>
          </div>
          <div className="model-switch-copy">
            <label>诊断状态</label>
            <span>{loadingConfiguration ? "正在读取……" : configuration ? (ready ? "可以直接执行全流程自检" : "请先补齐 AppID、AppSecret 和回调地址") : "暂无可用配置"}</span>
          </div>
          <div className="model-switch-copy">
            <label>正式开关</label>
            <span>{loadingConfiguration ? "正在读取……" : configuration ? (configuration.enabled ? "已开启，公开考试会使用微信登录" : "已关闭，公开考试暂不启用微信登录") : "暂无可用配置"}</span>
          </div>
          <div className="model-switch-copy">
            <label>公开考试限制</label>
            <span>{loadingConfiguration ? "正在读取……" : configuration ? (configuration.required_for_public_exams ? "匿名考试会被微信认证拦截" : "公开考试可继续匿名答题") : "暂无可用配置"}</span>
          </div>
        </div>

        <div className="wechat-platform-note">
          <ShieldCheck size={17} />
          <span>第 1 步需要管理员会话 Cookie。第 2 - 5 步建议共用 /tmp/huijuan-wechat-oauth.cookie，把 OAuth 状态和最终微信会话留在同一个 cookie jar 里；如果微信授权页直接报 scope 参数错误或没有 scope 权限，优先检查微信开放平台网站应用、授权域名和 Scope 权限。</span>
        </div>

        <div className="wechat-diagnostic-steps">
          {steps.map((step, index) => (
            <StepCard
              identity={identity}
              index={index}
              key={step.id}
              loadingIdentity={loadingIdentity}
              onCopy={(command) => void handleCopy(command)}
              onLogout={() => void handleLogout()}
              loggingOut={loggingOut}
              step={step}
            />
          ))}
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
