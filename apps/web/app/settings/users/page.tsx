"use client";

import { AlertTriangle, Check, Copy, Eye, KeyRound, Plus, RefreshCw, Shield, UserRound, UserX, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, createAdminUser, getAdminUsers, resetAdminUserPassword, updateAdminUser } from "@/lib/api";
import { formatDateTimeLong } from "@/lib/format";
import type { AdminUser } from "@/lib/types";

type Credential = { username: string; password: string; reason: "created" | "reset" };

export default function UserManagementPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<"admin" | "user">("user");
  const [temporaryPassword, setTemporaryPassword] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);
  const [newCredential, setNewCredential] = useState<Credential | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [resetting, setResetting] = useState(false);
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

  function resetCreateForm() {
    setUsername("");
    setDisplayName("");
    setTemporaryPassword("");
    setRole("user");
  }

  function closeCreate() {
    if (!submitting) { setCreateOpen(false); resetCreateForm(); }
  }

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
      setCreateOpen(false);
      resetCreateForm();
      setNewCredential({ username: result.user.username, password: result.temporary_password, reason: "created" });
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

  async function confirmResetPassword() {
    if (!resetTarget) return;
    setResetting(true);
    setError("");
    try {
      const result = await resetAdminUserPassword(resetTarget.id);
      setNewCredential({ username: resetTarget.username, password: result.temporary_password, reason: "reset" });
      setResetTarget(null);
      await load();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "临时密码重置失败");
    } finally {
      setResetting(false);
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
        <div><div className="eyebrow">System management</div><h1 className="page-title">用户管理</h1><p className="page-description">创建和维护平台账户。密码只保存不可逆哈希，原密码无法查看；创建或重置后的临时密码仅展示一次。</p></div>
        <div className="header-actions"><button aria-label="刷新用户列表" className="button button-secondary" disabled={loading} onClick={() => void load()} title="刷新用户列表" type="button"><RefreshCw className={loading ? "spin" : ""} size={15} />刷新</button><button className="button button-primary" onClick={() => { setCreateOpen(true); setError(""); }} type="button"><Plus size={15} />创建账户</button></div>
      </header>

      {error && <div className="toast-error">{error}</div>}
      {notice && <div className="toast-success">{notice}</div>}

      <section className="content-panel user-list-panel">
        <div className="section-title"><h2>平台用户</h2><span>{users.length} 个账户</span></div>
        {loading ? <div className="loading-state">正在读取用户列表……</div> : <div className="user-table-wrap"><table className="user-table"><thead><tr><th>用户</th><th>角色</th><th>工作空间</th><th>状态</th><th>最后登录</th><th>操作</th></tr></thead><tbody>{users.map((user) => <tr key={user.id}><td><strong>{user.display_name}</strong><small>{user.username}</small></td><td><span className="role-badge">{user.role === "admin" ? <Shield size={12} /> : <UserRound size={12} />}{user.role === "admin" ? "管理员" : "普通用户"}</span></td><td>{user.workspace.name}</td><td><span className={`status-badge status-${user.status}`}>{user.status === "active" ? "正常" : "已停用"}</span></td><td>{user.last_login_at ? formatDateTimeLong(user.last_login_at) : "尚未登录"}</td><td><span className="table-actions"><Link className="button button-quiet" href={`/admin/users/${user.id}/space`} title="进入只读临时空间"><Eye size={14} />查看空间</Link><button className="button button-quiet" onClick={() => { setResetTarget(user); setError(""); }} title="重置并查看一次性临时密码" type="button"><KeyRound size={14} />重置并查看密码</button><button className="button button-quiet" disabled={user.role === "admin" && user.status === "active"} onClick={() => void toggleStatus(user)} title={user.status === "active" ? "停用账户" : "恢复账户"} type="button">{user.status === "active" ? <UserX size={14} /> : <Check size={14} />}{user.status === "active" ? "停用" : "恢复"}</button></span></td></tr>)}</tbody></table></div>}
      </section>

      {createOpen && <div className="modal-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) closeCreate(); }} role="presentation"><section aria-labelledby="create-user-title" aria-modal="true" className="modal-panel" role="dialog"><div className="modal-heading"><div><span className="eyebrow">Create account</span><h2 id="create-user-title">创建账户</h2></div><button aria-label="关闭创建账户弹窗" className="modal-close" disabled={submitting} onClick={closeCreate} title="关闭" type="button"><X size={18} /></button></div><form className="form-grid" onSubmit={handleCreate}><div className="field"><label htmlFor="new-username">账户名</label><input autoFocus id="new-username" onChange={(event) => setUsername(event.target.value)} placeholder="如：reader-01" required value={username} /></div><div className="field"><label htmlFor="new-display-name">显示名称</label><input id="new-display-name" onChange={(event) => setDisplayName(event.target.value)} placeholder="如：林晓" required value={displayName} /></div><div className="field"><label htmlFor="new-role">角色</label><select id="new-role" onChange={(event) => setRole(event.target.value as "admin" | "user")} value={role}><option value="user">普通用户</option><option value="admin">管理员</option></select></div><div className="field"><label htmlFor="temporary-password">指定临时密码 <span className="optional">可选</span></label><input id="temporary-password" onChange={(event) => setTemporaryPassword(event.target.value)} placeholder="留空则自动生成" type="password" value={temporaryPassword} /></div><div className="field-full modal-actions"><button className="button button-secondary" disabled={submitting} onClick={closeCreate} type="button">取消</button><button className="button button-primary" disabled={submitting} type="submit"><Plus size={15} />{submitting ? "正在创建……" : "创建账户"}</button></div></form></section></div>}

      {resetTarget && <div className="modal-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target && !resetting) setResetTarget(null); }} role="presentation"><section aria-labelledby="reset-password-title" aria-modal="true" className="modal-panel confirm-modal" role="dialog"><div className="confirm-icon"><AlertTriangle size={22} /></div><h2 id="reset-password-title">确认重置密码</h2><p>将为 {resetTarget.display_name}（{resetTarget.username}）生成新的临时密码，并立即撤销该用户现有登录会话。原密码无法恢复。</p><div className="modal-actions"><button className="button button-secondary" disabled={resetting} onClick={() => setResetTarget(null)} type="button">取消</button><button className="button button-danger" disabled={resetting} onClick={() => void confirmResetPassword()} type="button"><KeyRound size={15} />{resetting ? "正在重置……" : "确认重置"}</button></div></section></div>}

      {newCredential && <div className="modal-backdrop" role="presentation"><section aria-labelledby="credential-title" aria-modal="true" className="modal-panel credential-modal" role="dialog"><div className="modal-heading"><div><span className="eyebrow">Temporary credential</span><h2 id="credential-title">{newCredential.reason === "created" ? "账户已创建" : "密码已重置"}</h2></div><button aria-label="关闭临时凭据弹窗" className="modal-close" onClick={() => { setNewCredential(null); setCopied(false); }} title="关闭" type="button"><X size={18} /></button></div><div className="credential-panel"><div className="credential-heading"><KeyRound size={18} /><div><strong>临时登录凭据</strong><span>请线下交付给用户。关闭此弹窗后，系统无法再次读取这段密码。</span></div></div><div className="credential-value"><small>账户名</small><code>{newCredential.username}</code></div><div className="credential-value"><small>临时密码</small><code>{newCredential.password}</code></div></div><div className="modal-actions"><button className="button button-secondary" onClick={() => void copyCredential()} type="button">{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? "已复制" : "复制凭据"}</button><button className="button button-primary" onClick={() => { setNewCredential(null); setCopied(false); }} type="button">完成</button></div></section></div>}
    </div>
  );
}
