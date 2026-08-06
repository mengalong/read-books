import type { Page } from "@playwright/test";

const adminUser = {
  id: "admin-1",
  username: "admin",
  display_name: "系统管理员",
  role: "admin",
  status: "active",
  must_change_password: false,
  last_login_at: "2026-08-06T08:00:00Z",
  workspace: { id: "workspace-1", name: "系统管理员的工作空间" },
};

export async function mockAdminIdentity(page: Page) {
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(adminUser),
    });
  });
}
