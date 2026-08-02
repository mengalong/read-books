import { expect, test } from "@playwright/test";

test("模型设置掩码显示密钥并支持覆盖保存", async ({ page }) => {
  let lastSavedApiKey = "";
  let configuration = {
    id: "default",
    provider_mode: "mock",
    base_url: "",
    model_name: "",
    timeout_ms: 60_000,
    temperature: 0.2,
    api_key_configured: false,
    created_at: null,
    updated_at: null,
  };
  await page.route("**/api/settings/model", async (route) => {
    if (route.request().method() === "PUT") {
      const payload = route.request().postDataJSON();
      if (payload.api_key) lastSavedApiKey = payload.api_key;
      configuration = {
        ...configuration,
        provider_mode: payload.provider_mode,
        base_url: payload.base_url,
        model_name: payload.model_name,
        timeout_ms: payload.timeout_ms,
        temperature: payload.temperature,
        api_key_configured: Boolean(payload.api_key) || configuration.api_key_configured,
      };
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(configuration) });
  });
  await page.route("**/api/settings/model/test", async (route) => {
    const payload = route.request().postDataJSON();
    expect(payload.base_url).toBe("https://models.example.com/v1");
    expect(payload.model_name).toBe("review-model");
    expect(payload.api_key).toBeUndefined();
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        message: "模型接口连接成功",
        latency_ms: 86,
        model_name: "review-model",
        model_response: "连接成功",
      }),
    });
  });
  await page.goto("/settings/model");
  await expect(page.getByRole("heading", { name: "模型设置" })).toBeVisible();

  await page.getByRole("checkbox", { name: /出题与评分模式/ }).check();
  await page.getByLabel("接口地址").fill("https://models.example.com/v1");
  await page.getByLabel("模型名称").fill("review-model");
  await page.getByLabel("API Key").fill("e2e-secret-key");
  await page.getByRole("button", { name: "保存配置" }).click();

  await expect(page.getByText("配置已保存")).toBeVisible();
  await page.reload();
  await expect(page.getByText("已保存密钥")).toBeVisible();
  await expect(page.getByLabel("API Key")).toHaveValue("****************");

  await page.getByLabel("API Key").fill("updated-e2e-secret");
  await page.getByRole("button", { name: "保存配置" }).click();
  expect(lastSavedApiKey).toBe("updated-e2e-secret");
  await expect(page.getByLabel("API Key")).toHaveValue("****************");

  await page.getByRole("button", { name: "测试连接" }).click();
  await expect(page.getByText("模型接口连接成功 · 86 ms")).toBeVisible();
  await expect(page.getByText("模型实际返回")).toBeVisible();
  await expect(page.locator(".curl-response")).toHaveText("连接成功");
  await expect(page.getByText("本次测试命令")).toBeVisible();
  await expect(page.locator(".curl-preview pre")).toContainText("https://models.example.com/v1/chat/completions");
  await expect(page.locator(".curl-preview pre")).toContainText("Authorization: Bearer ***");
  await expect(page.locator(".curl-preview pre")).not.toContainText("updated-e2e-secret");

  await page.getByRole("checkbox", { name: /出题与评分模式/ }).uncheck();
  await page.getByRole("button", { name: "保存配置" }).click();
  await expect(page.getByText("未保存密钥")).toBeVisible();
});
