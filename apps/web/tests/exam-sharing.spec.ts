import { expect, test } from "@playwright/test";

const currentUser = {
  id: "admin-1",
  username: "admin",
  display_name: "系统管理员",
  role: "admin",
  status: "active",
  must_change_password: false,
  last_login_at: "2026-08-06T08:00:00Z",
  workspace: { id: "workspace-1", name: "系统管理员的工作空间" },
};

const publicExam = {
  share_code: "public-code",
  name: "红楼梦读书考试",
  status: "active",
  book_title: "红楼梦",
  book_author: "曹雪芹",
  quiz_title: "第 2 套复习试卷",
  owner_display_name: "系统管理员",
  difficulty: "medium",
  duration_minutes: 15,
  source_mode: "pdf",
  max_score: 100,
  question_count: 10,
  single_count: 5,
  multiple_count: 3,
  short_count: 2,
  expires_at: null,
  authenticated: false,
  participant_name: null,
  existing_attempt_id: null,
  existing_attempt_status: null,
};

const examShare = {
  id: "share-1",
  share_code: "public-code",
  name: "红楼梦读书考试",
  status: "active",
  quiz_id: "quiz-1",
  book_id: "book-1",
  owner_user_id: "admin-1",
  owner_username: "admin",
  owner_display_name: "系统管理员",
  workspace_id: "workspace-1",
  book_title: "红楼梦",
  book_author: "曹雪芹",
  quiz_title: "第 2 套复习试卷",
  source_mode: "pdf",
  difficulty: "medium",
  duration_minutes: 15,
  max_score: 100,
  question_count: 10,
  single_count: 5,
  multiple_count: 3,
  short_count: 2,
  started_count: 4,
  submitted_count: 3,
  grading_count: 1,
  grading_failed_count: 0,
  completion_rate: 75,
  average_score: 78.5,
  highest_score: 92,
  created_at: "2026-08-06T08:00:00Z",
  updated_at: "2026-08-06T08:00:00Z",
  stopped_at: null,
  expires_at: null,
  last_attempt_at: "2026-08-06T09:00:00Z",
};

test("未登录用户可以打开公开考试且移动端没有横向溢出", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "请先登录" }) });
  });
  await page.route("**/api/public/exams/public-code", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(publicExam) });
  });

  await page.goto("/exams/public-code");
  await expect(page).toHaveURL(/\/exams\/public-code$/);
  await expect(page.getByRole("heading", { name: "红楼梦读书考试" })).toBeVisible();
  await expect(page.getByLabel("答题身份")).toBeVisible();
  await expect(page.getByText("10 题 · 单选 5 · 多选 3 · 问答 2")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("分享停止后仍允许继续已经开始的匿名答卷", async ({ page }) => {
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "请先登录" }) });
  });
  await page.addInitScript(() => {
    window.sessionStorage.setItem(
      "huijuan:exam:public-code",
      JSON.stringify({ attemptId: "attempt-in-progress", token: "attempt-token" }),
    );
  });
  await page.route("**/api/public/exams/public-code", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ ...publicExam, status: "stopped" }),
    });
  });

  await page.goto("/exams/public-code");
  await expect(page.getByText("分享已经停止，但已开始的答卷仍可继续完成。")).toBeVisible();
  await expect(page.getByRole("button", { name: "继续答题" })).toBeVisible();
});

test("考试管理展示分享链接和答题统计", async ({ page }) => {
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(currentUser) });
  });
  await page.route("**/api/exam-shares**", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify([examShare]) });
  });

  await page.goto("/exam-management");
  await expect(page.getByRole("heading", { name: "考试管理" })).toBeVisible();
  await expect(page.getByRole("cell", { name: /红楼梦读书考试/ })).toBeVisible();
  await expect(page.getByText("3 / 4")).toBeVisible();
  await expect(page.getByText("78.5%")).toBeVisible();
  await expect(page.getByRole("button", { name: "复制考试链接" })).toBeVisible();
  const activityRow = page.locator(".exam-management-table tbody tr").first();
  await expect(activityRow.locator("td").nth(2)).toContainText("3 / 4");
  await expect(activityRow.locator("td").nth(3)).toContainText("78.5%");
  expect(await activityRow.locator("td").nth(2).evaluate((element) => getComputedStyle(element).display)).toBe("table-cell");
  expect(await activityRow.locator("td").nth(3).evaluate((element) => getComputedStyle(element).display)).toBe("table-cell");
});

test("考试详情展示成绩柱状图、风控信息和个人学习方向", async ({ page }) => {
  const attemptSummary = {
    id: "attempt-completed",
    participant_type: "anonymous",
    participant_user_id: null,
    participant_name: "林同学",
    status: "completed",
    total_score: 42.5,
    max_score: 100,
    score_percentage: 42.5,
    elapsed_seconds: 386,
    started_at: "2026-08-06T08:00:00Z",
    submitted_at: "2026-08-06T08:06:26Z",
    completed_at: "2026-08-06T08:06:30Z",
    grading_error: null,
    device_type: "mobile",
    started_ip_address: "203.0.113.10",
    submitted_ip_address: "203.0.113.11",
    ip_changed: true,
  };
  const attemptDetail = {
    id: attemptSummary.id,
    exam_share_id: "share-1",
    share_code: "public-code",
    exam_name: "红楼梦读书考试",
    book_title: "红楼梦",
    quiz_title: "第 2 套复习试卷",
    participant_type: "anonymous",
    participant_name: "林同学",
    status: "completed",
    total_score: 42.5,
    max_score: 100,
    elapsed_seconds: 386,
    started_at: attemptSummary.started_at,
    submitted_at: attemptSummary.submitted_at,
    completed_at: attemptSummary.completed_at,
    grading_error: null,
    device_type: "mobile",
    user_agent: "Mozilla/5.0 (iPhone) Mobile/15E148",
    started_ip_address: "203.0.113.10",
    submitted_ip_address: "203.0.113.11",
    ip_changed: true,
    duration_minutes: 15,
    source_mode: "pdf",
    access_token: null,
    recommended_direction: "优先深入掌握“人物语言”。建议回到相关章节核对原文。",
    weak_knowledge_points: [{
      knowledge_point: "人物语言",
      score: 42.5,
      max_score: 100,
      score_percentage: 42.5,
      question_count: 1,
      focus_points: ["凤姐以福寿之说奉承贾母"],
      recommendation: "建议回到相关章节核对原文。",
    }],
    questions: [{
      id: "question-1",
      position: 1,
      question_type: "single",
      prompt: "凤姐如何回应贾母的回忆？",
      options: [{ id: "A", text: "以福寿之说奉承" }, { id: "B", text: "保持沉默" }],
      knowledge_point: "人物语言",
      difficulty: "medium",
      estimated_seconds: 45,
      max_score: 100,
      correct_answers: ["A"],
      explanation: "凤姐借寿星的典故奉承贾母。",
      reference_answer: null,
      grading_rubric: [],
      source_evidence: [],
    }],
    answers: [{
      question_id: "question-1",
      selected_answers: ["B"],
      text_answer: null,
      score: 42.5,
      max_score: 100,
      is_correct: false,
      feedback: "答案不正确。",
      matched_points: [],
      missing_points: ["A"],
      grading_status: "completed",
    }],
  };
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(currentUser) });
  });
  await page.route("**/api/exam-shares/share-1", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ ...examShare, started_count: 1, submitted_count: 1, grading_count: 0, attempts: [attemptSummary] }) });
  });
  await page.route("**/api/exam-shares/share-1/attempts/attempt-completed", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(attemptDetail) });
  });

  await page.goto("/exam-management/share-1");
  await expect(page.getByRole("img", { name: "已完成参与者实际得分柱状图" })).toBeVisible();
  await expect(page.locator(".score-bar")).toContainText("42.5");
  const attemptRow = page.locator(".attempt-table tbody tr").first();
  await expect(attemptRow.locator("td").nth(3)).toContainText("已完成");
  await expect(attemptRow.locator("td").nth(4)).toContainText("42.5 / 100");
  expect(await attemptRow.locator("td").nth(3).evaluate((element) => getComputedStyle(element).display)).toBe("table-cell");
  expect(await attemptRow.locator("td").nth(4).evaluate((element) => getComputedStyle(element).display)).toBe("table-cell");
  await expect(attemptRow.getByText("提交 IP 已变化")).toBeVisible();

  await page.getByRole("button", { name: "查看林同学的答卷" }).click();
  await expect(page.getByRole("heading", { name: "薄弱知识与深入方向" })).toBeVisible();
  await expect(page.getByText("凤姐以福寿之说奉承贾母")).toBeVisible();
  await expect(page.getByText("203.0.113.11")).toBeVisible();
});

test("公开结果展示答案但不展示 PDF 原文", async ({ page }) => {
  const result = {
    id: "attempt-1",
    exam_share_id: "share-1",
    share_code: "public-code",
    exam_name: "红楼梦读书考试",
    book_title: "红楼梦",
    quiz_title: "第 2 套复习试卷",
    participant_type: "anonymous",
    participant_name: "匿名读者",
    status: "completed",
    total_score: 40,
    max_score: 100,
    elapsed_seconds: 180,
    started_at: "2026-08-06T08:00:00Z",
    submitted_at: "2026-08-06T08:03:00Z",
    completed_at: "2026-08-06T08:03:10Z",
    grading_error: null,
    device_type: null,
    user_agent: null,
    started_ip_address: null,
    submitted_ip_address: null,
    ip_changed: false,
    duration_minutes: 15,
    source_mode: "pdf",
    access_token: null,
    recommended_direction: "优先深入掌握“人物语言”，重点核对人物回应方式。",
    weak_knowledge_points: [{
      knowledge_point: "人物语言",
      score: 40,
      max_score: 100,
      score_percentage: 40,
      question_count: 1,
      focus_points: ["A. 以福寿之说奉承"],
      recommendation: "重点核对人物回应方式。",
    }],
    questions: [{
      id: "question-1",
      position: 1,
      question_type: "single",
      prompt: "凤姐如何回应贾母的回忆？",
      options: [{ id: "A", text: "以福寿之说奉承" }, { id: "B", text: "保持沉默" }],
      knowledge_point: "人物语言",
      difficulty: "medium",
      estimated_seconds: 45,
      max_score: 100,
      correct_answers: ["A"],
      explanation: "凤姐借寿星的典故奉承贾母。",
      reference_answer: null,
      grading_rubric: [],
      source_evidence: [],
    }],
    answers: [{
      question_id: "question-1",
      selected_answers: ["B"],
      text_answer: null,
      score: 40,
      max_score: 100,
      is_correct: false,
      feedback: "答案不正确。",
      matched_points: [],
      missing_points: ["A"],
      grading_status: "completed",
    }],
  };
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "请先登录" }) });
  });
  await page.route("**/api/public/exam-attempts/attempt-1/result", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(result) });
  });

  await page.goto("/exams/public-code/results/attempt-1");
  await expect(page.getByText("40", { exact: true })).toBeVisible();
  await expect(page.getByText("A. 以福寿之说奉承", { exact: true })).toBeVisible();
  await expect(page.getByText("公开结果不展示 PDF 文件名、页码和原文摘录。")).toBeVisible();
  await expect(page.getByRole("heading", { name: "薄弱知识与深入方向" })).toBeVisible();
  await expect(page.getByText("优先深入掌握“人物语言”，重点核对人物回应方式。")).toBeVisible();
  await expect(page.getByText("测试书.pdf")).toHaveCount(0);
  await expect(page.locator(".result-score")).toHaveClass(/low/);
});
