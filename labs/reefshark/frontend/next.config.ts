import type { NextConfig } from "next";

// Static export served by the FastAPI backend under /app on port 8081 (same
// contract as the original Flask app). basePath/assetPrefix make all routes and
// assets resolve under /app so it works behind the nginx `/app` -> :8081 proxy.
const nextConfig: NextConfig = {
  output: "export",
  basePath: "/app",
  assetPrefix: "/app",
  trailingSlash: true,
  images: { unoptimized: true },
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: true },
};

export default nextConfig;
