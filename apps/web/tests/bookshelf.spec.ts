import { expect, test } from "@playwright/test";

import { mockAdminIdentity } from "./test-helpers";

function createBook(id: string, title: string, author: string) {
  return {
    id,
    title,
    author,
    description: `${title}简介`,
    cover_color: "#2F6B5F",
    language: "中文",
    reading_status: "finished",
    tags: [],
    created_at: "2026-08-03T10:00:00Z",
    updated_at: "2026-08-03T10:00:00Z",
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
      pdf_count: 0,
      completed_pdf_count: 0,
      chunk_count: 0,
      quiz_count: 0,
      average_score: null,
      last_reviewed_at: null,
      next_review_date: null,
    },
  };
}

test("书架输入完成后按回车搜索", async ({ page }) => {
  await mockAdminIdentity(page);
  const books = [createBook("book-1", "红楼梦", "曹雪芹"), createBook("book-2", "流俗地", "黎紫书")];
  const requestUrls: string[] = [];
  await page.route("**/api/books**", async (route) => {
    const requestUrl = route.request().url();
    requestUrls.push(requestUrl);
    const search = new URL(requestUrl).searchParams.get("search");
    const result = search
      ? books.filter((book) => book.title.includes(search) || book.author.includes(search))
      : books;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(result) });
  });

  await page.goto("/");
  await expect(page.getByText("2 条", { exact: true })).toBeVisible();

  const searchInput = page.getByLabel("搜索资源名称或主创");
  const requestCountBeforeTyping = requestUrls.length;
  await searchInput.fill("红楼梦");
  await page.waitForTimeout(350);
  expect(requestUrls).toHaveLength(requestCountBeforeTyping);
  await expect(page.getByText("2 条", { exact: true })).toBeVisible();

  await searchInput.press("Enter");
  await expect(page.getByText("1 条", { exact: true })).toBeVisible();
  expect(new URL(requestUrls.at(-1)!).searchParams.get("search")).toBe("红楼梦");
});
