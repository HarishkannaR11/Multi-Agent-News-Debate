/** @type {import('next').NextConfig} */
const nextConfig = {
  // Self-contained server bundle for the Docker image (its Dockerfile sets NEXT_OUTPUT).
  // Left off otherwise so platforms with their own Next.js builder (Vercel) build normally.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  poweredByHeader: false,
};

module.exports = nextConfig;
