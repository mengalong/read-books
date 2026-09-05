import { expect, test } from "@playwright/test";

import { mockAdminIdentity } from "./test-helpers";

test("题库页面展示引用关系并支持人工修改题目", async ({ page }) => {
  await mockAdminIdentity(page);
  let saved: Record<string, unknown> | null = null;
  const entry = {
    id: "bank-1",
    book_id: "book-bank",
    origin_quiz_id: "quiz-1",
    origin_question_id: "question-1",
    question_type: "single",
    question_subtype: "general",
    prompt: "原题干",
    options: [{ id: "A", text: "正确" }, { id: "B", text: "错误" }, { id: "C", text: "干扰" }, { id: "D", text: "干扰" }],
    correct_answers: ["A"],
    explanation: "原解析",
    knowledge_point: "人物行动",
    difficulty: "medium",
    estimated_seconds: 45,
    reference_answer: null,
    grading_rubric: [],
    source_chunk_ids: ["chunk-1"],
    quote_entry_ids: [],
    plot_event_ids: [],
    source_segment_ids: [],
    fact_key: "fact-1",
    fact_claim: "人物采取行动",
    semantic_signature: {},
    source_evidence: [{ chunk_id: "chunk-1", file_name: "source.pdf", page_number: 1, excerpt: "原文", support: "原文" }],
    source_mode: "pdf",
    max_score: 6,
    status: "active",
    use_count: 1,
    created_at: "2026-09-06T08:00:00Z",
    updated_at: "2026-09-06T08:00:00Z",
    usages: [{ id: "usage-1", entry_id: "bank-1", quiz_id: "quiz-1", question_id: "question-1", quiz_title: "原始试卷", question_position: 1, used_at: "2026-09-06T08:00:00Z" }],
  };
  await page.route("**/api/books/book-bank**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/question-bank/bank-1")) {
      saved = route.request().postDataJSON();
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ ...entry, ...saved, updated_at: "2026-09-06T08:01:00Z" }) });
      return;
    }
    if (path.endsWith("/question-bank")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [entry], total: 1, unused_count: 0 }) });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ ...entry, title: "题库测试资源", pdfs: [], quizzes: [], stats: { pdf_count: 0, completed_pdf_count: 0, chunk_count: 0, quiz_count: 0, average_score: null, last_reviewed_at: null, next_review_date: null, material_count: 0, ready_material_count: 0, quote_count: 0, confirmed_quote_count: 0 } }) });
  });

  await page.goto("/books/book-bank/question-bank");
  await expect(page.getByRole("heading", { name: "《题库测试资源》题库" })).toBeVisible();
  await expect(page.getByText("原题干")).toBeVisible();
  await page.getByText("查看试卷引用（1）").click();
  await expect(page.getByText("原始试卷")).toBeVisible();
  await page.getByTitle("编辑题库题目").click();
  await page.getByLabel("题干").fill("修改后的题干");
  await page.getByLabel("知识点").fill("修改后的知识点");
  await page.getByRole("button", { name: "保存题库题目" }).click();
  await expect.poll(() => saved).toMatchObject({ prompt: "修改后的题干", knowledge_point: "修改后的知识点" });
});
