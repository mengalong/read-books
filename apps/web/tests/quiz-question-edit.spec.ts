import { expect, test } from "@playwright/test";

import { mockAdminIdentity } from "./test-helpers";

test("结果页可人工修正题干、选项和标准答案", async ({ page }) => {
  await mockAdminIdentity(page);

  let savedPayload: Record<string, unknown> | null = null;
  await page.route("**/api/quizzes/quiz-edit/result", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "quiz-edit",
        book_id: "book-1",
        book_title: "测试书",
        title: "第 1 套复习试卷",
        difficulty: "medium",
        duration_minutes: 15,
        status: "submitted",
        source_mode: "pdf",
        total_score: 4,
        max_score: 6,
        elapsed_seconds: 120,
        submitted_at: "2026-08-03T10:00:00Z",
        next_review_date: "2026-08-04",
        created_at: "2026-08-03T09:00:00Z",
        questions: [
          {
            id: "q1",
            position: 1,
            question_type: "single",
            prompt: "原题干",
            options: [
              { id: "A", text: "原选项 A" },
              { id: "B", text: "原选项 B" },
              { id: "C", text: "原选项 C" },
              { id: "D", text: "原选项 D" },
            ],
            explanation: "原解析",
            knowledge_point: "原知识点",
            difficulty: "medium",
            estimated_seconds: 45,
            reference_answer: null,
            grading_rubric: [],
            source_evidence: [],
            max_score: 6,
            correct_answers: ["A"],
          },
        ],
        answers: [
          {
            question_id: "q1",
            selected_answers: ["C"],
            text_answer: null,
            score: 0,
            max_score: 6,
            is_correct: false,
            feedback: "原反馈",
            matched_points: [],
            missing_points: ["A"],
          },
        ],
        weak_points: [],
      }),
    });
  });

  await page.route("**/api/quizzes/quiz-edit/questions/q1", async (route) => {
    if (route.request().method() === "PATCH") {
      savedPayload = route.request().postDataJSON();
    }
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "q1",
        position: 1,
        question_type: "single",
        prompt: "修正后的题干",
        options: [
          { id: "A", text: "错误选项" },
          { id: "B", text: "正确选项" },
          { id: "C", text: "干扰项一" },
          { id: "D", text: "干扰项二" },
        ],
        explanation: "修正后的解析",
        knowledge_point: "修正后的知识点",
        difficulty: "medium",
        estimated_seconds: 45,
        reference_answer: null,
        grading_rubric: [],
        source_evidence: [],
        max_score: 6,
        correct_answers: ["B"],
      }),
    });
  });

  await page.goto("/quizzes/quiz-edit/result");
  await page.getByRole("button", { name: "编辑题目" }).click();

  await page.getByLabel("题干").fill("修正后的题干");
  await page.getByLabel("知识点").fill("修正后的知识点");
  await page.getByLabel("解析说明").fill("修正后的解析");
  await page.getByPlaceholder("选项 A").fill("错误选项");
  await page.getByPlaceholder("选项 B").fill("正确选项");
  await page.getByPlaceholder("选项 C").fill("干扰项一");
  await page.getByPlaceholder("选项 D").fill("干扰项二");
  await page.locator(".question-answer-choice").nth(1).click();
  await page.getByRole("button", { name: "保存修改" }).click();

  await expect(page.getByText("修正后的题干")).toBeVisible();
  expect(savedPayload).toMatchObject({
    prompt: "修正后的题干",
    knowledge_point: "修正后的知识点",
    explanation: "修正后的解析",
    correct_answers: ["B"],
  });
});
