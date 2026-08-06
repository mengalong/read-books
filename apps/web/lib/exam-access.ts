type ExamAccess = { attemptId: string; token: string | null };

function storageKey(shareCode: string) {
  return `huijuan:exam:${shareCode}`;
}

export function saveExamAccess(shareCode: string, access: ExamAccess) {
  window.localStorage.setItem(storageKey(shareCode), JSON.stringify(access));
  window.sessionStorage.removeItem(storageKey(shareCode));
}

export function readExamAccess(shareCode: string): ExamAccess | null {
  try {
    const raw = window.localStorage.getItem(storageKey(shareCode)) || window.sessionStorage.getItem(storageKey(shareCode));
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<ExamAccess>;
    const access = typeof value.attemptId === "string"
      ? { attemptId: value.attemptId, token: typeof value.token === "string" ? value.token : null }
      : null;
    if (access && !window.localStorage.getItem(storageKey(shareCode))) saveExamAccess(shareCode, access);
    return access;
  } catch {
    return null;
  }
}
