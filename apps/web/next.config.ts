import type { NextConfig } from "next";

const buildUpdatedAt = process.env.NEXT_PUBLIC_BUILD_UPDATED_AT || new Date().toISOString();

const nextConfig: NextConfig = {
  // Keep development output separate so a production build cannot invalidate a running dev server.
  distDir: process.env.NODE_ENV === "development" ? ".next-dev" : ".next",
  env: {
    NEXT_PUBLIC_BUILD_UPDATED_AT: buildUpdatedAt,
  },
  reactStrictMode: true,
};

export default nextConfig;
