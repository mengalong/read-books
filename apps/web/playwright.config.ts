import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const root = path.resolve(__dirname, "../..");

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: "DATABASE_URL=sqlite:////tmp/read-books-e2e.db SEED_DEMO_DATA=false conda run --no-capture-output -n read-books uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000",
      cwd: root,
      url: "http://localhost:8000/api/health",
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: "npm run dev",
      cwd: path.resolve(__dirname),
      url: "http://localhost:3000",
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
