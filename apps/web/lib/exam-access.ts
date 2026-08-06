type ExamAccess = { attemptId: string; token: string | null };

function storageKey(shareCode: string) {
  return `huijuan:exam:${shareCode}`;
}

export function saveExamAccess(shareCode: string, access: ExamAccess) {
  window.sessionStorage.setItem(storageKey(shareCode), JSON.stringify(access));
}

export function readExamAccess(shareCode: string): ExamAccess | null {
  try {
    const raw = window.sessionStorage.getItem(storageKey(shareCode));
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<ExamAccess>;
    return typeof value.attemptId === "string"
      ? { attemptId: value.attemptId, token: typeof value.token === "string" ? value.token : null }
      : null;
  } catch {
    return null;
  }
}
