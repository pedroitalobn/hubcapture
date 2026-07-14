/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@hub/api-client"],
  // build autossuficiente p/ imagem Docker enxuta (server + deps mínimos)
  output: "standalone",
};

export default nextConfig;
