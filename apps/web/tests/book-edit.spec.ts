import { expect, test } from "@playwright/test";

import { mockAdminIdentity } from "./test-helpers";

test("修改书籍信息并返回详情页", async ({ page }) => {
  await mockAdminIdentity(page);
  let savedPayload: Record<string, unknown> | null = null;
  const book = {
    id: "book-edit",
    title: "红楼梦",
    author: "曹雪芹",
    description: "原有简介",
    cover_color: "#2F6B5F",
    language: "中文",
    reading_status: "finished",
    tags: ["古典文学"],
    stats: { pdf_count: 1, completed_pdf_count: 1, chunk_count: 10, quiz_count: 0, average_score: null, last_reviewed_at: null, next_review_date: null },
    pre_generation_enabled: false,
    pre_generation_status: "disabled",
    pre_generation_error: null,
    pre_generation_quiz_id: null,
    active_generation_task_id: null,
    active_generation_status: null,
    active_generation_completed_questions: 0,
    active_generation_total_questions: 0,
    active_generation_phase: null,
    pdfs: [],
    quizzes: [],
  };

  await page.route("**/api/books/book-edit", async (route) => {
    if (route.request().method() === "PATCH") {
      savedPayload = route.request().postDataJSON();
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ ...book, ...(savedPayload || {}) }) });
  });

  await page.goto("/books/book-edit/edit");
  await expect(page.getByRole("heading", { name: "修改资源信息" })).toBeVisible();
  await expect(page.getByLabel("资源名称")).toHaveValue("红楼梦");

  await page.getByLabel("资源名称").fill("红楼梦（校订版）");
  await page.getByLabel("一句话备注").fill("更新后的简介");
  await page.getByLabel("阅读状态").selectOption("reviewing");
  await page.getByLabel("标签").fill("古典文学，版本研究");
  await page.getByRole("button", { name: "保存修改" }).click();

  await expect(page).toHaveURL(/\/books\/book-edit$/);
  expect(savedPayload).toMatchObject({
    title: "红楼梦（校订版）",
    description: "更新后的简介",
    reading_status: "reviewing",
    tags: ["古典文学", "版本研究"],
  });
});
