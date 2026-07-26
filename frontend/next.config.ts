import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The repo root also has a package-lock.json (it runs both services with
  // concurrently), so Turbopack infers the wrong workspace root and builds an
  // empty client manifest in dev. Pin the root to this directory.
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
