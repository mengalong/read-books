import { expect, test } from "@playwright/test";

import { mockAdminIdentity, mockInsecureClipboard, readCopiedText } from "./test-helpers";

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

test("试卷出题过程页展示每道题的 prompt、模型回复和 token", async ({ page }) => {
  await mockAdminIdentity(page);
  await page.route("**/api/quizzes/quiz-debug/generation-debug", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        quiz_id: "quiz-debug",
        book_id: "book-1",
        quiz_title: "调试试卷",
        generation_task_id: "task-debug",
        task_type: "manual_quiz_generation",
        task_status: "completed",
        model_name: "debug-model",
        input_tokens: 120,
        output_tokens: 30,
        total_tokens: 150,
        questions: [{
          question_id: "q1",
          position: 1,
          prompt: "模型生成题目",
          input_tokens: 120,
          output_tokens: 30,
          total_tokens: 150,
          unreported_calls: 0,
          calls: [{
            id: "call-1",
            question_position: 1,
            phase: "quiz_generation",
            call_number: 1,
            model_name: "debug-model",
            request_messages: [
              { role: "system", content: "系统提示" },
              { role: "user", content: "用户输入 prompt" },
            ],
            model_response: '{"questions": []}',
            input_tokens: 120,
            output_tokens: 30,
            total_tokens: 150,
            status: "success",
            error_message: null,
            latency_ms: 240,
            created_at: "2026-09-04T08:00:00Z",
          }],
        }],
        unassigned_calls: [],
      }),
    });
  });

  await page.goto("/quizzes/quiz-debug/generation-debug");
  await expect(page.getByRole("heading", { name: "出题过程 Prompt" })).toBeVisible();
  await expect(page.getByText("模型生成题目")).toBeVisible();
  await expect(page.getByText("用户输入 prompt")).toBeVisible();
  await expect(page.getByText('{"questions": []}')).toBeVisible();
  await expect(page.getByText("150 token").first()).toBeVisible();
  await expect(page.getByText("输入 120")).toBeVisible();
  await expect(page.getByText("输出 30")).toBeVisible();
});

test("出题任务中断后保留逐题状态并支持人工确认", async ({ page }) => {
  await mockAdminIdentity(page);
  await mockInsecureClipboard(page);
  let taskResponse: Record<string, any> = {
    id: "task-intervention",
    book_id: "book-task",
    task_type: "manual_quiz_generation",
    status: "awaiting_intervention",
    source_mode: "pdf",
    generation_theme: "general",
    theme_config: {},
    total_questions: 2,
    completed_questions: 1,
    current_question_position: 2,
    current_phase: "第 2 道题需要人工处理",
    difficulty: "medium",
    duration_minutes: 15,
    single_count: 2,
    multiple_count: 0,
    short_count: 0,
    quiz_id: null,
    error_message: "第 2 道题与已有事实重复",
    question_states: [
      { position: 1, question_type: "single", status: "ready", attempts: 1, error_message: null, question: { prompt: "第一题草稿" }, updated_at: null },
      { position: 2, question_type: "single", status: "awaiting_intervention", attempts: 3, error_message: "第 2 道题与已有事实重复", question: { question_type: "single", prompt: "第二题草稿", options: [{ id: "A", text: "正确" }, { id: "B", text: "错误" }], correct_answers: ["A"], explanation: "解析", knowledge_point: "知识点" }, updated_at: null },
    ],
    created_at: "2026-09-04T08:00:00Z",
    updated_at: "2026-09-04T08:01:00Z",
  };
  await page.route("**/api/books/book-task", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({
      id: "book-task", title: "任务测试书", author: "作者", description: "", resource_type: "book", cover_color: "#2F6B5F", language: "中文", reading_status: "finished", shelf_status: "active", tags: [], pdfs: [], stats: { pdf_count: 0, completed_pdf_count: 0, chunk_count: 0, quiz_count: 0, average_score: null, last_reviewed_at: null, next_review_date: null, material_count: 0, ready_material_count: 0, quote_count: 0, confirmed_quote_count: 0 }, pre_generation_enabled: false, pre_generation_status: "disabled", pre_generation_error: null, pre_generation_quiz_id: null, active_generation_task_id: "task-intervention", active_generation_status: "awaiting_intervention", active_generation_completed_questions: 1, active_generation_total_questions: 2, active_generation_phase: "第 2 道题需要人工处理", model_knowledge_supported: true, model_knowledge_message: null, model_knowledge_checked_at: null, created_at: "2026-09-04T08:00:00Z", updated_at: "2026-09-04T08:01:00Z",
    }) });
  });
  await page.route("**/api/books/book-task/materials", async (route) => {
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });
  await page.route("**/api/books/book-task/quotes**", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [], total: 0, speakers: [], pending_count: 0, confirmed_count: 0 }) });
  });
  await page.route("**/api/quiz-generation-tasks/task-intervention", async (route) => {
    if (route.request().method() === "DELETE") {
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(taskResponse) });
  });
  await page.route("**/api/quiz-generation-tasks/task-intervention/debug", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({
      task_id: "task-intervention",
      calls: [{
        id: "call-2", question_position: 2, phase: "quiz_generation", call_number: 1,
        model_name: "test-model", request_messages: [{ role: "user", content: "第二题输入 Prompt" }],
        model_response: "第二题模型回复", input_tokens: 100, output_tokens: 20, total_tokens: 120,
        status: "success", error_message: null, latency_ms: 200, created_at: "2026-09-04T08:00:00Z",
      }],
    }) });
  });
  let action = "";
  await page.route("**/api/quiz-generation-tasks/task-intervention/questions/2/intervene", async (route) => {
    action = route.request().postDataJSON().action;
    taskResponse = { ...taskResponse, status: "pending", error_message: null, current_phase: "等待继续处理第 2 道题", question_states: taskResponse.question_states.map((state: any) => state.position === 2 ? { ...state, status: "confirmed", error_message: null } : state) };
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(taskResponse) });
  });
  await page.route("**/api/quiz-generation-tasks/task-intervention/cancel", async (route) => {
    taskResponse = { ...taskResponse, status: "cancelled", error_message: "出题任务已由用户手动终止", current_phase: "已手动终止" };
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(taskResponse) });
  });

  await page.goto("/books/book-task/quiz/new");
  await expect(page.getByText("本次出题需要人工处理")).toBeVisible();
  await page.getByRole("button", { name: "人工调整本题" }).first().click();
  await expect(page.getByLabel("第1题人工题干")).toHaveValue("第一题草稿");
  await page.getByRole("button", { name: "收起编辑" }).first().click();
  await expect(page.getByLabel("第1题人工题干")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "人工调整本题" }).first()).toBeVisible();
  await expect(page.getByLabel("第2题人工题干")).toHaveValue("第二题草稿");
  await page.getByText("查看完整题目草稿").nth(1).click();
  await expect(page.getByText("A. 正确（正确答案）")).toBeVisible();
  await expect(page.getByText("解析", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("知识点", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "复制当前出题内容" }).click();
  await expect(page.getByRole("button", { name: "已复制出题内容" })).toBeVisible();
  expect(await readCopiedText(page)).toContain("第二题输入 Prompt");
  expect(await readCopiedText(page)).toContain("第二题模型回复");
  expect(await readCopiedText(page)).toContain("第二题草稿");
  await expect(page.getByRole("button", { name: "终止出题" })).toBeVisible();
  await page.getByRole("button", { name: "确认题目可用" }).click();
  await expect(page.getByText("已确认")).toBeVisible();
  expect(action).toBe("accept");
  await expect(page.getByRole("button", { name: "终止出题" })).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "终止出题" }).click();
  await expect(page.getByText("本次出题已手动终止")).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "删除任务" }).click();
  await expect(page.getByRole("button", { name: "复制当前出题内容" })).toHaveCount(0);
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
  await expect(page.getByRole("heading", { name: "确认重新出题" })).toBeVisible();
  await page.getByRole("button", { name: "确认重新出题" }).click();

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
  await page.route("**/api/quizzes/quiz-1/export", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        format: "read-books-quiz-validation-v1",
        purpose: "请校验题目和答案",
        quiz: {
          id: "quiz-1", book_id: "book-1", book_title: "测试书", title: "第一套试卷",
          difficulty: "medium", duration_minutes: 15, status: "ready", source_mode: "pdf",
          generation_theme: "general", theme_config: {}, total_score: null, max_score: 6,
          elapsed_seconds: null, submitted_at: null, next_review_date: null,
          created_at: "2026-08-03T09:00:00Z",
          questions: [{
            id: "q1", position: 1, question_type: "single", question_subtype: "general",
            prompt: "题干", options: [{ id: "A", text: "选项 A" }, { id: "B", text: "选项 B" }],
            correct_answers: ["A"], explanation: "解析", knowledge_point: "知识点",
            difficulty: "medium", estimated_seconds: 45, reference_answer: null,
            grading_rubric: [], source_evidence: [], quote_entry_ids: [], source_segment_ids: [],
            max_score: 6,
          }],
        },
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
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出题目与答案" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain("题目答案校验.json");
  await page.getByRole("link", { name: "预览题目与答案" }).click();
  await expect(page).toHaveURL(/\/quizzes\/quiz-1\/preview$/);
  await expect(page.getByText("正确答案", { exact: true })).toBeVisible();
  await expect(page.getByText("解析", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/选项 A/)).toBeVisible();
  await page.getByRole("link", { name: "返回试卷概览" }).click();
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
