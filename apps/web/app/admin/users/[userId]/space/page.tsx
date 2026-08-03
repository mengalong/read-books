"use client";

import { ArrowLeft, BookOpenText, Eye, LockKeyhole, UserRound } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { BookCard, EmptyState, ErrorState } from "@/components/ui";
import { ApiError, getAdminBooks, getAdminUsers } from "@/lib/api";
import type { AdminUser, BookSummary } from "@/lib/types";

export default function AdminUserSpacePage() {
  const params = useParams<{ userId: string }>();
  const [user, setUser] = useState<AdminUser | null>(null);
  const [books, setBooks] = useState<BookSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([getAdminUsers(), getAdminBooks("", params.userId)])
      .then(([users, items]) => {
        if (cancelled) return;
        const matchedUser = users.find((item) => item.id === params.userId);
        if (!matchedUser) throw new ApiError("未找到该用户", 404);
        setUser(matchedUser);
        setBooks(items);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof ApiError ? reason.message : "用户空间加载失败");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [params.userId]);

  const metrics = useMemo(() => ({
    pdfBooks: books.filter((book) => book.stats.pdf_count > 0).length,
    reviews: books.reduce((total, book) => total + book.stats.quiz_count, 0),
  }), [books]);

  if (loading) return <div className="page-wrap"><div className="loading-state">正在进入用户空间……</div></div>;
  if (!user || error) return <div className="page-wrap"><ErrorState message={error || "未找到该用户"} /></div>;

  return (
    <div className="page-wrap">
      <Link className="back-link" href="/settings/users"><ArrowLeft size={14} />返回用户管理</Link>
      <header className="page-header compact-header">
        <div>
          <div className="eyebrow">Temporary workspace</div>
          <h1 className="page-title">{user.display_name} 的空间</h1>
          <p className="page-description">当前正在只读查看 {user.username} 的个人工作空间，与管理员自己的书架完全分开。</p>
        </div>
        <span className="readonly-badge"><LockKeyhole size={14} />管理员只读视图</span>
      </header>

      <div className="workspace-context-banner">
        <UserRound size={18} />
        <div><strong>{user.workspace.name}</strong><span>账户状态：{user.status === "active" ? "正常" : "已停用"} · 角色：{user.role === "admin" ? "管理员" : "普通用户"}</span></div>
      </div>

      <section className="metrics-grid" aria-label="用户空间概览">
        <div className="metric"><div className="metric-label">书籍总数</div><div className="metric-value">{books.length}<span className="metric-detail">本</span></div></div>
        <div className="metric"><div className="metric-label">包含 PDF</div><div className="metric-value">{metrics.pdfBooks}<span className="metric-detail">本</span></div></div>
        <div className="metric"><div className="metric-label">复习记录</div><div className="metric-value">{metrics.reviews}<span className="metric-detail">次</span></div></div>
      </section>

      <div className="books-toolbar">
        <div className="section-title" style={{ marginBottom: 0 }}><h2>空间书架</h2><span>{books.length} 本</span></div>
        <Link className="button button-secondary" href={`/settings/books?owner_id=${user.id}`}><Eye size={15} />前往书籍管理</Link>
      </div>
      {books.length === 0
        ? <EmptyState title="该空间还没有书籍" detail="用户添加或接收共享书籍后，会在这里显示。" />
        : <div className="book-grid">{books.map((book) => <BookCard book={book} href={`/admin/books/${book.id}`} key={book.id} />)}</div>}
      <div className="readonly-footnote"><BookOpenText size={14} />这里只提供内容核查；复制书籍请前往系统管理中的书籍管理。</div>
    </div>
  );
}
