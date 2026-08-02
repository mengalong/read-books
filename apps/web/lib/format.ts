export function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDate(value: string | null | undefined) {
  if (!value) return "暂无";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date(value));
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return "暂无";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatDuration(seconds: number | null | undefined) {
  if (!seconds) return "未记录";
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${minutes}分${String(remaining).padStart(2, "0")}秒`;
}

export function statusLabel(status: string) {
  const labels: Record<string, string> = {
    reading: "在读",
    finished: "已读",
    reviewing: "复习中",
    pending: "等待解析",
    processing: "解析中",
    completed: "解析完成",
    failed: "解析失败",
    ready: "待完成",
    in_progress: "进行中",
    submitted: "已完成",
  };
  return labels[status] || status;
}
