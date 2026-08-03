"use client";

import { BookCopy, Eye, FileText, FileX2, Search, UserRound, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import { EmptyState, StatusBadge } from "@/components/ui";
import { ApiError, copyAdminBook, getAdminBooks, getAdminUsers } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { AdminUser, BookSummary } from "@/lib/types";

export default function AdminBookManagementPage() {
  const [books, setBooks] = useState<BookSummary[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [searchInput, setSearchInput] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [ownerId, setOwnerId] = useState(() => (
    typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get("owner_id") || ""
  ));
  const [copySource, setCopySource] = useState<BookSummary | null>(null);
  const [targetUserId, setTargetUserId] = useState("");
  const [copyPdf, setCopyPdf] = useState(true);
  const [copyContent, setCopyContent] = useState(true);
  const [loading, setLoading] = useState(true);
  const [copying, setCopying] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [bookItems, userItems] = await Promise.all([
        getAdminBooks(appliedSearch, ownerId || undefined),
        getAdminUsers(),
      ]);
      setBooks(bookItems);
      setUsers(userItems);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "书籍管理数据加载失败");
    } finally {
      setLoading(false);
    }
  }, [appliedSearch, ownerId]);

  useEffect(() => { void load(); }, [load]);

  const activeTargets = useMemo(
    () => users.filter((user) => user.status === "active" && user.id !== copySource?.owner_user_id),
    [copySource?.owner_user_id, users],
  );

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedSearch(searchInput.trim());
  }

  function openCopy(book: BookSummary) {
    const hasPdf = book.stats.pdf_count > 0;
    const targets = users.filter((user) => user.status === "active" && user.id !== book.owner_user_id);
    setCopySource(book);
    setTargetUserId(targets[0]?.id || "");
    setCopyPdf(hasPdf);
    setCopyContent(hasPdf && book.stats.chunk_count > 0);
    setError("");
    setNotice("");
  }

  function closeCopy() {
    if (!copying) setCopySource(null);
  }

  async function handleCopy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!copySource || !targetUserId) return;
    const target = users.find((user) => user.id === targetUserId);
    setCopying(true);
    setError("");
    try {
      const result = await copyAdminBook(copySource.id, {
        target_user_id: targetUserId,
        copy_pdf: copyPdf,
        copy_content: copyPdf && copyContent,
      });
      setNotice(`已将《${copySource.title}》复制到 ${target?.display_name || "目标用户"} 的书架，共复制 ${result.copied_pdf_count} 份 PDF、${result.copied_chunk_count} 个原文片段。`);
      setCopySource(null);
      await load();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "书籍复制失败");
    } finally {
      setCopying(false);
    }
  }

  return (
    <div className="page-wrap">
      <header className="page-header compact-header">
        <div><div className="eyebrow">System management</div><h1 className="page-title">书籍管理</h1><p className="page-description">跨用户查看平台书籍，并将已有书籍资料复制到指定用户的个人书架。</p></div>
      </header>

      {error && <div className="toast-error">{error}</div>}
      {notice && <div className="toast-success">{notice}</div>}

      <div className="admin-book-toolbar">
        <form className="search-box" onSubmit={handleSearch}>
          <Search size={15} />
          <input aria-label="搜索书名或作者" onChange={(event) => setSearchInput(event.target.value)} placeholder="搜索书名或作者，按回车搜索" value={searchInput} />
        </form>
        <label className="admin-owner-filter">所属用户<select aria-label="按所属用户筛选书籍" onChange={(event) => setOwnerId(event.target.value)} value={ownerId}><option value="">全部用户</option>{users.map((user) => <option key={user.id} value={user.id}>{user.display_name}（{user.username}）</option>)}</select></label>
      </div>

      <section className="content-panel admin-book-panel">
        <div className="section-title"><h2>平台书籍</h2><span>{books.length} 本</span></div>
        {loading ? <div className="loading-state">正在读取平台书籍……</div> : books.length === 0 ? <EmptyState title="没有匹配的书籍" detail="调整搜索词或所属用户后再试。" /> : <div className="admin-book-table-wrap"><table className="admin-book-table"><thead><tr><th>书籍</th><th>所属用户</th><th>阅读状态</th><th>资料</th><th>最近更新</th><th>操作</th></tr></thead><tbody>{books.map((book) => <tr key={book.id}><td><strong>{book.title}</strong><small>{book.author || "作者未填写"}</small></td><td><span className="owner-cell"><UserRound size={13} />{book.owner_display_name || "历史未归属"}</span></td><td><StatusBadge status={book.reading_status} /></td><td><span className={book.stats.pdf_count > 0 ? "source-cell has-source" : "source-cell"}>{book.stats.pdf_count > 0 ? <FileText size={13} /> : <FileX2 size={13} />}{book.stats.pdf_count > 0 ? `${book.stats.pdf_count} 份 PDF · ${book.stats.chunk_count} 段原文` : "无 PDF"}</span></td><td>{formatDateTime(book.updated_at)}</td><td><span className="table-actions"><Link aria-label={`查看${book.title}`} className="button button-quiet" href={`/admin/books/${book.id}`} title="查看书籍"><Eye size={15} /></Link><button aria-label={`复制${book.title}`} className="button button-quiet" onClick={() => openCopy(book)} title="复制到其他用户" type="button"><BookCopy size={15} /></button></span></td></tr>)}</tbody></table></div>}
      </section>

      {copySource && <div className="modal-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) closeCopy(); }} role="presentation"><section aria-labelledby="copy-book-title" aria-modal="true" className="modal-panel" role="dialog"><div className="modal-heading"><div><span className="eyebrow">Copy book</span><h2 id="copy-book-title">复制《{copySource.title}》</h2></div><button aria-label="关闭复制弹窗" className="modal-close" disabled={copying} onClick={closeCopy} title="关闭" type="button"><X size={18} /></button></div><form onSubmit={handleCopy}><div className="field"><label htmlFor="copy-target">目标用户</label><select id="copy-target" onChange={(event) => setTargetUserId(event.target.value)} required value={targetUserId}>{activeTargets.length === 0 && <option value="">没有可用的目标用户</option>}{activeTargets.map((user) => <option key={user.id} value={user.id}>{user.display_name}（{user.username}）</option>)}</select></div><div className="copy-options"><label><input checked={copyPdf} disabled={copySource.stats.pdf_count === 0} onChange={(event) => { setCopyPdf(event.target.checked); if (!event.target.checked) setCopyContent(false); }} type="checkbox" /><span><strong>复制 PDF 文件</strong><small>{copySource.stats.pdf_count ? `共 ${copySource.stats.pdf_count} 份` : "源书籍没有 PDF"}</small></span></label><label><input checked={copyContent} disabled={!copyPdf || copySource.stats.chunk_count === 0} onChange={(event) => setCopyContent(event.target.checked)} type="checkbox" /><span><strong>复制已解析原文片段</strong><small>{copySource.stats.chunk_count ? `共 ${copySource.stats.chunk_count} 段，需同时复制 PDF` : "源书籍没有可复制片段"}</small></span></label></div><div className="copy-scope-note">只复制书籍资料；历史试卷、复习任务、答案和成绩不会复制。</div><div className="modal-actions"><button className="button button-secondary" disabled={copying} onClick={closeCopy} type="button">取消</button><button className="button button-primary" disabled={copying || !targetUserId} type="submit"><BookCopy size={15} />{copying ? "正在复制……" : "确认复制"}</button></div></form></section></div>}
    </div>
  );
}
