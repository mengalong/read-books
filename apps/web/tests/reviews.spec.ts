import { expect, test } from "@playwright/test";

const reviews = [
  {
    id: "review-1",
    quiz_id: "quiz-1",
    book_id: "book-1",
    book_title: "红楼梦",
    title: "第 1 套复习试卷",
    difficulty: "medium",
    status: "submitted",
    total_score: 8,
    max_score: 10,
    duration_minutes: 15,
    elapsed_seconds: 120,
    question_count: 5,
    created_at: "2026-08-03T10:00:00Z",
    submitted_at: "2026-08-03T10:02:00Z",
    next_review_date: "2026-08-10",
    attempt_number: 1,
  },
  {
    id: "review-2",
    quiz_id: "quiz-2",
    book_id: "book-2",
    book_title: "流俗地",
    title: "第 1 套复习试卷",
    difficulty: "medium",
    status: "submitted",
    total_score: 9,
    max_score: 10,
    duration_minutes: 15,
    elapsed_seconds: 180,
    question_count: 5,
    created_at: "2026-08-03T11:00:00Z",
    submitted_at: "2026-08-03T11:03:00Z",
    next_review_date: "2026-08-10",
    attempt_number: 1,
  },
];

test("复习记录按回车搜索并使用统一时间格式", async ({ page }) => {
  const requestUrls: string[] = [];
  await page.route("**/api/reviews**", async (route) => {
    const requestUrl = route.request().url();
    requestUrls.push(requestUrl);
    const search = new URL(requestUrl).searchParams.get("search");
    const result = search ? reviews.filter((review) => review.book_title.includes(search)) : reviews;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(result) });
  });

  await page.goto("/reviews");
  await expect(page.getByText("2 条记录")).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "操作" })).toBeVisible();
  await expect(page.locator(".page-header svg")).toHaveCount(0);
  await expect(page.getByRole("cell", { name: "2026-08-03 18:02:00" })).toBeVisible();

  const searchInput = page.getByLabel("按书名或作者搜索复习记录");
  await searchInput.fill("红楼梦");
  await page.waitForTimeout(350);
  expect(requestUrls).toHaveLength(1);
  await expect(page.getByText("2 条记录")).toBeVisible();

  await searchInput.press("Enter");
  await expect(page.getByText("1 条记录")).toBeVisible();
  expect(new URL(requestUrls.at(-1)!).searchParams.get("search")).toBe("红楼梦");
});
