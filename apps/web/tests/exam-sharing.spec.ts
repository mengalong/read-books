import { expect, test } from "@playwright/test";
import { stat } from "node:fs/promises";

import { mockAdminIdentity, mockInsecureClipboard, readCopiedText } from "./test-helpers";

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
  identity_type: "anonymous",
  participant_name: null,
  participant_avatar_url: null,
  wechat_login_enabled: false,
  wechat_login_required: false,
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
  attempts_total: 4,
  attempts_page: 1,
  attempts_page_size: 20,
  graded_count: 1,
  average_points: 42.5,
  median_points: 42.5,
  median_score: 42.5,
  above_threshold_count: 0,
  above_threshold_rate: 0,
  score_distribution: [
    { label: "0–59", min_score: 0, max_score: 59, count: 1, percentage: 100 },
    { label: "60–69", min_score: 60, max_score: 69, count: 0, percentage: 0 },
    { label: "70–79", min_score: 70, max_score: 79, count: 0, percentage: 0 },
    { label: "80–89", min_score: 80, max_score: 89, count: 0, percentage: 0 },
    { label: "90–100", min_score: 90, max_score: 100, count: 0, percentage: 0 },
  ],
  participation_granularity: "month",
  participation_year: 2026,
  participation_month: 8,
  participation_periods: [
    { period_key: "2026-08-06", period_label: "2026-08-06", participant_count: 1, completed_count: 1 },
  ],
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
  expect(await page.evaluate(() => window.localStorage.getItem("huijuan:exam:public-code"))).toContain("attempt-in-progress");
});

test("考试过期后提示已经结束并禁止开始答题", async ({ page }) => {
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "请先登录" }) });
  });
  await page.route("**/api/public/exams/public-code", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ ...publicExam, status: "expired", expires_at: "2026-08-06T08:30:00Z" }),
    });
  });

  await page.goto("/exams/public-code");
  await expect(page.getByText("你来晚了，考试已经结束", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "开始答题" })).toHaveCount(0);
  await expect(page.getByText("2026-08-06 16:30:00")).toBeVisible();
});

test("参加过考试的匿名用户可以从原浏览器查看历史答卷", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "huijuan:exam:public-code",
      JSON.stringify({ attemptId: "attempt-completed", token: "saved-attempt-token" }),
    );
  });
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "请先登录" }) });
  });
  await page.route("**/api/public/exams/public-code", async (route) => {
    expect(route.request().headers()["x-exam-attempt-token"]).toBe("saved-attempt-token");
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ...publicExam,
        status: "expired",
        expires_at: "2026-08-06T08:30:00Z",
        existing_attempt_id: "attempt-completed",
        existing_attempt_status: "completed",
      }),
    });
  });

  await page.goto("/exams/public-code");
  await expect(page.getByText("你参加过这场考试")).toBeVisible();
  await expect(page.getByRole("button", { name: "查看答题记录" })).toBeVisible();
  await page.getByRole("button", { name: "查看答题记录" }).click();
  await expect(page).toHaveURL(/\/exams\/public-code\/results\/attempt-completed$/);
});

test("要求微信认证时不再允许手填身份开始答题", async ({ page }) => {
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "请先登录" }) });
  });
  await page.route("**/api/public/exams/public-code", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ ...publicExam, wechat_login_enabled: true, wechat_login_required: true }),
    });
  });

  await page.goto("/exams/public-code");
  await expect(page.getByRole("button", { name: "微信登录答题" })).toBeVisible();
  await expect(page.getByPlaceholder("填写你的答题名称")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "开始答题" })).toHaveCount(0);
});

test("微信参与者再次进入可以查看历史答卷", async ({ page }) => {
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "请先登录" }) });
  });
  await page.route("**/api/public/exams/public-code", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ...publicExam,
        authenticated: true,
        identity_type: "wechat",
        participant_name: "微信读者",
        participant_avatar_url: "https://example.com/wechat-avatar.png",
        wechat_login_enabled: true,
        existing_attempt_id: "wechat-attempt-completed",
        existing_attempt_status: "completed",
      }),
    });
  });

  await page.goto("/exams/public-code");
  await expect(page.getByText("你参加过这场考试")).toBeVisible();
  await page.getByRole("button", { name: "查看答题记录" }).click();
  await expect(page).toHaveURL(/\/results\/wechat-attempt-completed$/);
});

test("考试管理展示分享链接和答题统计", async ({ page }) => {
  await mockInsecureClipboard(page);
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(currentUser) });
  });
  await page.route("**/api/exam-shares**", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify([examShare]) });
  });

  await page.goto("/exam-management");
  await expect(page.getByRole("heading", { name: "考试管理" })).toBeVisible();
  await expect(page.getByRole("cell", { name: /红楼梦读书考试/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "编辑考试题目" })).toHaveAttribute("href", "/exam-management/share-1/edit");
  await expect(page.getByText("3 / 4")).toBeVisible();
  await expect(page.getByText("78.5%")).toBeVisible();
  await expect(page.getByRole("button", { name: "复制考试链接" })).toBeVisible();
  await page.getByRole("button", { name: "复制考试链接" }).click();
  await expect(page.getByRole("button", { name: "考试链接已复制" })).toBeVisible();
  const origin = new URL(page.url()).origin;
  expect(await readCopiedText(page)).toBe(`${origin}/exams/public-code`);
  await page.getByRole("button", { name: "设置考试有效期" }).click();
  await expect(page.getByRole("heading", { name: "设置考试有效期" })).toBeVisible();
  await expect(page.getByText("关闭后考试长期有效。")).toBeVisible();
  const activityRow = page.locator(".exam-management-table tbody tr").first();
  await expect(activityRow.locator("td").nth(2)).toContainText("3 / 4");
  await expect(activityRow.locator("td").nth(3)).toContainText("78.5%");
  expect(await activityRow.locator("td").nth(2).evaluate((element) => getComputedStyle(element).display)).toBe("table-cell");
  expect(await activityRow.locator("td").nth(3).evaluate((element) => getComputedStyle(element).display)).toBe("table-cell");
});

test("考试编辑页可以修改题目、重出单题并删除历史版本", async ({ page }) => {
  await mockAdminIdentity(page);

  const createdAt = "2026-08-06T08:00:00Z";
  const initialQuestion = {
    id: "question-1",
    position: 1,
    question_type: "single",
    prompt: "原题干",
    options: [
      { id: "A", text: "原选项 A" },
      { id: "B", text: "原选项 B" },
      { id: "C", text: "原选项 C" },
      { id: "D", text: "原选项 D" },
    ],
    knowledge_point: "原知识点",
    difficulty: "medium",
    estimated_seconds: 45,
    max_score: 6,
    correct_answers: ["A"],
    explanation: "原解析",
    reference_answer: null,
    grading_rubric: [],
    source_evidence: [],
  };
  let question = initialQuestion;
  let snapshotVersion = 1;
  let versionNumbers = [1];
  let savedPayload: Record<string, unknown> | null = null;
  let deletedVersion: number | null = null;

  function versionSummary(version: number) {
    return {
      version,
      is_current: version === snapshotVersion,
      question_count: 1,
      single_count: 1,
      multiple_count: 0,
      short_count: 0,
      max_score: 6,
      created_at: createdAt,
    };
  }

  function editableResponse() {
    return {
      id: "share-edit",
      share_code: "edit-code",
      name: "考试编辑测试",
      status: "active",
      quiz_id: "quiz-edit",
      book_id: "book-edit",
      owner_user_id: "admin-1",
      owner_username: "admin",
      owner_display_name: "系统管理员",
      book_title: "测试书",
      book_author: "测试作者",
      quiz_title: "第 1 套复习试卷",
      source_mode: "pdf",
      difficulty: "medium",
      duration_minutes: 15,
      max_score: 6,
      snapshot_version: snapshotVersion,
      created_at: createdAt,
      updated_at: createdAt,
      questions: [question],
      versions: [...versionNumbers].reverse().map((version) => versionSummary(version)),
    };
  }

  await page.route("**/api/exam-shares/share-edit/editable", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(editableResponse()) });
  });
  await page.route("**/api/exam-shares/share-edit/questions/question-1", async (route) => {
    if (route.request().method() === "PATCH") {
      savedPayload = route.request().postDataJSON();
      const body = savedPayload as {
        prompt?: string;
        knowledge_point?: string;
        explanation?: string | null;
        options?: { id: string; text: string }[];
        correct_answers?: string[];
      };
      question = {
        ...question,
        prompt: body.prompt || question.prompt,
        knowledge_point: body.knowledge_point || question.knowledge_point,
        explanation: body.explanation ?? question.explanation,
        options: body.options || question.options,
        correct_answers: body.correct_answers || question.correct_answers,
      };
      snapshotVersion = 2;
      versionNumbers = [1, 2];
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(question) });
  });
  await page.route("**/api/exam-shares/share-edit/questions/question-1/regenerate", async (route) => {
    question = {
      ...question,
      prompt: "重出的题干",
      knowledge_point: "重出后的知识点",
      explanation: "重出后的解析",
      options: [
        { id: "A", text: "新选项 A" },
        { id: "B", text: "新选项 B" },
        { id: "C", text: "新选项 C" },
        { id: "D", text: "新选项 D" },
      ],
      correct_answers: ["C"],
    };
    snapshotVersion = 3;
    versionNumbers = [1, 2, 3];
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(question) });
  });
  await page.route("**/api/exam-shares/share-edit/versions/1", async (route) => {
    deletedVersion = 1;
    versionNumbers = versionNumbers.filter((version) => version !== 1);
    await route.fulfill({ status: 204, body: "" });
  });

  await page.goto("/exam-management/share-edit/edit");
  await expect(page.getByRole("heading", { name: "考试编辑测试" })).toBeVisible();
  await expect(page.getByText("当前编辑的是考试快照版本，新版本会只影响后续开始的答题。")).toBeVisible();
  await expect(page.getByLabel("题干")).toHaveValue("原题干");

  await page.getByLabel("题干").fill("修正后的题干");
  await page.getByLabel("知识点").fill("修正后的知识点");
  await page.getByLabel("解析说明").fill("修正后的解析");
  await page.getByPlaceholder("选项 A").fill("错误选项");
  await page.getByPlaceholder("选项 B").fill("正确选项");
  await page.getByPlaceholder("选项 C").fill("干扰项一");
  await page.getByPlaceholder("选项 D").fill("干扰项二");
  await page.locator(".question-answer-choice").nth(1).click();
  await page.getByRole("button", { name: "保存本题" }).click();

  await expect(page.getByText("已保存")).toBeVisible();
  expect(savedPayload).toMatchObject({
    prompt: "修正后的题干",
    knowledge_point: "修正后的知识点",
    explanation: "修正后的解析",
    correct_answers: ["B"],
  });
  await expect(page.getByLabel("题干")).toHaveValue("修正后的题干");
  await expect(page.getByText("v2 · 当前")).toBeVisible();

  await page.getByRole("button", { name: "重出本题" }).click();
  await expect(page.getByRole("heading", { name: "确认重新出题" })).toBeVisible();
  await page.getByRole("button", { name: "确认重新出题" }).click();
  await expect(page.getByLabel("题干")).toHaveValue("重出的题干");
  await expect(page.getByText("v3 · 当前")).toBeVisible();

  page.once("dialog", async (dialog) => {
    await dialog.accept();
  });
  await page.getByRole("button", { name: "删除历史版本 v1" }).click();
  await expect(page.getByText("2 个版本")).toBeVisible();
  expect(deletedVersion).toBe(1);
});

test("考试详情展示成绩分布、风控信息和个人学习方向", async ({ page }) => {
  await mockInsecureClipboard(page);
  const attemptSummary = {
    id: "attempt-completed",
    participant_type: "wechat",
    participant_user_id: null,
    participant_name: "林同学",
    participant_avatar_url: "https://example.com/wechat-avatar.png",
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
    participant_type: "wechat",
    participant_name: "林同学",
    participant_avatar_url: "https://example.com/wechat-avatar.png",
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
  await page.route("**/api/exam-shares/share-1**", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ ...examShare, started_count: 1, submitted_count: 1, grading_count: 0, attempts: [attemptSummary] }) });
  });
  await page.route("**/api/exam-shares/share-1/attempts/attempt-completed", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(attemptDetail) });
  });

  await page.goto("/exam-management/share-1");
  await page.getByRole("button", { name: "复制链接" }).click();
  await expect(page.getByRole("button", { name: "已复制" })).toBeVisible();
  expect(await readCopiedText(page)).toBe(`${new URL(page.url()).origin}/exams/public-code`);
  await expect(page.getByRole("heading", { name: "参与考试人数" })).toBeVisible();
  await expect(page.locator(".participation-calendar-weekdays")).toContainText("一");
  await expect(page.locator(".participation-calendar-month .participation-calendar-cell")).toHaveCount(42);
  const juneCell = page.locator(".participation-calendar-month .participation-calendar-cell").filter({ hasText: "6" }).first();
  await expect(juneCell.locator(".participation-stat-participants strong")).toHaveText("1");
  await expect(juneCell.locator(".participation-stat-completed strong")).toHaveText("1");
  await expect(page.locator(".participation-calendar-month")).toBeVisible();
  await expect(page.locator(".participation-line-chart")).toHaveCount(0);
  await page.getByRole("button", { name: "折线图" }).click();
  await expect(page.locator(".participation-calendar-month")).toHaveCount(0);
  await expect(page.locator(".participation-line-chart")).toBeVisible();
  await expect(page.locator(".participation-chart-line")).toHaveCount(2);
  await page.getByRole("button", { name: "日历" }).click();
  await expect(page.locator(".participation-calendar-month")).toBeVisible();
  await expect(page.getByRole("heading", { name: "成绩分布" })).toBeVisible();
  const attemptRow = page.locator(".attempt-table tbody tr").first();
  await expect(attemptRow.locator("td").nth(3)).toContainText("已完成");
  await expect(attemptRow.locator("td").nth(4)).toContainText("42.5 / 100");
  await expect(attemptRow.getByText("微信认证")).toBeVisible();
  await expect(attemptRow.locator(".participant-avatar img")).toHaveCount(1);
  expect(await attemptRow.locator("td").nth(3).evaluate((element) => getComputedStyle(element).display)).toBe("table-cell");
  expect(await attemptRow.locator("td").nth(4).evaluate((element) => getComputedStyle(element).display)).toBe("table-cell");
  await expect(attemptRow.getByText("提交 IP 已变化")).toBeVisible();
  const actionCell = attemptRow.locator("td").last();
  expect(await actionCell.evaluate((element) => getComputedStyle(element).position)).toBe("sticky");
  await page.getByLabel("搜索参与者名称或 IP").fill("203.0.113.10");
  await page.getByRole("button", { name: "搜索答题记录" }).click();
  await expect(page).toHaveURL(/search=203\.0\.113\.10/);
  await page.getByLabel("每页显示记录数").selectOption("200");
  await expect(page).toHaveURL(/page_size=200/);
  await page.getByLabel("参与人数统计方式").selectOption("year");
  await expect(page).toHaveURL(/granularity=year/);
  await expect(page.getByRole("button", { name: "查看林同学的答卷" })).toBeVisible();
  await expect(page.getByRole("button", { name: "下载林同学的答题报告" })).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载林同学的答题报告" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("红楼梦读书考试-林同学-答题报告.png");
  expect((await stat(await download.path())).size).toBeGreaterThan(1000);

  await page.getByRole("button", { name: "查看林同学的答卷" }).click();
  await expect(page.getByRole("heading", { name: "薄弱知识与深入方向" })).toBeVisible();
  await expect(page.getByText("凤姐以福寿之说奉承贾母")).toBeVisible();
  await expect(page.getByText("203.0.113.11")).toBeVisible();
  await expect(page.getByRole("button", { name: "导出报告" })).toBeVisible();
});

test("创建考试后可以在 HTTP 页面复制分享链接", async ({ page }) => {
  await mockInsecureClipboard(page);
  const book = {
    id: "book-share",
    workspace_id: "workspace-1",
    owner_user_id: "admin-1",
    owner_display_name: "系统管理员",
    title: "红楼梦",
    author: "曹雪芹",
    description: "考试分享测试书籍",
    cover_color: "#2F6B5F",
    language: "中文",
    reading_status: "finished",
    shelf_status: "active",
    tags: [],
    created_at: "2026-08-06T08:00:00Z",
    updated_at: "2026-08-06T08:00:00Z",
    pre_generation_enabled: false,
    pre_generation_status: "disabled",
    pre_generation_error: null,
    pre_generation_quiz_id: null,
    active_generation_task_id: null,
    active_generation_status: null,
    active_generation_completed_questions: 0,
    active_generation_total_questions: 0,
    active_generation_phase: null,
    stats: {
      pdf_count: 1,
      completed_pdf_count: 1,
      chunk_count: 0,
      quiz_count: 1,
      average_score: null,
      last_reviewed_at: null,
      next_review_date: null,
    },
    pdfs: [],
    quizzes: [{
      id: "quiz-share",
      book_id: "book-share",
      title: "第 1 套复习试卷",
      difficulty: "medium",
      duration_minutes: 15,
      status: "ready",
      source_mode: "pdf",
      question_count: 2,
      single_count: 1,
      multiple_count: 0,
      short_count: 1,
      max_score: 100,
      created_at: "2026-08-06T08:00:00Z",
      review_count: 0,
      latest_score: null,
      last_reviewed_at: null,
    }],
  };
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(currentUser) });
  });
  await page.route("**/api/books/book-share", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(book) });
  });
  await page.route("**/api/quizzes/quiz-share/exam-shares", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ ...examShare, id: "created-share", share_code: "created-code" }),
    });
  });

  await page.goto("/books/book-share");
  await page.getByTitle("分享考试").click();
  await page.getByRole("button", { name: "生成考试链接" }).click();
  await expect(page.getByText("考试链接已创建")).toBeVisible();
  await page.getByRole("button", { name: "复制考试链接" }).click();
  await expect(page.getByRole("button", { name: "复制考试链接" })).toContainText("已复制");
  expect(await readCopiedText(page)).toBe(`${new URL(page.url()).origin}/exams/created-code`);
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
    participant_avatar_url: null,
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
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "保存结果长图" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("红楼梦读书考试-匿名读者-答题报告.png");
  expect((await stat(await download.path())).size).toBeGreaterThan(1000);
});
