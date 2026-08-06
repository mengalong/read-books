import { expect, test } from "@playwright/test";

const currentUser = {
  id: "admin-1",
  username: "admin",
  display_name: "系统管理员",
  role: "admin",
  status: "active",
  must_change_password: false,
  last_login_at: "2026-08-06T08:00:00Z",
  workspace: { id: "workspace-1", name: "系统管理员的工作空间" },
};

test("管理员可以配置微信登录并覆盖已保存的密钥", async ({ page }) => {
  let savedPayload: Record<string, unknown> | null = null;
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(currentUser) });
  });
  await page.route("**/api/settings/wechat-login", async (route) => {
    if (route.request().method() === "PATCH") {
      savedPayload = route.request().postDataJSON();
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "default",
          enabled: true,
          required_for_public_exams: true,
          app_id: "wx-updated-app-id",
          app_secret_configured: true,
          callback_base_url: "https://books.example.com",
          callback_url: "https://books.example.com/api/public/wechat/callback",
          configuration_complete: true,
          created_at: "2026-08-06T08:00:00Z",
          updated_at: "2026-08-06T09:00:00Z",
        }),
      });
      return;
    }
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "default",
        enabled: false,
        required_for_public_exams: false,
        app_id: "wx-old-app-id",
        app_secret_configured: true,
        callback_base_url: "https://books.example.com",
        callback_url: "https://books.example.com/api/public/wechat/callback",
        configuration_complete: true,
        created_at: "2026-08-06T08:00:00Z",
        updated_at: "2026-08-06T08:00:00Z",
      }),
    });
  });

  await page.goto("/settings/wechat");
  await expect(page.getByRole("heading", { name: "微信登录" })).toBeVisible();
  const appSecretInput = page.getByRole("textbox", { name: "AppSecret", exact: true });
  await expect(appSecretInput).toHaveValue("****************");
  await page.getByLabel("微信登录", { exact: true }).check();
  await page.getByLabel("要求微信认证").check();
  await page.getByLabel("AppID").fill("wx-updated-app-id");
  await appSecretInput.fill("new-app-secret");
  await page.getByRole("button", { name: "保存配置" }).click();

  await expect(page.getByText("配置已保存")).toBeVisible();
  expect(savedPayload).toMatchObject({
    enabled: true,
    required_for_public_exams: true,
    app_id: "wx-updated-app-id",
    app_secret: "new-app-secret",
  });
  await expect(appSecretInput).toHaveValue("****************");
});
