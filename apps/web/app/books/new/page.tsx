"use client";

import { ArrowLeft, BookPlus, Palette } from "lucide-react";
import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, createBook } from "@/lib/api";
import type { ReadingStatus } from "@/lib/types";

const colors = ["#2F6B5F", "#8B3A3A", "#355C7D", "#9A6B18", "#735A8B", "#4B6A58"];

export default function NewBookPage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<ReadingStatus>("finished");
  const [color, setColor] = useState(colors[0]);
  const [tags, setTags] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const book = await createBook({
        title,
        author,
        description,
        cover_color: color,
        language: "中文",
        reading_status: status,
        tags: tags.split(/[，,]/).map((tag) => tag.trim()).filter(Boolean),
      });
      router.push(`/books/${book.id}`);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "书籍创建失败");
      setSaving(false);
    }
  }

  return (
    <div className="page-wrap">
      <Link className="back-link" href="/"><ArrowLeft size={14} />返回书架</Link>
      <header className="page-header" style={{ marginBottom: 25 }}>
        <div>
          <div className="eyebrow">New title</div>
          <h1 className="page-title">添加一本书</h1>
          <p className="page-description">先记录书籍信息，再上传读过的 PDF。书籍建立后也可以随时补充资料。</p>
        </div>
      </header>
      <form className="form-panel" onSubmit={handleSubmit}>
        {error && <div className="toast-error">{error}</div>}
        <div className="form-grid">
          <div className="field field-full"><label htmlFor="title">书名</label><input id="title" required value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：红楼梦" /></div>
          <div className="field"><label htmlFor="author">作者</label><input id="author" value={author} onChange={(event) => setAuthor(event.target.value)} placeholder="例如：曹雪芹" /></div>
          <div className="field"><label htmlFor="status">阅读状态</label><select id="status" value={status} onChange={(event) => setStatus(event.target.value as ReadingStatus)}><option value="finished">已读</option><option value="reviewing">复习中</option><option value="reading">在读</option></select></div>
          <div className="field field-full"><label htmlFor="description">一句话备注</label><textarea id="description" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="这本书对你有什么重要的地方？" /></div>
          <div className="field field-full"><label htmlFor="tags">标签</label><input id="tags" value={tags} onChange={(event) => setTags(event.target.value)} placeholder="用逗号分隔，例如：文学，人物，长期复习" /><span className="field-hint">标签用于在书架上快速辨认，不影响出题。</span></div>
          <div className="field field-full"><label><Palette size={14} style={{ verticalAlign: "-3px", marginRight: 4 }} />封面色</label><div style={{ display: "flex", gap: 9 }}>{colors.map((item) => <button aria-label={`选择${item}封面色`} className="color-swatch" key={item} onClick={() => setColor(item)} style={{ background: item, borderColor: color === item ? "var(--ink)" : "transparent" }} type="button" />)}</div></div>
        </div>
        <div className="form-actions"><Link className="button button-secondary" href="/">取消</Link><button className="button button-primary" disabled={saving} type="submit"><BookPlus size={16} />{saving ? "创建中……" : "创建书籍"}</button></div>
      </form>
    </div>
  );
}
