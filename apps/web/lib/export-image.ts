const MAX_CANVAS_DIMENSION = 30_000;
const MAX_CANVAS_PIXELS = 64_000_000;

export async function downloadElementAsPng(element: HTMLElement, fileName: string) {
  await document.fonts?.ready;

  const width = Math.ceil(element.scrollWidth);
  const height = Math.ceil(element.scrollHeight);
  if (!width || !height) throw new Error("报告内容尚未完成渲染");

  const dimensionScale = MAX_CANVAS_DIMENSION / Math.max(width, height);
  const pixelScale = Math.sqrt(MAX_CANVAS_PIXELS / (width * height));
  const scale = Math.min(2, dimensionScale, pixelScale);
  const { default: html2canvas } = await import("html2canvas");
  const canvas = await html2canvas(element, {
    backgroundColor: "#f4f6f4",
    height,
    logging: false,
    scale,
    useCORS: true,
    width,
    windowHeight: height,
    windowWidth: width,
  });
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((value) => value ? resolve(value) : reject(new Error("报告图片生成失败")), "image/png");
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.download = `${sanitizeFileName(fileName)}.png`;
  link.href = url;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function sanitizeFileName(value: string) {
  const cleaned = value.trim().replace(/[\\/:*?"<>|\u0000-\u001f]/g, "-").replace(/\s+/g, " ");
  return cleaned.slice(0, 100) || "考试答题报告";
}
