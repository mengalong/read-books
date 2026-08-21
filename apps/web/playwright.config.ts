import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const root = path.resolve(__dirname, "../..");

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3001",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        channel: process.env.PLAYWRIGHT_CHANNEL,
      },
    },
  ],
  webServer: [
    {
      command: "DATABASE_URL=sqlite:////tmp/read-books-e2e.db conda run --no-capture-output -n read-books alembic -c apps/api/alembic.ini upgrade head && DATABASE_URL=sqlite:////tmp/read-books-e2e.db SEED_DEMO_DATA=false conda run --no-capture-output -n read-books uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8002",
      cwd: root,
      url: "http://localhost:8002/api/health",
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: "NEXT_PUBLIC_API_BASE_URL=http://localhost:8002/api npm run build && PORT=3001 NEXT_PUBLIC_API_BASE_URL=http://localhost:8002/api npm run start",
      cwd: path.resolve(__dirname),
      url: "http://localhost:3001",
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
