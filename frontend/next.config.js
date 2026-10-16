// A type hint so editors can autocomplete and check the options below.
/** @type {import('next').NextConfig} */
const nextConfig = {
  // Self-contained server bundle for the Docker image (its Dockerfile sets NEXT_OUTPUT).
  // Left off otherwise so platforms with their own Next.js builder (Vercel) build normally.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  // Do not send the "X-Powered-By: Next.js" header (it reveals which software the site runs).
  poweredByHeader: false,
};

// Export the configuration so Next.js can read it.
module.exports = nextConfig;
