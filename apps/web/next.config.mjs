/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@hub/api-client"],
  // build autossuficiente p/ imagem Docker enxuta (server + deps mínimos)
  output: "standalone",
  // Proxy same-origin → API: o navegador chama /api/v1/* no domínio da web e o
  // Next repassa para a API pela rede interna (compose: http://api:8000). Isso
  // dispensa domínio público para a API e NEXT_PUBLIC_API_URL no build. Se
  // NEXT_PUBLIC_API_URL for definido, o client chama a API direto e este proxy
  // fica ocioso. API_INTERNAL_URL é resolvido no build (standalone congela o
  // config) — o default cobre compose (api) e dev local (localhost).
  async rewrites() {
    const apiInterna =
      process.env.API_INTERNAL_URL ?? "http://localhost:8000";
    return [
      { source: "/api/v1/:path*", destination: `${apiInterna}/api/v1/:path*` },
    ];
  },
};

export default nextConfig;
