"use client";

import { Activity, BarChart3, BookMarked, BookOpenText, ClipboardCheck, Clock3, FileCode2, History, LibraryBig, LogOut, Plus, Settings2, Users } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ApiError, getCurrentUser, logout, recordActivity } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { CurrentUser } from "@/lib/types";

const navigation = [
  { href: "/", label: "我的书架", icon: LibraryBig },
  { href: "/books/new", label: "添加书籍", icon: Plus },
  { href: "/reviews", label: "复习记录", icon: History },
  { href: "/exam-management", label: "考试管理", icon: ClipboardCheck },
];

const systemNavigation = [
  { href: "/settings/books", label: "书籍管理", icon: BookMarked },
  { href: "/settings/model", label: "模型设置", icon: Settings2 },
  { href: "/settings/prompts", label: "提示词管理", icon: FileCode2 },
  { href: "/settings/token-usage", label: "Token 用量", icon: BarChart3 },
  { href: "/settings/access-statistics", label: "访问统计", icon: Activity },
  { href: "/settings/users", label: "用户管理", icon: Users },
  { href: "/settings/exams", label: "考试管理", icon: ClipboardCheck },
];

const buildUpdatedAt = process.env.NEXT_PUBLIC_BUILD_UPDATED_AT || "";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const authPage = pathname === "/login" || pathname === "/change-password";
  const publicExamPage = pathname.startsWith("/exams/");

  const loadUser = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const current = await getCurrentUser();
      setUser(current);
      if (current.role !== "admin" && pathname.startsWith("/settings")) {
        router.replace("/");
      } else if (current.must_change_password && pathname !== "/change-password") {
        router.replace("/change-password");
      } else if (!current.must_change_password && authPage) {
        router.replace("/");
      }
    } catch (reason: unknown) {
      setUser(null);
      if (reason instanceof ApiError && reason.status === 401) {
        if (!publicExamPage && pathname !== "/login") router.replace("/login");
      } else {
        setError(reason instanceof ApiError ? reason.message : "账户状态加载失败");
      }
    } finally {
      setLoading(false);
    }
  }, [authPage, pathname, publicExamPage, router]);

  useEffect(() => { void loadUser(); }, [loadUser]);

  useEffect(() => {
    if (!user || authPage || publicExamPage) return;
    let sending = false;
    const sendHeartbeat = async () => {
      if (document.visibilityState !== "visible" || sending) return;
      sending = true;
      try {
        await recordActivity();
      } catch (reason: unknown) {
        if (reason instanceof ApiError && reason.status === 401) {
          setUser(null);
          router.replace("/login");
        }
      } finally {
        sending = false;
      }
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") void sendHeartbeat();
    };
    const timer = window.setInterval(() => { void sendHeartbeat(); }, 60_000);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [authPage, publicExamPage, router, user]);

  async function handleLogout() {
    try {
      await logout();
    } finally {
      setUser(null);
      router.replace("/login");
    }
  }

  if (loading) return <div className="auth-loading">正在确认账户状态……</div>;
  if (authPage) return <div className="auth-layout">{children}</div>;
  if (publicExamPage) return <div className="public-exam-layout">{children}</div>;
  if (!user) {
    return error ? (
      <div className="auth-loading auth-error"><span>{error}</span><button className="button button-secondary" onClick={() => void loadUser()} type="button">重新连接</button></div>
    ) : <div className="auth-loading">正在前往登录页面……</div>;
  }
  return (
    <div className="app-layout">
      <aside className="app-sidebar">
        <Link className="brand" href="/">
          <span className="brand-mark">卷</span>
          <span>
            <span className="brand-name">回卷</span>
            <span className="brand-subtitle">把读过的书再想起来</span>
          </span>
        </Link>
        <nav className="side-nav" aria-label="主导航">
          {navigation.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link className={active ? "active" : ""} href={href} key={href}>
                <Icon size={17} strokeWidth={1.8} />
                {label}
              </Link>
            );
          })}
          {user.role === "admin" && <>
            <div className="nav-group-label">系统管理</div>
            {systemNavigation.map(({ href, label, icon: Icon }) => {
              const active = pathname.startsWith(href);
              return (
                <Link className={active ? "active" : ""} href={href} key={href}>
                  <Icon size={17} strokeWidth={1.8} />
                  {label}
                </Link>
              );
            })}
          </>}
        </nav>
        <div className="sidebar-note">
          <strong><BookOpenText size={13} /> 原文优先</strong>
          上传 PDF 时保留页码与原文依据；没有电子版时可使用模型知识兜底。
        </div>
        <div className="sidebar-account">
          <span className="account-avatar">{user.display_name.slice(0, 1)}</span>
          <span className="account-copy"><strong>{user.display_name}</strong><small>{user.role === "admin" ? "管理员" : user.username}</small></span>
          <button aria-label="退出登录" onClick={() => void handleLogout()} title="退出登录" type="button"><LogOut size={16} /></button>
        </div>
        <div className="sidebar-version" title={`当前版本构建于 ${formatDateTime(buildUpdatedAt)}`}>
          <Clock3 size={13} />
          <span><small>版本更新时间</small><time dateTime={buildUpdatedAt}>{formatDateTime(buildUpdatedAt)}</time></span>
        </div>
      </aside>
      <main className="app-main">{children}</main>
    </div>
  );
}
