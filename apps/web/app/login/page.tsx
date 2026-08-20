"use client";

import { ArrowRight, Eye, EyeOff, LockKeyhole } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { FormEvent } from "react";

import { SiteFooter } from "@/components/site-footer";
import { ApiError, login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const user = await login(username, password);
      router.replace(user.must_change_password ? "/change-password" : "/");
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "登录失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page-shell">
      <main className="auth-panel-wrap">
        <section className="auth-panel">
          <div className="auth-brand"><span className="brand-mark">卷</span><span><strong>回卷</strong><small>读书复习系统</small></span></div>
          <div className="auth-heading"><span className="eyebrow">Welcome back</span><h1>登录回卷</h1><p>进入你的阅读工作空间，继续下一次主动回忆。</p></div>
          <form className="auth-form" onSubmit={handleSubmit}>
            <label htmlFor="username">账户名</label>
            <input autoComplete="username" id="username" onChange={(event) => setUsername(event.target.value)} placeholder="请输入账户名" required value={username} />
            <label htmlFor="password">密码</label>
            <div className="password-input-wrap">
              <input autoComplete="current-password" id="password" onChange={(event) => setPassword(event.target.value)} placeholder="请输入密码" required type={showPassword ? "text" : "password"} value={password} />
              <button aria-label={showPassword ? "隐藏密码" : "显示密码"} className="password-toggle" onClick={() => setShowPassword((visible) => !visible)} title={showPassword ? "隐藏密码" : "显示密码"} type="button">
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            {error && <div className="auth-form-error">{error}</div>}
            <button className="button button-primary auth-submit" disabled={submitting} type="submit"><LockKeyhole className="auth-submit-leading" size={16} /><span>{submitting ? "正在登录……" : "登录"}</span><ArrowRight className="auth-submit-trailing" size={16} /></button>
          </form>
          <p className="auth-footnote">账户由管理员创建。如遇到登录问题，请联系管理员。</p>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
