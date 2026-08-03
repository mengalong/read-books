import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep development output separate so a production build cannot invalidate a running dev server.
  distDir: process.env.NODE_ENV === "development" ? ".next-dev" : ".next",
  reactStrictMode: true,
};

export default nextConfig;
