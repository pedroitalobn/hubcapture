import { headers } from "next/headers";
import type { Branding } from "./marca";
import { MARCA_PADRAO } from "./marca";

/**
 * Resolve a marca do HOST no servidor (white label, §69) — roda no layout raiz,
 * antes da primeira pintura, para a tela de login já sair vestida sem piscar as
 * cores do Hub Capture.
 *
 * Fala com a API pela rede interna (mesmo `API_INTERNAL_URL` do proxy) e cacheia
 * por host por 60s. API fora do ar ou lenta NUNCA derruba a página: cai no Hub
 * Capture.
 */
export async function marcaDoHost(): Promise<Branding> {
  const h = await headers();
  const host = (h.get("x-forwarded-host") ?? h.get("host") ?? "").split(",")[0]!.trim();
  if (!host) return MARCA_PADRAO;
  const api = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
  try {
    const resp = await fetch(
      `${api}/api/v1/branding?host=${encodeURIComponent(host)}`,
      { next: { revalidate: 60 }, signal: AbortSignal.timeout(2500) },
    );
    if (!resp.ok) return MARCA_PADRAO;
    const marca = (await resp.json()) as Branding;
    // cinto e suspensório: o CSS vai dentro de <style>; nada pode fechar a tag
    return { ...marca, css: (marca.css ?? "").replace(/<\/(style)/gi, "<\\/$1") };
  } catch {
    return MARCA_PADRAO;
  }
}
