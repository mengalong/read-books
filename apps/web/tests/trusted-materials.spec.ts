import { expect, test, type Page } from "@playwright/test";

import { mockAdminIdentity } from "./test-helpers";

const book = {
  id: "book-topic",
  workspace_id: "workspace-1",
  owner_user_id: "admin-1",
  owner_display_name: "系统管理员",
  resource_type: "tv_series",
  title: "潜伏",
  author: "姜伟",
  description: "电视剧经典台词专题测试",
  cover_color: "#2F6B5F",
  language: "中文",
  reading_status: "finished",
  shelf_status: "active",
  tags: ["谍战"],
  created_at: "2026-09-03T08:00:00Z",
  updated_at: "2026-09-03T08:00:00Z",
  pre_generation_enabled: false,
  pre_generation_status: "disabled",
  pre_generation_error: null,
  pre_generation_quiz_id: null,
  active_generation_task_id: null,
  active_generation_status: null,
  active_generation_completed_questions: 0,
  active_generation_total_questions: 0,
  active_generation_phase: null,
  model_knowledge_supported: true,
  model_knowledge_message: "high: 已确认资源内容",
  model_knowledge_checked_at: "2026-09-03T08:00:00Z",
  stats: {
    pdf_count: 0,
    completed_pdf_count: 0,
    chunk_count: 0,
    quiz_count: 0,
    average_score: null,
    last_reviewed_at: null,
    next_review_date: null,
    material_count: 1,
    ready_material_count: 0,
    quote_count: 10,
    confirmed_quote_count: 10,
  },
  pdfs: [],
  quizzes: [],
};

const material = {
  id: "material-1",
  book_id: book.id,
  material_type: "subtitle",
  file_format: "srt",
  file_name: "潜伏第1集.srt",
  file_size: 2048,
  season_number: 1,
  episode_label: "第 1 集",
  version_label: "DVD 字幕版",
  parse_status: "needs_review",
  error_message: null,
  segment_count: 12,
  quote_count: 10,
  created_at: "2026-09-03T08:00:00Z",
  updated_at: "2026-09-03T08:00:00Z",
};

function quote(index: number, overrides: Record<string, unknown> = {}) {
  return {
    id: `quote-${index}`,
    book_id: book.id,
    material_id: material.id,
    material_file_name: material.file_name,
    source_segment_ids: [`segment-${index}`],
    quote_text: `第 ${index} 条可信台词`,
    speaker: index % 2 ? "吴站长" : "余则成",
    speaker_origin: index === 1 ? "unknown" : "provided",
    context: `第 ${index} 条台词上下文`,
    season_number: 1,
    episode_number: 1,
    start_ms: index * 1000,
    end_ms: index * 1000 + 800,
    page_number: null,
    review_status: "confirmed",
    enabled_for_generation: true,
    created_at: "2026-09-03T08:00:00Z",
    updated_at: "2026-09-03T08:00:00Z",
    ...overrides,
  };
}

async function mockBookAndMaterials(
  page: Page,
  initialMaterials: Record<string, unknown>[] = [material],
) {
  let materials = [...initialMaterials];
  await page.route(`**/api/books/${book.id}`, async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(book) });
  });
  await page.route(`**/api/books/${book.id}/materials`, async (route) => {
    if (route.request().method() === "POST") {
      materials = [
        {
          ...material,
          id: "material-2",
          material_type: "quote_sheet",
          file_format: "csv",
          file_name: "吴站长台词.csv",
          parse_status: "pending",
          segment_count: 0,
          quote_count: 0,
        },
        ...materials,
      ];
      await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(materials[0]) });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(materials) });
  });
}

test("资源详情支持上传可信台词资料", async ({ page }) => {
  await mockAdminIdentity(page);
  await mockBookAndMaterials(page);

  await page.goto(`/books/${book.id}`);
  await expect(page.getByRole("heading", { name: "可信资料" })).toBeVisible();
  await expect(page.getByText(material.file_name)).toBeVisible();
  await expect(page.getByText("电影和电视剧不支持 PDF 上传")).toHaveCount(0);

  await page.getByRole("button", { name: "上传资料" }).click();
  await expect(page.getByRole("heading", { name: "上传可信资料" })).toBeVisible();
  await page.getByLabel("资料类型").selectOption("quote_sheet");
  await page.getByLabel("选择文件").setInputFiles({
    name: "吴站长台词.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("台词,角色\n会议开始,吴站长\n"),
  });
  await page.getByRole("button", { name: "上传并解析" }).click();
  await expect(page.getByText("吴站长台词.csv")).toBeVisible();
});

test("台词校对支持修正角色并确认", async ({ page }) => {
  await mockAdminIdentity(page);
  await mockBookAndMaterials(page);
  let current = quote(1, {
    speaker: null,
    speaker_origin: "unknown",
    review_status: "pending",
    enabled_for_generation: false,
  });
  let patchPayload: Record<string, unknown> | null = null;
  await page.route(`**/api/books/${book.id}/quotes**`, async (route) => {
    if (route.request().method() === "PATCH") {
      patchPayload = route.request().postDataJSON();
      current = {
        ...current,
        ...patchPayload,
        speaker_origin: "confirmed",
        enabled_for_generation: true,
      };
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(current) });
      return;
    }
    const requestedStatus = new URL(route.request().url()).searchParams.get("review_status");
    const items = !requestedStatus || current.review_status === requestedStatus ? [current] : [];
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({
      items,
      total: items.length,
      speakers: current.speaker ? [current.speaker] : [],
      pending_count: current.review_status === "pending" ? 1 : 0,
      confirmed_count: current.review_status === "confirmed" ? 1 : 0,
    }) });
  });

  await page.goto(`/books/${book.id}/quotes`);
  await expect(page.getByText("第 1 条可信台词")).toBeVisible();
  await page.getByRole("textbox", { name: "角色" }).fill("吴站长");
  await page.getByRole("button", { name: "确认台词" }).click();
  await expect.poll(() => patchPayload).toMatchObject({ speaker: "吴站长", review_status: "confirmed" });
  await expect(page.getByText("没有符合条件的台词")).toBeVisible();
});

test("生成页提交经典台词专题范围", async ({ page }) => {
  await mockAdminIdentity(page);
  await mockBookAndMaterials(page);
  const quoteItems = Array.from({ length: 10 }, (_, index) => quote(index + 1));
  let generationPayload: Record<string, unknown> | null = null;
  await page.route(`**/api/books/${book.id}/quotes**`, async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({
      items: quoteItems,
      total: quoteItems.length,
      speakers: ["余则成", "吴站长"],
      pending_count: 0,
      confirmed_count: quoteItems.length,
    }) });
  });
  await page.route(`**/api/books/${book.id}/quizzes`, async (route) => {
    generationPayload = route.request().postDataJSON();
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({
      id: "task-topic",
      book_id: book.id,
      task_type: "manual_quiz_generation",
      status: "pending",
      source_mode: "material",
      generation_theme: "classic_quotes",
      theme_config: generationPayload?.theme_config,
      total_questions: 10,
      completed_questions: 0,
      current_question_position: null,
      current_phase: "等待开始",
      difficulty: "medium",
      duration_minutes: 15,
      single_count: 5,
      multiple_count: 3,
      short_count: 2,
      quiz_id: null,
      error_message: null,
      created_at: "2026-09-03T08:00:00Z",
      updated_at: "2026-09-03T08:00:00Z",
    }) });
  });
  await page.route("**/api/quiz-generation-tasks/task-topic", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      id: "task-topic",
      status: "processing",
      total_questions: 10,
      completed_questions: 1,
      current_phase: "正在生成第 2 道题",
    }) });
  });

  await page.goto(`/books/${book.id}/quiz/new`);
  await page.getByRole("button", { name: "经典台词" }).click();
  await expect(page.getByText("可信资料", { exact: true })).toBeVisible();
  await expect(page.getByText("10 条台词", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "生成复习试卷" }).click();
  await expect.poll(() => generationPayload).toMatchObject({
    generation_theme: "classic_quotes",
    theme_config: {
      material_ids: [material.id],
      character_names: [],
      question_subtypes: ["quote_speaker", "quote_context", "quote_meaning"],
    },
  });
});
