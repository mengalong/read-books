"use client";

import { KeyRound, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { FormEvent } from "react";

import { ApiError, changePassword } from "@/lib/api";

export default function ChangePasswordPage() {
  const router = useRouter();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (newPassword !== confirmPassword) {
      setError("两次输入的新密码不一致");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await changePassword(currentPassword, newPassword);
      router.replace("/");
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "密码修改失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-panel-wrap">
      <section className="auth-panel">
        <div className="auth-icon"><ShieldCheck size={23} /></div>
        <div className="auth-heading"><span className="eyebrow">First sign-in</span><h1>修改临时密码</h1><p>为了保护你的工作空间，请先设置一个新的登录密码。</p></div>
        <form className="auth-form" onSubmit={handleSubmit}>
          <label htmlFor="current-password">当前密码</label>
          <input autoComplete="current-password" id="current-password" onChange={(event) => setCurrentPassword(event.target.value)} required type="password" value={currentPassword} />
          <label htmlFor="new-password">新密码</label>
          <input autoComplete="new-password" id="new-password" onChange={(event) => setNewPassword(event.target.value)} placeholder="至少 8 位，包含三类字符" required type="password" value={newPassword} />
          <label htmlFor="confirm-password">确认新密码</label>
          <input autoComplete="new-password" id="confirm-password" onChange={(event) => setConfirmPassword(event.target.value)} required type="password" value={confirmPassword} />
          {error && <div className="auth-form-error">{error}</div>}
          <button className="button button-primary auth-submit" disabled={submitting} type="submit"><KeyRound className="auth-submit-leading" size={16} /><span>{submitting ? "正在保存……" : "保存新密码"}</span></button>
        </form>
      </section>
    </main>
  );
}
