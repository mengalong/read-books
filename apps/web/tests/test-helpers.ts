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

export async function mockInsecureClipboard(page: Page) {
  await page.addInitScript(() => {
    Object.defineProperty(window, "isSecureContext", {
      configurable: true,
      value: false,
    });
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: undefined,
    });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: (command: string) => {
        if (command !== "copy") return false;
        const activeElement = document.activeElement;
        (window as Window & { __copiedText?: string }).__copiedText =
          activeElement instanceof HTMLTextAreaElement ? activeElement.value : "";
        return true;
      },
    });
  });
}

export function readCopiedText(page: Page) {
  return page.evaluate(
    () => (window as Window & { __copiedText?: string }).__copiedText || "",
  );
}
