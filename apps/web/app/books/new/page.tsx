"use client";

import { ArrowLeft, BookPlus, Palette } from "lucide-react";
import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, createBook } from "@/lib/api";
import { resourceAuthorLabel, resourceTypeLabel } from "@/lib/format";
import type { ReadingStatus, ResourceType } from "@/lib/types";

const colors = ["#2F6B5F", "#8B3A3A", "#355C7D", "#9A6B18", "#735A8B", "#4B6A58"];
const resourceTypes: { value: ResourceType; label: string; detail: string }[] = [
  { value: "book", label: "书籍", detail: "上传 PDF 后优先按原文出题" },
  { value: "movie", label: "电影", detail: "保存后自动检查模型是否掌握真实内容" },
  { value: "tv_series", label: "电视剧", detail: "保存后自动检查模型是否掌握真实内容" },
];

export default function NewBookPage() {
  const router = useRouter();
  const [resourceType, setResourceType] = useState<ResourceType>("book");
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<ReadingStatus>("finished");
  const [color, setColor] = useState(colors[0]);
  const [tags, setTags] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const authorLabel = resourceAuthorLabel(resourceType);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const book = await createBook({
        resource_type: resourceType,
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
      setError(reason instanceof ApiError ? reason.message : "资源创建失败");
      setSaving(false);
    }
  }

  return (
    <div className="page-wrap">
      <Link className="back-link" href="/"><ArrowLeft size={14} />返回内容库</Link>
      <header className="page-header" style={{ marginBottom: 25 }}>
        <div>
          <div className="eyebrow">New title</div>
          <h1 className="page-title">添加内容资源</h1>
          <p className="page-description">先记录资源信息，再上传 PDF 或让系统自动检查模型是否掌握真实内容。</p>
        </div>
      </header>
      <form className="form-panel" onSubmit={handleSubmit}>
        {error && <div className="toast-error">{error}</div>}
        <div className="form-grid">
          <div className="field field-full"><label htmlFor="resource-type">资源类型</label><select id="resource-type" value={resourceType} onChange={(event) => setResourceType(event.target.value as ResourceType)}>{resourceTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select><span className="field-hint">{resourceTypes.find((item) => item.value === resourceType)?.detail}；{resourceType === "book" ? "后续可以上传 PDF。" : "没有真实内容验证前，不能依赖模型知识出题。"}</span></div>
          <div className="field field-full"><label htmlFor="title">资源名称</label><input id="title" required value={title} onChange={(event) => setTitle(event.target.value)} placeholder={`例如：${resourceType === "movie" ? "霸王别姬" : resourceType === "tv_series" ? "觉醒年代" : "红楼梦"}`} /></div>
          <div className="field"><label htmlFor="author">{authorLabel}</label><input id="author" value={author} onChange={(event) => setAuthor(event.target.value)} placeholder={`例如：${resourceType === "movie" ? "张艺谋" : resourceType === "tv_series" ? "张永新" : "曹雪芹"}`} /></div>
          <div className="field"><label htmlFor="status">阅读状态</label><select id="status" value={status} onChange={(event) => setStatus(event.target.value as ReadingStatus)}><option value="finished">已读</option><option value="reviewing">复习中</option><option value="reading">在读</option></select></div>
          <div className="field field-full"><label htmlFor="description">一句话备注</label><textarea id="description" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="这个资源对你有什么重要的地方？" /></div>
          <div className="field field-full"><label htmlFor="tags">标签</label><input id="tags" value={tags} onChange={(event) => setTags(event.target.value)} placeholder="用逗号分隔，例如：文学，人物，长期复习" /><span className="field-hint">标签用于在内容库中快速辨认，不影响出题。</span></div>
          <div className="field field-full"><label><Palette size={14} style={{ verticalAlign: "-3px", marginRight: 4 }} />封面色</label><div style={{ display: "flex", gap: 9 }}>{colors.map((item) => <button aria-label={`选择${item}封面色`} className="color-swatch" key={item} onClick={() => setColor(item)} style={{ background: item, borderColor: color === item ? "var(--ink)" : "transparent" }} type="button" />)}</div></div>
        </div>
        <div className="form-actions"><Link className="button button-secondary" href="/">取消</Link><button className="button button-primary" disabled={saving} type="submit"><BookPlus size={16} />{saving ? "创建中……" : `创建${resourceTypeLabel(resourceType)}`}</button></div>
      </form>
    </div>
  );
}
