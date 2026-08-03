"use client";

import { Check, Copy, Eye, KeyRound, Plus, RefreshCw, Shield, UserRound, UserX } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, createAdminUser, getAdminUsers, resetAdminUserPassword, updateAdminUser } from "@/lib/api";
import { formatDateTimeLong } from "@/lib/format";
import type { AdminUser } from "@/lib/types";

export default function UserManagementPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<"admin" | "user">("user");
  const [temporaryPassword, setTemporaryPassword] = useState("");
  const [newCredential, setNewCredential] = useState<{ username: string; password: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setUsers(await getAdminUsers());
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "用户列表加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      const result = await createAdminUser({
        username,
        display_name: displayName,
        role,
        ...(temporaryPassword ? { temporary_password: temporaryPassword } : {}),
      });
      setNewCredential({ username: result.user.username, password: result.temporary_password });
      setUsername("");
      setDisplayName("");
      setTemporaryPassword("");
      setRole("user");
      await load();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "用户创建失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function toggleStatus(user: AdminUser) {
    setError("");
    try {
      await updateAdminUser(user.id, { status: user.status === "active" ? "disabled" : "active" });
      setNotice(user.status === "active" ? `已停用 ${user.display_name}` : `已恢复 ${user.display_name}`);
      await load();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "用户状态更新失败");
    }
  }

  async function resetPassword(user: AdminUser) {
    setError("");
    try {
      const result = await resetAdminUserPassword(user.id);
      setNewCredential({ username: user.username, password: result.temporary_password });
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "临时密码重置失败");
    }
  }

  async function copyCredential() {
    if (!newCredential) return;
    await navigator.clipboard.writeText(`账户名：${newCredential.username}\n临时密码：${newCredential.password}`);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="page-wrap">
      <header className="page-header compact-header">
        <div><div className="eyebrow">System management</div><h1 className="page-title">用户管理</h1><p className="page-description">创建和维护平台账户。临时密码只在创建或重置时展示一次，请线下交付给用户。</p></div>
        <button aria-label="刷新用户列表" className="button button-secondary" disabled={loading} onClick={() => void load()} title="刷新用户列表" type="button"><RefreshCw className={loading ? "spin" : ""} size={15} />刷新</button>
      </header>

      {error && <div className="toast-error">{error}</div>}
      {notice && <div className="toast-success">{notice}</div>}

      <div className="user-management-grid">
        <section className="content-panel">
          <div className="section-title"><div><h2><Plus size={16} />创建账户</h2><span>账户创建后默认需要首次修改密码</span></div></div>
          <form className="form-grid" onSubmit={handleCreate}>
            <div className="field"><label htmlFor="new-username">账户名</label><input id="new-username" onChange={(event) => setUsername(event.target.value)} placeholder="如：reader-01" required value={username} /></div>
            <div className="field"><label htmlFor="new-display-name">显示名称</label><input id="new-display-name" onChange={(event) => setDisplayName(event.target.value)} placeholder="如：林晓" required value={displayName} /></div>
            <div className="field"><label htmlFor="new-role">角色</label><select id="new-role" onChange={(event) => setRole(event.target.value as "admin" | "user")} value={role}><option value="user">普通用户</option><option value="admin">管理员</option></select></div>
            <div className="field"><label htmlFor="temporary-password">指定临时密码 <span className="optional">可选</span></label><input id="temporary-password" onChange={(event) => setTemporaryPassword(event.target.value)} placeholder="留空则自动生成" type="password" value={temporaryPassword} /></div>
            <div className="field-full form-actions"><button className="button button-primary" disabled={submitting} type="submit"><Plus size={15} />{submitting ? "正在创建……" : "创建账户"}</button></div>
          </form>
        </section>

        {newCredential && <section className="credential-panel">
          <div className="credential-heading"><KeyRound size={18} /><div><strong>临时登录凭据</strong><span>请确认已线下交付，关闭后不再自动显示。</span></div></div>
          <div className="credential-value"><small>账户名</small><code>{newCredential.username}</code></div>
          <div className="credential-value"><small>临时密码</small><code>{newCredential.password}</code></div>
          <button className="button button-secondary" onClick={() => void copyCredential()} type="button">{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? "已复制" : "复制凭据"}</button>
          <button className="button button-quiet" onClick={() => setNewCredential(null)} type="button">关闭凭据</button>
        </section>}
      </div>

      <section className="content-panel user-list-panel">
        {loading ? <div className="loading-state">正在读取用户列表……</div> : <div className="user-table-wrap"><table className="user-table"><thead><tr><th>用户</th><th>角色</th><th>工作空间</th><th>状态</th><th>最后登录</th><th>操作</th></tr></thead><tbody>{users.map((user) => <tr key={user.id}><td><strong>{user.display_name}</strong><small>{user.username}</small></td><td><span className="role-badge">{user.role === "admin" ? <Shield size={12} /> : <UserRound size={12} />}{user.role === "admin" ? "管理员" : "普通用户"}</span></td><td>{user.workspace.name}</td><td><span className={`status-badge status-${user.status}`}>{user.status === "active" ? "正常" : "已停用"}</span></td><td>{user.last_login_at ? formatDateTimeLong(user.last_login_at) : "尚未登录"}</td><td><span className="table-actions"><Link className="button button-quiet" href={`/?owner_id=${user.id}`} title="查看用户书架"><Eye size={14} />查看书架</Link><button className="button button-quiet" onClick={() => void resetPassword(user)} title="重置临时密码" type="button"><KeyRound size={14} />重置密码</button><button className="button button-quiet" disabled={user.role === "admin" && user.status === "active"} onClick={() => void toggleStatus(user)} title={user.status === "active" ? "停用账户" : "恢复账户"} type="button">{user.status === "active" ? <UserX size={14} /> : <Check size={14} />}{user.status === "active" ? "停用" : "恢复"}</button></span></td></tr>)}</tbody></table></div>}
      </section>
    </div>
  );
}
