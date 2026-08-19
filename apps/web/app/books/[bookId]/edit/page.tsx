"use client";

import { ArrowLeft, Palette, Save } from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { ApiError, getBook, updateBook } from "@/lib/api";
import { resourceAuthorLabel } from "@/lib/format";
import type { BookDetail, ReadingStatus, ResourceType } from "@/lib/types";

const colors = ["#2F6B5F", "#8B3A3A", "#355C7D", "#9A6B18", "#735A8B", "#4B6A58"];
const resourceTypes: { value: ResourceType; label: string }[] = [
  { value: "book", label: "书籍" },
  { value: "movie", label: "电影" },
  { value: "tv_series", label: "电视剧" },
];

type BookFormValues = {
  resource_type: ResourceType;
  title: string;
  author: string;
  description: string;
  reading_status: ReadingStatus;
  cover_color: string;
  tags: string;
};

function formValuesFromBook(book: BookDetail): BookFormValues {
  return {
    resource_type: book.resource_type || "book",
    title: book.title,
    author: book.author,
    description: book.description,
    reading_status: book.reading_status,
    cover_color: book.cover_color,
    tags: book.tags.join("，"),
  };
}

export default function EditBookPage() {
  const params = useParams<{ bookId: string }>();
  const router = useRouter();
  const bookId = params.bookId;
  const [book, setBook] = useState<BookDetail | null>(null);
  const [values, setValues] = useState<BookFormValues | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getBook(bookId)
      .then((nextBook) => {
        setBook(nextBook);
        setValues(formValuesFromBook(nextBook));
      })
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "资源信息加载失败"))
      .finally(() => setLoading(false));
  }, [bookId]);

  function updateValue<Key extends keyof BookFormValues>(key: Key, value: BookFormValues[Key]) {
    setValues((current) => current ? { ...current, [key]: value } : current);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!book || !values) return;
    const title = values.title.trim();
    if (!title) {
      setError("资源名称不能为空");
      return;
    }

    setSaving(true);
    setError("");
    try {
      await updateBook(book.id, {
        resource_type: values.resource_type,
        title,
        author: values.author.trim(),
        description: values.description.trim(),
        cover_color: values.cover_color,
        language: book.language,
        reading_status: values.reading_status,
        tags: values.tags.split(/[，,]/).map((tag) => tag.trim()).filter(Boolean),
      });
      router.push(`/books/${book.id}`);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "资源信息保存失败");
      setSaving(false);
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在打开资源信息……</div></div>;
  if (!book || !values) return <div className="page-wrap"><div className="error-state">{error || "未找到这个资源"}</div></div>;
  const authorLabel = resourceAuthorLabel(values.resource_type);

  return (
    <div className="page-wrap">
      <Link className="back-link" href={`/books/${book.id}`}><ArrowLeft size={14} />返回《{book.title}》</Link>
      <header className="page-header" style={{ marginBottom: 25 }}>
        <div>
          <div className="eyebrow">Edit title</div>
          <h1 className="page-title">修改资源信息</h1>
          <p className="page-description">调整资源资料不会影响已经生成的试卷和历史复习记录。</p>
        </div>
      </header>

      <form className="form-panel" onSubmit={handleSubmit}>
        {error && <div className="toast-error">{error}</div>}
        <div className="form-grid">
          <div className="field field-full"><label htmlFor="edit-resource-type">资源类型</label><select id="edit-resource-type" value={values.resource_type} onChange={(event) => updateValue("resource_type", event.target.value as ResourceType)}>{resourceTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select><span className="field-hint">修改资源类型或名称后，系统会重新检查模型是否掌握真实内容。</span></div>
          <div className="field field-full"><label htmlFor="edit-title">资源名称</label><input id="edit-title" required value={values.title} onChange={(event) => updateValue("title", event.target.value)} /></div>
          <div className="field"><label htmlFor="edit-author">{authorLabel}</label><input id="edit-author" value={values.author} onChange={(event) => updateValue("author", event.target.value)} /></div>
          <div className="field"><label htmlFor="edit-status">阅读状态</label><select id="edit-status" value={values.reading_status} onChange={(event) => updateValue("reading_status", event.target.value as ReadingStatus)}><option value="finished">已读</option><option value="reviewing">复习中</option><option value="reading">在读</option></select></div>
          <div className="field field-full"><label htmlFor="edit-description">一句话备注</label><textarea id="edit-description" value={values.description} onChange={(event) => updateValue("description", event.target.value)} /></div>
          <div className="field field-full"><label htmlFor="edit-tags">标签</label><input id="edit-tags" value={values.tags} onChange={(event) => updateValue("tags", event.target.value)} placeholder="用逗号分隔，例如：文学，人物，长期复习" /><span className="field-hint">标签用于在内容库中快速辨认，不影响出题。</span></div>
          <div className="field field-full"><label><Palette size={14} style={{ verticalAlign: "-3px", marginRight: 4 }} />封面色</label><div style={{ display: "flex", gap: 9 }}>{colors.map((color) => <button aria-label={`选择${color}封面色`} className="color-swatch" key={color} onClick={() => updateValue("cover_color", color)} style={{ background: color, borderColor: values.cover_color === color ? "var(--ink)" : "transparent" }} type="button" />)}</div></div>
        </div>
        <div className="form-actions"><Link className="button button-secondary" href={`/books/${book.id}`}>取消</Link><button className="button button-primary" disabled={saving} type="submit"><Save size={16} />{saving ? "保存中……" : "保存修改"}</button></div>
      </form>
    </div>
  );
}
