import { expect, test } from "@playwright/test";

import { mockAdminIdentity } from "./test-helpers";

test("试卷编辑页可直接修正题干、选项和标准答案", async ({ page }) => {
  await mockAdminIdentity(page);

  let savedPayload: Record<string, unknown> | null = null;
  await page.route("**/api/quizzes/quiz-edit/editable", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "quiz-edit",
        book_id: "book-1",
        book_title: "测试书",
        title: "第 1 套复习试卷",
        difficulty: "medium",
        duration_minutes: 15,
        status: "ready",
        source_mode: "pdf",
        total_score: null,
        max_score: 6,
        elapsed_seconds: null,
        submitted_at: null,
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

  await page.goto("/quizzes/quiz-edit/edit");

  await page.getByLabel("题干").fill("修正后的题干");
  await page.getByLabel("知识点").fill("修正后的知识点");
  await page.getByLabel("解析说明").fill("修正后的解析");
  await page.getByPlaceholder("选项 A").fill("错误选项");
  await page.getByPlaceholder("选项 B").fill("正确选项");
  await page.getByPlaceholder("选项 C").fill("干扰项一");
  await page.getByPlaceholder("选项 D").fill("干扰项二");
  await page.locator(".question-answer-choice").nth(1).click();
  await page.getByRole("button", { name: "保存本题" }).click();

  await expect(page.getByText("修正后的题干")).toBeVisible();
  await expect(page.getByText("已保存")).toBeVisible();
  expect(savedPayload).toMatchObject({
    prompt: "修正后的题干",
    knowledge_point: "修正后的知识点",
    explanation: "修正后的解析",
    correct_answers: ["B"],
  });
});

test("试卷编辑页支持单题重出并刷新当前题目", async ({ page }) => {
  await mockAdminIdentity(page);

  let regenerateCalled = false;
  await page.route("**/api/quizzes/quiz-edit/editable", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "quiz-edit",
        book_id: "book-1",
        book_title: "测试书",
        title: "第 1 套复习试卷",
        difficulty: "medium",
        duration_minutes: 15,
        status: "ready",
        source_mode: "pdf",
        total_score: null,
        max_score: 6,
        elapsed_seconds: null,
        submitted_at: null,
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
      }),
    });
  });

  await page.route("**/api/quizzes/quiz-edit/questions/q1/regenerate", async (route) => {
    regenerateCalled = true;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "q1",
        position: 1,
        question_type: "single",
        prompt: "重出的题干",
        options: [
          { id: "A", text: "新选项 A" },
          { id: "B", text: "新选项 B" },
          { id: "C", text: "新选项 C" },
          { id: "D", text: "新选项 D" },
        ],
        explanation: "重出后的解析",
        knowledge_point: "重出后的知识点",
        difficulty: "medium",
        estimated_seconds: 45,
        reference_answer: null,
        grading_rubric: [],
        source_evidence: [],
        max_score: 6,
        correct_answers: ["C"],
      }),
    });
  });

  await page.goto("/quizzes/quiz-edit/edit");
  await page.getByRole("button", { name: "重出本题" }).click();

  await expect(page.getByLabel("题干")).toHaveValue("重出的题干");
  await expect(page.getByLabel("知识点")).toHaveValue("重出后的知识点");
  await expect(page.getByText("重出的题干")).toBeVisible();
  expect(regenerateCalled).toBe(true);
});

test("书籍页选择试卷先看概览，再开始答题进入复习", async ({ page }) => {
  await mockAdminIdentity(page);

  let reviewRequests = 0;
  await page.route("**/api/books/book-1", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "book-1",
        workspace_id: "workspace-1",
        owner_user_id: "admin-1",
        owner_display_name: "系统管理员",
        title: "测试书",
        author: "测试作者",
        description: "测试描述",
        cover_color: "#2f6b5f",
        language: "zh",
        reading_status: "reading",
        shelf_status: "active",
        tags: [],
        created_at: "2026-08-03T09:00:00Z",
        updated_at: "2026-08-03T09:00:00Z",
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
          quiz_count: 1,
          average_score: null,
          last_reviewed_at: null,
          next_review_date: null,
        },
        pdfs: [],
        quizzes: [
          {
            id: "quiz-1",
            book_id: "book-1",
            title: "第一套试卷",
            difficulty: "medium",
            duration_minutes: 15,
            status: "ready",
            source_mode: "pdf",
            question_count: 1,
            single_count: 1,
            multiple_count: 0,
            short_count: 0,
            max_score: 6,
            created_at: "2026-08-03T09:00:00Z",
            review_count: 0,
            latest_score: null,
            last_reviewed_at: null,
          },
        ],
      }),
    });
  });

  await page.route("**/api/quizzes/quiz-1", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "quiz-1",
        book_id: "book-1",
        book_title: "测试书",
        title: "第一套试卷",
        difficulty: "medium",
        duration_minutes: 15,
        status: "ready",
        source_mode: "pdf",
        total_score: null,
        max_score: 6,
        elapsed_seconds: null,
        submitted_at: null,
        next_review_date: null,
        created_at: "2026-08-03T09:00:00Z",
        questions: [
          {
            id: "q1",
            position: 1,
            question_type: "single",
            prompt: "题干",
            options: [
              { id: "A", text: "选项 A" },
              { id: "B", text: "选项 B" },
              { id: "C", text: "选项 C" },
              { id: "D", text: "选项 D" },
            ],
            explanation: "解析",
            knowledge_point: "知识点",
            difficulty: "medium",
            estimated_seconds: 45,
            reference_answer: null,
            grading_rubric: [],
            source_evidence: [],
            max_score: 6,
            correct_answers: ["A"],
          },
        ],
      }),
    });
  });

  await page.route("**/api/quizzes/quiz-1/reviews", async (route) => {
    reviewRequests += 1;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "review-1",
        quiz_id: "quiz-1",
        book_id: "book-1",
        book_title: "测试书",
        title: "第一套试卷",
        attempt_number: 1,
        status: "in_progress",
        source_mode: "pdf",
        difficulty: "medium",
        duration_minutes: 15,
        total_score: null,
        max_score: 6,
        elapsed_seconds: null,
        submitted_at: null,
        next_review_date: null,
        created_at: "2026-08-03T09:00:00Z",
        questions: [
          {
            id: "q1",
            position: 1,
            question_type: "single",
            prompt: "题干",
            options: [
              { id: "A", text: "选项 A" },
              { id: "B", text: "选项 B" },
              { id: "C", text: "选项 C" },
              { id: "D", text: "选项 D" },
            ],
            explanation: "解析",
            knowledge_point: "知识点",
            difficulty: "medium",
            estimated_seconds: 45,
            reference_answer: null,
            grading_rubric: [],
            source_evidence: [],
            max_score: 6,
            correct_answers: null,
          },
        ],
        answers: [],
        weak_points: [],
      }),
    });
  });

  await page.route("**/api/reviews/review-1", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "review-1",
        quiz_id: "quiz-1",
        book_id: "book-1",
        book_title: "测试书",
        title: "第一套试卷",
        attempt_number: 1,
        status: "in_progress",
        source_mode: "pdf",
        difficulty: "medium",
        duration_minutes: 15,
        total_score: null,
        max_score: 6,
        elapsed_seconds: null,
        submitted_at: null,
        next_review_date: null,
        created_at: "2026-08-03T09:00:00Z",
        questions: [
          {
            id: "q1",
            position: 1,
            question_type: "single",
            prompt: "题干",
            options: [
              { id: "A", text: "选项 A" },
              { id: "B", text: "选项 B" },
              { id: "C", text: "选项 C" },
              { id: "D", text: "选项 D" },
            ],
            explanation: "解析",
            knowledge_point: "知识点",
            difficulty: "medium",
            estimated_seconds: 45,
            reference_answer: null,
            grading_rubric: [],
            source_evidence: [],
            max_score: 6,
            correct_answers: null,
          },
        ],
        answers: [],
        weak_points: [],
      }),
    });
  });

  await page.goto("/books/book-1");

  await expect(page.getByRole("button", { name: "分享考试" })).toBeVisible();
  await expect(page.getByRole("link", { name: "编辑第一套试卷" })).toHaveAttribute("href", "/quizzes/quiz-1/edit");

  await page.getByRole("link", { name: "选择这套" }).click();
  await expect(page).toHaveURL(/\/quizzes\/quiz-1$/);
  await expect(page.getByRole("button", { name: "开始答题" })).toBeVisible();
  expect(reviewRequests).toBe(0);
  await expect(page.getByRole("button", { name: "编辑题目" })).toHaveCount(0);

  await page.getByRole("button", { name: "开始答题" }).click();
  await expect(page).toHaveURL(/\/reviews\/review-1$/);
  expect(reviewRequests).toBe(1);
});

test("结果页不显示题目编辑入口", async ({ page }) => {
  await mockAdminIdentity(page);

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
        questions: [],
        answers: [],
        weak_points: [],
      }),
    });
  });

  await page.goto("/quizzes/quiz-edit/result");
  await expect(page.getByRole("button", { name: "编辑题目" })).toHaveCount(0);
});
