import type { GenerationTheme, ResourceMaterial, ResourceType } from "@/lib/types";

const BEIJING_TIME_ZONE = "Asia/Shanghai";

function parseServerDate(value: string) {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return new Date(`${value}T00:00:00+08:00`);
  }
  if (/(?:Z|[+-]\d{2}:?\d{2})$/.test(value)) {
    return new Date(value);
  }
  return new Date(`${value}Z`);
}

export function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDate(value: string | null | undefined) {
  return formatDateTime(value);
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return "暂无";
  const parts = new Intl.DateTimeFormat("en-CA", {
    day: "2-digit",
    hour: "2-digit",
    hourCycle: "h23",
    minute: "2-digit",
    month: "2-digit",
    second: "2-digit",
    timeZone: BEIJING_TIME_ZONE,
    year: "numeric",
  }).formatToParts(parseServerDate(value));
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second}`;
}

export function formatDateTimeLong(value: string | null | undefined) {
  return formatDateTime(value);
}

export function formatDuration(seconds: number | null | undefined) {
  if (!seconds) return "未记录";
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${minutes}分${String(remaining).padStart(2, "0")}秒`;
}

export function elapsedSecondsSince(value: string) {
  const startedAt = parseServerDate(value).getTime();
  if (Number.isNaN(startedAt)) return 0;
  return Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
}

export function formatScore(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return value.toFixed(2).replace(/\.00$/, "").replace(/(\.\d)0$/, "$1");
}

export function scorePercentage(score: number | null | undefined, maxScore: number) {
  if (score === null || score === undefined || maxScore <= 0) return null;
  return Math.round(score / maxScore * 100);
}

export function statusLabel(status: string) {
  const labels: Record<string, string> = {
    reading: "在读",
    finished: "已读",
    reviewing: "复习中",
    pending: "等待解析",
    processing: "解析中",
    needs_review: "待校对",
    completed: "解析完成",
    failed: "解析失败",
    ready: "待完成",
    in_progress: "进行中",
    submitted: "已完成",
    not_copied: "未复制原文",
    active: "已上架",
    unlisted: "已下架",
    stopped: "已停止",
    source_deleted: "原试卷已删除",
    expired: "已过期",
    grading: "评分中",
    grading_failed: "评分失败",
    anonymous: "匿名参与者",
    user: "登录用户",
    confirmed: "已确认",
    rejected: "已排除",
  };
  return labels[status] || status;
}

export function materialTypeLabel(value: ResourceMaterial["material_type"]) {
  return {
    book_text: "原文资料",
    script: "剧本或整理稿",
    subtitle: "字幕",
    quote_sheet: "结构化台词表",
    plot_summary: "剧情梗概",
  }[value];
}

export function generationThemeLabel(value: GenerationTheme) {
  return {
    general: "综合内容",
    classic_quotes: "经典台词",
    character: "角色专题",
  }[value];
}

export function formatMediaTime(milliseconds: number | null | undefined) {
  if (milliseconds === null || milliseconds === undefined) return null;
  const totalSeconds = Math.floor(milliseconds / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor(totalSeconds % 3600 / 60);
  const seconds = totalSeconds % 60;
  return `${hours ? `${String(hours).padStart(2, "0")}:` : ""}${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function resourceTypeLabel(value: ResourceType | string | null | undefined) {
  const labels: Record<ResourceType, string> = {
    book: "书籍",
    movie: "电影",
    tv_series: "电视剧",
  };
  return labels[(value as ResourceType) || "book"] || "书籍";
}

export function resourceTypeShortLabel(value: ResourceType | string | null | undefined) {
  const labels: Record<ResourceType, string> = {
    book: "BOOK",
    movie: "MOVIE",
    tv_series: "TV",
  };
  return labels[(value as ResourceType) || "book"] || "BOOK";
}

export function resourceAuthorLabel(value: ResourceType | string | null | undefined) {
  const labels: Record<ResourceType, string> = {
    book: "作者",
    movie: "导演",
    tv_series: "主创",
  };
  return labels[(value as ResourceType) || "book"] || "作者";
}
