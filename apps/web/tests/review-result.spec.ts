import { expect, test } from "@playwright/test";

test("结果页区分实际得分与得分率", async ({ page }) => {
  await page.route("**/api/reviews/score-display/result", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "score-display",
        quiz_id: "quiz-1",
        book_id: "book-1",
        book_title: "解忧杂货店",
        title: "第 1 套复习试卷",
        attempt_number: 1,
        status: "submitted",
        difficulty: "medium",
        duration_minutes: 15,
        total_score: 4.2,
        max_score: 36,
        elapsed_seconds: 180,
        submitted_at: "2026-08-03T10:00:00Z",
        next_review_date: "2026-08-04",
        created_at: "2026-08-03T09:00:00Z",
        questions: [],
        answers: [],
        weak_points: [],
      }),
    });
  });

  await page.goto("/reviews/score-display/result");

  await expect(page.locator(".score-number strong")).toHaveText("4.2");
  await expect(page.locator(".score-number span")).toHaveText("/ 36");
  await expect(page.locator(".score-copy")).toContainText("得分率 12%");
  await expect(page.locator(".result-score")).toHaveClass(/low/);
});
